#!/usr/bin/env python3
"""Read-only local dashboard and CLI for studio progress across Git worktrees."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
from urllib.parse import parse_qs, urlsplit

from progress_records import LABELS, note
from progress_snapshot import Monitor
from studio_common import ROOT


def make_server(monitor, port=8765, ui_root=None):
    ui_root = Path(ui_root or ROOT / 'apps/monitor/dist').resolve()
    cast_token = secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, status, payload, content_type='application/json; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Cache-Control', 'no-store' if content_type.startswith('application/json') else 'no-cache')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self'; font-src 'self'; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            if self.command == 'HEAD':
                return
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def json(self, status, value):
            self.send(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8'))

        def do_GET(self):
            allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            if self.headers.get('Host') not in allowed:
                return self.json(403, {'error': 'Use the local monitor address'})
            route = urlsplit(self.path)
            try:
                if route.path in ('/', '/index.html'):
                    index = ui_root / 'index.html'
                    if not index.is_file():
                        return self.json(503, {'error': 'Build the monitor UI: npm --prefix apps/monitor ci, then npm --prefix apps/monitor run build. The read-only API remains available.'})
                    return self.send(200, index.read_bytes(), 'text/html; charset=utf-8')
                if route.path == '/logo.png':
                    return self.send(200, (ROOT / 'assets/branding/story-film-studio-logo.png').read_bytes(), 'image/png')
                if route.path.startswith('/assets/'):
                    name = route.path.removeprefix('/assets/')
                    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', name):
                        return self.json(404, {'error': 'Unknown UI asset'})
                    asset = (ui_root / 'assets' / name).resolve()
                    if not asset.is_relative_to(ui_root / 'assets') or not asset.is_file():
                        return self.json(404, {'error': 'Unknown UI asset'})
                    return self.send(200, asset.read_bytes(), mimetypes.guess_type(asset.name)[0] or 'application/octet-stream')
                if route.path == '/api/media':
                    return self.media(parse_qs(route.query))
                if route.path == '/api/projects':
                    return self.json(200, monitor.overview())
                if route.path == '/api/status':
                    identity = parse_qs(route.query).get('project', [''])[0]
                    snapshot = monitor.get(identity)
                    snapshot['cast_control'] = {'token': cast_token, 'scope': 'Character-change requests only; no production, canonical edits or approvals'}
                    return self.json(200, snapshot)
                if route.path == '/api/cast-image':
                    from monitor_cast import cast_image
                    query = parse_qs(route.query)
                    identity = query.get('project', [''])[0]
                    with monitor.lock:
                        info = next((item for item in monitor.projects() if item['id'] == identity), None)
                        if info is None:
                            return self.json(404, {'error': 'Unknown project'})
                        try:
                            path = cast_image(monitor.reader, info['path'], query.get('character', [''])[0], query.get('v', [''])[0])
                        except ValueError:
                            return self.json(404, {'error': 'This registered character reference is not available'})
                    return self.send(200, path.read_bytes(), mimetypes.guess_type(path.name)[0])
                return self.json(404, {'error': 'Not found'})
            except KeyError:
                return self.json(404, {'error': 'Project is not in the watched workspaces'})
            except (OSError, ValueError, TypeError):
                return self.json(503, {'error': 'A production record is being updated. Retrying will keep the last visible snapshot.'})

        def media(self, query):
            identity, part_id, kind = (query.get(key, [''])[0] for key in ('project', 'part', 'kind'))
            if not re.fullmatch(r'part_\d{3,}', part_id):
                return self.json(404, {'error': 'Unknown part'})
            with monitor.lock:
                info = next((project for project in monitor.projects() if project['id'] == identity), None)
                if info is None:
                    return self.json(404, {'error': 'Unknown project'})
                root = Path(info['path']).resolve()
                part = root / 'parts' / part_id
                name = {'preview': 'preview.mp4', 'master': 'final.mp4'}.get(kind)
                if kind == 'shot':
                    shot_id = query.get('shot', [''])[0]
                    timeline = monitor.reader.json(part / 'timeline.json')
                    name = next((shot.get('image') for shot in timeline.get('shots', []) if shot.get('id') == shot_id), None)
                if not name:
                    return self.json(404, {'error': 'Unknown media'})
                source = (part / name).resolve()
                if not source.is_relative_to(root) or not source.is_file():
                    return self.json(404, {'error': 'Media is not available'})
                version = query.get('v', [''])[0]
                if version and (monitor.reader.digest(source) or '')[:12] != version:
                    return self.json(409, {'error': 'A newer media revision is available; refresh the preview'})
            size = source.stat().st_size
            start, end = 0, size - 1
            requested = self.headers.get('Range')
            if requested:
                match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
                if not match or not any(match.groups()):
                    return self.json(416, {'error': 'Use a single valid byte range'})
                if not match[1]:
                    start = max(0, size - int(match[2]))
                else:
                    start = int(match[1])
                    end = min(end, int(match[2])) if match[2] else end
                if start >= size or start > end:
                    self.send_response(416)
                    self.send_header('Content-Range', f'bytes */{size}')
                    self.end_headers()
                    return
            self.send_response(206 if requested else 200)
            self.send_header('Content-Type', mimetypes.guess_type(source.name)[0] or 'application/octet-stream')
            self.send_header('Content-Length', str(max(0, end - start + 1)))
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('X-Content-Type-Options', 'nosniff')
            if requested:
                self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
            self.end_headers()
            if self.command == 'HEAD':
                return
            try:
                with source.open('rb') as stream:
                    stream.seek(start)
                    remaining = end - start + 1
                    while remaining > 0:
                        block = stream.read(min(262144, remaining))
                        if not block:
                            break
                        self.wfile.write(block)
                        remaining -= len(block)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_HEAD(self):
            self.do_GET()

        def do_POST(self):
            if urlsplit(self.path).path != '/api/cast-change':
                return self.json(405, {'error': 'Only explicit character-change requests are supported'})
            allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            host = self.headers.get('Host', '')
            if (host not in allowed or self.headers.get('Origin') != 'http://' + host
                    or not secrets.compare_digest(self.headers.get('X-Studio-Cast-Token', ''), cast_token)):
                return self.json(403, {'error': 'Submit character changes from this local monitor page'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.json(415, {'error': 'Use JSON for the character-change request'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    return self.json(413, {'error': 'Character-change request is too large or empty'})
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict) or set(data) != {'project', 'character_id', 'request', 'base_version', 'id'}:
                    return self.json(400, {'error': 'Provide the selected character, current design and actual change request'})
                with monitor.lock:
                    info = next((item for item in monitor.projects() if item['id'] == data['project']), None)
                if info is None:
                    return self.json(404, {'error': 'Unknown project'})
                from cast import request_change
                result = request_change(info['path'], data['character_id'], data['request'], data['base_version'],
                                        'Actual user submission in the local cast monitor', data['id'])
                return self.json(201, result)
            except (ValueError, KeyError, TypeError) as error:
                return self.json(409, {'error': str(error)})
            except (OSError, RuntimeError):
                return self.json(503, {'error': 'The cast records are busy; retry the same request after refreshing'})

        def do_PUT(self):
            self.json(405, {'error': 'Production and canonical records cannot be edited through the monitor'})

        do_DELETE = do_PATCH = do_PUT
    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def status(project, as_json=False):
    project = Path(project).resolve()
    monitor = Monitor([project.parent.parent], discover=False)
    info = next((item for item in monitor.projects() if Path(item['path']) == project), None)
    if info is None:
        raise ValueError('Select an initialized stories/<safe-slug> project')
    value = monitor.get(info['id'])
    if as_json:
        print(json.dumps(value, indent=2, ensure_ascii=False))
    else:
        print(info['title'] + ' | ' + info['branch'])
        print(value['current']['label'] + ': ' + value['current']['message'])
        print(f"Local steps: {value['steps']['done']}/{value['steps']['total'] or 'not planned'} | Images: {value['assets']['images']}/{value['assets']['shots']} | Voice clips: {value['assets']['clips']}")
        eta = value['current']['eta']
        print('Current operation estimate: ' + (f"{eta['low_seconds']}–{eta['high_seconds']} seconds ({eta['basis']})" if eta['available'] else eta['reason']))
        for item in value['attention']:
            print('Attention: ' + item['message'])
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    show = sub.add_parser('status')
    show.add_argument('project', type=Path)
    show.add_argument('--json', action='store_true')
    serve = sub.add_parser('serve')
    serve.add_argument('--workspace', type=Path, action='append', default=[])
    serve.add_argument('--port', type=int, default=8765, help='Loopback port; 0 chooses an available port')
    serve.add_argument('--no-discover', action='store_true', help='Watch only explicitly configured workspaces')
    report = sub.add_parser('progress')
    report.add_argument('project', type=Path)
    report.add_argument('--stage', choices=tuple(LABELS), required=True)
    report.add_argument('--state', choices=('running', 'waiting', 'complete', 'failed'), required=True)
    report.add_argument('--message', required=True)
    report.add_argument('--completed', type=float)
    report.add_argument('--total', type=float)
    report.add_argument('--unit', default='items')
    report.add_argument('--actor', choices=('agent', 'user', 'provider'), default='agent')
    args = parser.parse_args()
    try:
        if args.action == 'status':
            status(args.project, args.json)
        elif args.action == 'progress':
            print(json.dumps(note(args.project, args.stage, args.state, args.message, args.completed, args.total, args.unit, args.actor), indent=2))
        else:
            if not 0 <= args.port <= 65535:
                raise ValueError('Choose a port from 0 to 65535')
            roots = args.workspace or [ROOT]
            if any(not root.is_dir() for root in roots):
                raise ValueError('Every watched workspace must be an existing directory')
            server = make_server(Monitor(roots, discover=not args.no_discover), args.port)
            print(f'Studio monitor: http://127.0.0.1:{server.server_port}', flush=True)
            print('Read-only • local only • no production or provider requests are started', flush=True)
            if not (ROOT / 'apps/monitor/dist/index.html').is_file():
                print('UI build missing: npm --prefix apps/monitor ci, then npm --prefix apps/monitor run build', flush=True)
            try:
                server.serve_forever(poll_interval=.5)
            except KeyboardInterrupt:
                pass
            finally:
                server.server_close()
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
