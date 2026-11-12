#!/usr/bin/env python3
"""Import/source sound files with reusable metadata; evidence and listening stay explicit."""
import argparse
from pathlib import Path
import shutil
import re
import sys
import tempfile

from mix_audio import probe_duration
from setup_studio import download
from studio_common import ROOT, atomic_json, executable, fingerprint, process, read_json, require_production, sha256_file, utc_now


def generated_sound(cache_root, parameters):
    cache_root = Path(cache_root).resolve()
    identity = fingerprint({'parameters': parameters, 'tool': sha256_file(ROOT / 'tools/generate_sound.py')})
    output = cache_root / (identity + '.wav')
    receipt = output.with_suffix('.wav.json')
    if output.is_file() and receipt.is_file() and read_json(receipt).get('file_sha256') == sha256_file(output):
        return output
    cache_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.sound-', dir=cache_root) as directory:
        scratch = Path(directory).resolve()
        if scratch.parent != cache_root:
            raise ValueError('Generated sound scratch directory escaped its cache')
        candidate = scratch / 'sound.wav'
        command = [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools/generate_sound.py'),
                   '--kind', parameters['kind'], '--duration', str(parameters['duration']),
                   '--seed', str(parameters.get('seed', 7)), '--output', str(candidate)]
        for field, option in (('frequency', '--frequency'), ('peak_db', '--peak-db')):
            if field in parameters:
                command.extend([option, str(parameters[field])])
        process(command)
        candidate.replace(output)
        candidate.with_suffix('.wav.json').replace(receipt)
    return output


def make_loop(source, output, crossfade=0.25):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or output.exists():
        raise ValueError('Loop preparation requires a new output revision')
    duration = probe_duration(source, executable('ffprobe'))
    if not 0 < crossfade < duration / 2:
        raise ValueError('Crossfade must be positive and shorter than half the source')
    output.parent.mkdir(parents=True, exist_ok=True)
    graph = (f'[0:a]asplit=3[a][b][c];[a]atrim=start={crossfade}:end={duration-crossfade},asetpts=PTS-STARTPTS[mid];'
             f'[b]atrim=start={duration-crossfade}:end={duration},asetpts=PTS-STARTPTS[tail];'
             f'[c]atrim=start=0:end={crossfade},asetpts=PTS-STARTPTS[head];'
             f'[tail][head]acrossfade=d={crossfade}:c1=tri:c2=tri[seam];[mid][seam]concat=n=2:v=0:a=1[out]')
    process([executable('ffmpeg'), '-v', 'error', '-i', str(source), '-filter_complex', graph,
             '-map', '[out]', '-c:a', 'pcm_s16le', str(output)])
    atomic_json(output.with_suffix('.loop.json'), {'source_sha256': sha256_file(source), 'output_sha256': sha256_file(output),
                                                  'crossfade': crossfade, 'duration': probe_duration(output),
                                                  'qa_status': 'listening_pending'})
    return output


def register(project, source, asset_id, kind, metadata, tags=None):
    project, source = Path(project).resolve(), Path(source).resolve()
    if not re.fullmatch(r'AUD-\d{3,}', asset_id):
        raise ValueError('Audio asset IDs must use AUD-### naming')
    method = metadata.get('method')
    tool = 'procedural-audio' if method == 'procedural' else 'https-audio' if method == 'sourced' else 'provided-audio'
    require_production(project, stage='sound', tool=tool)
    registry_path = project / 'audio/assets.json'
    registry = read_json(registry_path, {'schema_version': 1, 'assets': {}})
    if asset_id in registry['assets']:
        existing = registry['assets'][asset_id]
        if existing.get('sha256') != sha256_file(source):
            raise ValueError('Audio asset ID already names different bytes; create an explicit new ID/revision')
        return existing
    folders = {'ambience': 'ambience', 'sfx': 'sfx', 'music': 'music'}
    if kind not in folders:
        raise ValueError('kind must be ambience, sfx or music')
    duration = probe_duration(source, executable('ffprobe'))
    digest = sha256_file(source)
    destination = project / 'audio' / folders[kind] / (asset_id + '-' + digest[:12] + source.suffix.lower())
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source != destination:
        shutil.copy2(source, destination)
    record = {'file': destination.relative_to(registry_path.parent).as_posix(), 'sha256': digest,
              'kind': kind, 'duration': duration, 'source': metadata, 'tags': tags or [],
              'rights_status': 'unverified', 'rights_evidence': None,
              'qa_status': 'pending', 'qa_notes': None, 'registered_at': utc_now()}
    registry['assets'][asset_id] = record
    atomic_json(registry_path, registry)
    return record


def search(project, tags=None, kind=None):
    registry = read_json(Path(project) / 'audio/assets.json')
    return {identity: record for identity, record in registry['assets'].items()
            if (not kind or record.get('kind') == kind)
            and set(tags or []).issubset(set(record.get('tags', [])))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    sub = parser.add_subparsers(dest='action', required=True)
    add = sub.add_parser('add')
    add.add_argument('--file', type=Path)
    add.add_argument('--download-url')
    add.add_argument('--source-page', required=True)
    add.add_argument('--creator', required=True)
    add.add_argument('--terms', required=True)
    add.add_argument('--id', required=True)
    add.add_argument('--kind', required=True, choices=('ambience', 'sfx', 'music'))
    add.add_argument('--tags', nargs='*', default=[])
    find = sub.add_parser('search')
    find.add_argument('--kind')
    find.add_argument('--tags', nargs='*', default=[])
    review = sub.add_parser('review')
    review.add_argument('--id', required=True)
    review.add_argument('--rights-evidence')
    review.add_argument('--listening-notes')
    loop = sub.add_parser('loop')
    loop.add_argument('--file', required=True, type=Path)
    loop.add_argument('--output', required=True, type=Path)
    loop.add_argument('--crossfade', type=float, default=0.25)
    args = parser.parse_args()
    try:
        if args.action == 'search':
            print(search(args.project, args.tags, args.kind))
            return
        require_production(args.project, stage='sound')
        if args.action == 'loop':
            print(make_loop(args.file, args.output, args.crossfade))
        elif args.action == 'review':
            path = args.project / 'audio/assets.json'
            registry = read_json(path)
            record = registry['assets'][args.id]
            if args.rights_evidence:
                record.update(rights_status='verified', rights_evidence=args.rights_evidence)
            if args.listening_notes:
                record.update(qa_status='passed', qa_notes=args.listening_notes)
            atomic_json(path, registry)
        else:
            if bool(args.file) == bool(args.download_url):
                raise ValueError('Choose exactly one actual source file or HTTPS download URL')
            source = args.file
            if args.download_url:
                from workflow import require_download
                from urllib.parse import urlparse
                suffix = Path(urlparse(args.download_url).path).suffix
                if suffix.lower() not in ('.wav', '.mp3', '.flac', '.ogg', '.m4a'):
                    raise ValueError('Download must identify a supported audio file format')
                hosts = require_download(args.project, args.download_url)
                source = download(args.download_url, args.project / 'production/cache/downloads' / (args.id + suffix), allowed_hosts=hosts)
            metadata = {'method': 'sourced' if args.download_url else 'provided', 'source_url': args.source_page,
                        'creator': args.creator, 'license_or_terms': args.terms,
                        'retrieved_at': utc_now()}
            print(register(args.project, source, args.id, args.kind, metadata, args.tags)['file'])
    except (ValueError, OSError, RuntimeError, KeyError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
