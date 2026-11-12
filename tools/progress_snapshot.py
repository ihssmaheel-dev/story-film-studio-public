"""Read-only, bounded snapshots of actual studio records across worktrees."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import threading
import time

from progress_records import LABELS, label


def timestamp(value):
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp() if isinstance(value, str) else None
    except (ValueError, TypeError, OverflowError):
        return None


def age(value, now):
    when = timestamp(value)
    return max(0, now - when) if when is not None else None


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def public_text(value, limit=500):
    return str(value or '').replace('\x00', '')[:limit]


class Reader:
    """Keep last good JSON during concurrent legacy writes; expose the warning."""
    def __init__(self):
        self.cache, self.warnings, self.hashes = {}, [], {}

    def digest(self, path):
        if path is None:
            return None
        path = Path(path)
        try:
            before = path.stat()
            key = (str(path), before.st_size, before.st_mtime_ns)
            if key in self.hashes:
                return self.hashes[key]
            value = hashlib.sha256()
            with path.open('rb') as source:
                for block in iter(lambda: source.read(1048576), b''):
                    value.update(block)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                return None
            self.hashes[key] = value.hexdigest()
            return self.hashes[key]
        except OSError:
            return None

    def json(self, path, default=None):
        path = Path(path)
        default = {} if default is None else default
        try:
            stat = path.stat()
            if stat.st_size > 4 * 1024 * 1024:
                raise ValueError('record exceeds the monitor size limit')
            stamp = (stat.st_mtime_ns, stat.st_size)
            old = self.cache.get(str(path))
            if old and old[0] == stamp:
                return old[1]
            value = json.loads(path.read_text(encoding='utf-8-sig'), parse_constant=lambda _: None)
            if not isinstance(value, dict):
                raise ValueError('record must be an object')
            self.cache[str(path)] = (stamp, value)
            return value
        except FileNotFoundError:
            return default
        except (OSError, ValueError, TypeError):
            self.warnings.append(path.name + ': record is being updated or is unreadable; showing last available data')
            return self.cache.get(str(path), (None, default))[1]

    def lines(self, path, count=100):
        try:
            with Path(path).open('rb') as stream:
                stream.seek(0, 2)
                size = stream.tell()
                stream.seek(max(0, size - 131072))
                content = stream.read().decode('utf-8', errors='replace').splitlines()
            result = []
            for line in content[-count:]:
                try:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        result.append(value)
                except ValueError:
                    continue
            return result
        except OSError:
            return []


def contained(project, name):
    if not isinstance(name, str) or not name:
        return None
    path = (project / name).resolve()
    return path if path.is_relative_to(project) else None


def estimate(job, timings):
    """An operation range, never a fictional fresh-film completion promise."""
    if job['state'] != 'running':
        return {'available': False, 'reason': 'No verified active operation'}
    elapsed = job.get('elapsed_seconds')
    done, total = job.get('completed'), job.get('total')
    if finite(done) and finite(total) and elapsed and done >= 2 and 0 < done < total and elapsed >= 2:
        remaining = elapsed / done * (total - done)
        return {'available': True, 'low_seconds': round(remaining * .65), 'high_seconds': max(1, round(remaining * 1.6)),
                'basis': 'Measured pace of this operation', 'confidence': 'developing', 'scope': 'current operation'}
    samples = [item['seconds'] for item in timings if item.get('job') == job['id'] and
               not item.get('cache_hit') and not item.get('error') and finite(item.get('seconds')) and item['seconds'] > 0]
    if len(samples) >= 2:
        samples = sorted(samples[-12:])
        low, high = samples[max(0, len(samples) // 4)] * .7, samples[min(len(samples) - 1, 3 * len(samples) // 4)] * 1.5
        if elapsed is not None and elapsed >= high:
            return {'available': False, 'reason': 'Taking longer than earlier runs; recalculating after new progress'}
        return {'available': True, 'low_seconds': round(max(0, low - (elapsed or 0))),
                'high_seconds': round(max(1, high - (elapsed or 0))),
                'basis': f'{len(samples)} earlier successful runs of this operation',
                'confidence': 'historical', 'scope': 'current operation'}
    if finite(done) and finite(total) and done >= total:
        return {'available': False, 'reason': 'Finalizing and checking the output'}
    return {'available': False, 'reason': 'Learning from the first run; more measured progress is needed'}


def remaining_estimate(planned, jobs, timings, status, missing_images=False):
    if not planned or status != 'running':
        return {'available': False, 'reason': 'No active complete local run plan'}
    if missing_images and any(identity.startswith('render:') for identity in planned):
        return {'available': False, 'reason': 'Image generation remains outside the timed local pass'}
    estimates = []
    for identity in planned:
        job = jobs[identity]
        if job['state'] in ('complete', 'cached'):
            continue
        candidate = estimate(dict(job, state='running', elapsed_seconds=0), timings) if job['state'] == 'pending' else job['eta']
        if not candidate.get('available'):
            return {'available': False, 'reason': 'Some remaining steps have insufficient timing evidence'}
        estimates.append(candidate)
    if not estimates:
        return {'available': False, 'reason': 'Finalizing the selected local pass'}
    return {'available': True, 'low_seconds': sum(item['low_seconds'] for item in estimates),
            'high_seconds': sum(item['high_seconds'] for item in estimates), 'scope': 'selected local pass',
            'basis': 'Current measured pace and earlier successful runs; creative work and human review are excluded'}


class Monitor:
    def __init__(self, roots, discover=True):
        self.roots = list(dict.fromkeys(Path(root).resolve() for root in roots))
        self.discover = discover
        self.reader, self.lock = Reader(), threading.RLock()
        self.last_discovery, self.workspaces = 0, self.roots[:]

    def worktrees(self):
        if not self.discover or time.monotonic() - self.last_discovery < 15:
            return self.workspaces
        found = self.roots[:]
        for root in self.roots:
            try:
                result = subprocess.run(['git', '-C', str(root), 'worktree', 'list', '--porcelain'],
                                        capture_output=True, text=True, encoding='utf-8', timeout=3)
                if result.returncode == 0:
                    found.extend(Path(line[9:]).resolve() for line in result.stdout.splitlines() if line.startswith('worktree '))
            except (OSError, subprocess.TimeoutExpired):
                pass
        self.workspaces = list(dict.fromkeys(found))
        self.last_discovery = time.monotonic()
        return self.workspaces

    def projects(self):
        result, seen = [], set()
        for workspace in self.worktrees():
            directory = workspace / 'stories'
            if not directory.is_dir():
                continue
            for project in sorted(directory.iterdir()):
                project = project.resolve()
                if (not project.is_relative_to(directory.resolve()) or project in seen or
                        not (project / 'creative/intake.json').is_file()):
                    continue
                seen.add(project)
                intake = self.reader.json(project / 'creative/intake.json')
                git = self.reader.json(project / 'production/git.json')
                result.append({'id': hashlib.sha256(str(project).encode()).hexdigest()[:20],
                               'title': public_text(intake.get('title') or project.name.replace('-', ' ').title(), 100),
                               'branch': public_text(git.get('branch') or 'Unrecorded branch', 100),
                               'workspace': str(workspace), 'path': str(project)})
        return result

    def overview(self):
        with self.lock:
            self.reader.warnings = []
            rows = []
            for project in self.projects():
                snapshot = self.snapshot(project)
                rows.append({**project, 'state': snapshot['state'], 'updated_at': snapshot['updated_at'],
                             'active': snapshot['current']['label'], 'attention_count': len(snapshot['attention'])})
            rows.sort(key=lambda item: (item['state'] == 'running', timestamp(item['updated_at']) or 0), reverse=True)
            return {'projects': rows, 'observed_at': datetime.now(timezone.utc).isoformat(), 'read_only': True}

    def get(self, identity):
        with self.lock:
            self.reader.warnings = []
            for project in self.projects():
                if project['id'] == identity:
                    return self.snapshot(project)
            raise KeyError('Project is not in the watched workspaces')

    def snapshot(self, info, now=None):
        now = time.time() if now is None else now
        project = Path(info['path'])
        read = self.reader.json
        status = read(project / 'production/status.json')
        run = read(project / 'production/progress/run.json')
        note = read(project / 'production/progress/agent.json')
        last = read(project / 'production/last-run.json')
        intake = read(project / 'creative/intake.json')
        source = read(project / 'creative/source.json')
        ledger = read(project / 'continuity/story-ledger.json')
        timelines, part_rows, jobs, events, attention, media = {}, [], {}, [], [], []
        timings = self.reader.lines(project / 'production/logs/timings.jsonl', 400)
        for identity, raw in status.get('jobs', {}).items():
            if not isinstance(raw, dict):
                continue
            jobs[identity] = self.job(identity, raw, now, live=False)
        for path in (project / 'production/progress/jobs').glob('*.json'):
            raw = read(path)
            identity = raw.get('job')
            if isinstance(identity, str):
                jobs[identity] = self.job(identity, raw, now, live=True)
        for job in jobs.values():
            # Prefer the measured timer over whole-second legacy timestamps.
            finished = timestamp(job.get('finished_at'))
            if job['state'] in ('complete', 'failed') and finished is not None and not job['instrumented']:
                measured = next((item for item in reversed(timings) if item.get('job') == job['id'] and
                                 not item.get('cache_hit') and finite(item.get('seconds')) and item['seconds'] >= 0 and
                                 bool(item.get('error')) == (job['state'] == 'failed') and
                                 timestamp(item.get('at')) is not None and abs(timestamp(item['at']) - finished) < 3), None)
                if measured:
                    job['elapsed_seconds'] = measured['seconds']
            job['eta'] = estimate(job, timings)
            if job['state'] in ('failed', 'interrupted'):
                attention.append({'kind': 'error', 'actor': 'agent', 'message': job['label'] + ' needs attention before continuing.'})
            elif job['state'] == 'stale':
                attention.append({'kind': 'stale', 'actor': 'agent', 'message': job['label'] + ' has no recent heartbeat. Check the runner before retrying.'})
        image_requests, speech_requests = [], []
        external = []
        for directory, target in (('image-jobs', image_requests), ('speech-jobs', speech_requests)):
            for path in sorted((project / 'production' / directory).glob('*.json'))[-1000:]:
                record = read(path)
                target.append(record)
                if record.get('status') in ('needs_attention', 'requesting'):
                    if record.get('status') == 'requesting':
                        cast_sheet = directory == 'image-jobs' and record.get('reference_group') == 'characters'
                        external.append({'id': ('cast:provider:' if cast_sheet else 'provider:' + directory + ':') + path.stem, 'label': 'Cast-sheet request' if cast_sheet else 'Image generation' if directory == 'image-jobs' else 'Voice generation',
                                         'state': 'provider_wait', 'message': 'Request submitted; waiting for a provider result.',
                                         'elapsed_seconds': age(record.get('started_at') or record.get('created_at'), now),
                                         'started_at': record.get('started_at') or record.get('created_at'),
                                         'heartbeat_age_seconds': None, 'percent': None,
                                         'eta': {'available': False, 'reason': 'This provider has not reported a completion estimate'}})
                    unknown = record.get('status') == 'needs_attention' and record.get('outcome_known') is not True
                    if unknown:
                        attention.append({'kind': 'error', 'actor': 'agent', 'message': 'A provider result needs reconciliation. Automatic retries remain blocked.'})
        image_reviews = read(project / 'production/image-reviews.json').get('reviews', {})
        for part in sorted((project / 'parts').glob('part_*')):
            shots = read(part / 'shots.json').get('shots', [])
            timeline = read(part / 'timeline.json')
            timelines[part.name] = timeline
            timeline_shots = {shot.get('id'): shot for shot in timeline.get('shots', [])}
            image_count = reviewed_count = 0
            for shot in shots:
                path = contained(project, str(part.relative_to(project) / timeline_shots.get(shot.get('id'), shot).get('image', '')))
                if path and path.is_file():
                    image_count += 1
                    reviewed_count += image_reviews.get(part.name + '/' + str(shot.get('id')), {}).get('verdict') == 'passed'
            script = read(part / 'speech.json').get('utterances', [])
            narration = contained(project, str(part.relative_to(project) / timeline.get('narration_file', ''))) if timeline.get('narration_file') else None
            chunks = read(narration.with_suffix('.chunks.json')).get('chunks', []) if narration else []
            clips = sum(bool((path := contained(project, str(narration.parent.relative_to(project) / item.get('file', '')))) and path.is_file())
                        for item in chunks) if narration else 0
            part_rows.append({'id': part.name, 'title': public_text(read(part / 'part.json').get('title') or part.name.replace('_', ' ').title(), 100),
                              'images': {'done': image_count, 'total': len(shots), 'reviewed': reviewed_count},
                              'voice': {'done': clips, 'total': len(script) or len(chunks) or None,
                                        'applicable': bool(timeline.get('narration_file'))},
                              'preview': (part / 'preview.mp4').is_file(), 'master': (part / 'final.mp4').is_file(),
                              'duration_seconds': timeline.get('duration') if finite(timeline.get('duration')) else None})
            from monitor_media import part_view
            media.append(part_view(self.reader, info, part, timeline, chunks))
        for item in media:
            if item['preview']['review_state'] == 'decision_needed':
                attention.append({'kind': 'decision', 'actor': 'user', 'message': item['part'].replace('part_', 'Part ') + ': watch the current preview, updated voices and captions, then give your production agent a preview decision.'})
            elif item['voice_changes'] and item['voice_changes'][-1]['state'] in ('speech_pending', 'preview_pending'):
                attention.append({'kind': 'voice_change', 'actor': 'agent', 'message': 'Voice revision is being applied. ' + item['preview']['reasons'][0]})
        for item in last.get('parts', []):
            for action in item.get('next_actions', []):
                attention.append({'kind': 'waiting', 'actor': action.get('actor', 'agent'), 'message': public_text(action.get('message'))})
            if not item.get('next_actions'):
                attention.extend({'kind': 'waiting', 'actor': 'agent', 'message': public_text(message)} for message in item.get('waiting_for', []))
        reviewed_note = note.get('stage') == 'review' and note.get('actor') == 'user' and media and all(item['preview']['approved'] for item in media)
        if note.get('status') == 'waiting' and not reviewed_note:
            attention.append({'kind': 'waiting', 'actor': note.get('actor', 'agent'), 'message': public_text(note.get('message'))})
        unique = {(item['kind'], item['message']): item for item in attention}
        attention = list(unique.values())
        active = sorted([job for job in jobs.values() if job['state'] == 'running' and not job['id'].startswith('run:')],
                        key=lambda job: timestamp(job.get('started_at')) or 0, reverse=True)
        coordinator = [job for job in jobs.values() if job['state'] == 'running' and job['id'].startswith('run:')]
        reported = sorted([job for job in jobs.values() if job['state'] == 'reported'], key=lambda job: timestamp(job.get('started_at')) or 0, reverse=True)
        selected = active[0] if active else external[-1] if external else coordinator[0] if coordinator else reported[0] if reported else None
        current = {'label': 'Ready when you are', 'message': 'No live operation is reporting right now.', 'state': 'idle',
                   'elapsed_seconds': None, 'heartbeat_age_seconds': None, 'percent': None,
                   'eta': {'available': False, 'reason': 'An estimate appears once a measured operation is running'}}
        if selected:
            current = selected
        elif note and note.get('status') == 'running' and (timestamp(note.get('at')) or 0) >= max(
                (timestamp(job.get('finished_at')) or 0 for job in jobs.values()), default=0):
            recent = age(note.get('at'), now)
            done, total = note.get('completed'), note.get('total')
            measured = finite(done) and finite(total) and total > 0 and 0 <= done <= total
            current.update(label=public_text(note.get('label')), message=public_text(note.get('message')),
                           state='reported' if recent is not None and recent <= 120 else 'stale',
                           heartbeat_age_seconds=recent, origin='agent-note',
                           completed=done if measured else None, total=total if measured else None,
                           unit=public_text(note.get('unit'), 40), percent=100 * done / total if measured else None)
        elif attention:
            current.update(label='Needs attention' if any(x['kind'] == 'error' for x in attention) else
                           'Your preview decision' if any(x['kind'] == 'decision' for x in attention) else
                           'Updating the selected voice' if any(x['kind'] == 'voice_change' for x in attention) else 'Waiting for the next step',
                           message=attention[0]['message'], state='waiting')
        elif run.get('status') == 'local_complete':
            current.update(label='Selected local steps finished', message='Preview review, playback and delivery follow their own recorded checks.', state='idle')
        planned = run.get('planned_jobs', [])
        for identity in planned:
            if identity not in jobs or jobs[identity].get('run_id') != run.get('run_id'):
                jobs[identity] = {'id': identity, 'label': label(identity), 'state': 'pending',
                                  'part': next((value for value in identity.split(':') if value.startswith('part_')), None),
                                  'message': 'Waiting for this run', 'elapsed_seconds': None, 'completed': None, 'total': None,
                                  'run_id': run.get('run_id'), 'started_at': None, 'finished_at': None, 'heartbeat_at': None,
                                  'instrumented': True, 'eta': {'available': False, 'reason': 'Not started'}}
        done = sum(jobs.get(identity, {}).get('state') in ('complete', 'cached') and
                   jobs.get(identity, {}).get('run_id') == run.get('run_id') for identity in planned)
        if not planned:
            done = sum(job['state'] in ('complete', 'cached') for identity, job in jobs.items()
                       if not identity.startswith('run:'))
        # Only an explicit immutable delivery record is labeled delivered.
        deliveries = []
        for path in sorted((project / 'delivery').glob('*/manifest.json'))[-30:]:
            record = read(path)
            if record.get('release_ready') is True:
                part_id = record.get('part_id')
                master_name = f'parts/{part_id}/final.mp4'
                matches = bool(record.get('files', {}).get(master_name)) and record['files'][master_name] == self.reader.digest(project / master_name)
                deliveries.append({'revision': public_text(record.get('revision')), 'part': public_text(part_id), 'current_master': matches, 'at': record.get('exported_at')})
        delivered = bool(media and all(item['preview']['approved'] and item['master_current'] and any(
            delivery['current_master'] and delivery['part'] == item['part'] for delivery in deliveries) for item in media))
        if not selected and not attention and delivered:
            current.update(label='Delivery is available', state='idle', message='The current master has a recorded delivery package. Preview approval and voice revisions are shown below.')
        finished_at = max((item['at'] for item in deliveries if item['current_master'] and timestamp(item['at']) is not None),
                          key=timestamp, default=None) if delivered and not selected and not attention else None
        start = timestamp(source.get('copied_at_utc'))
        production_elapsed = max(0, (timestamp(finished_at) or now) - start) if start is not None else None
        from monitor_history import production_history
        events = production_history(self.reader, project, timings, media, source,
                                    [('cast', [r for r in image_requests if r.get('reference_group') == 'characters']),
                                     ('images', [r for r in image_requests if r.get('reference_group') != 'characters']), ('narration', speech_requests)])
        from monitor_cast import cast_view
        cast = cast_view(self.reader, info)
        events += cast.pop('events')
        dates = [job.get('heartbeat_at') or job.get('finished_at') or job.get('started_at') for job in jobs.values()]
        dates += [note.get('at'), source.get('copied_at_utc'), *[item.get('at') for item in events]]
        dates.extend(record.get(key) for record in [*image_requests, *speech_requests]
                     for key in ('created_at', 'started_at', 'imported_at', 'failed_at'))
        for path in [project / 'continuity/story-ledger.json', project / 'production/image-reviews.json',
                     project / 'audio/voice-plan.json', *[(project / 'parts' / part['id'] / 'shots.json') for part in part_rows]]:
            if path.is_file():
                dates.append(datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat())
        updated = max((value for value in dates if timestamp(value) is not None), key=timestamp, default=None)
        warnings = list(dict.fromkeys(self.reader.warnings))
        if jobs and not any(job.get('instrumented') for job in jobs.values()):
            warnings.append('This producer has older job records. Start/finish activity is visible; live heartbeats require the updated producer tools.')
        state = 'running' if active or coordinator else 'waiting' if external or attention else 'reported' if current['state'] == 'reported' else 'idle'
        return {'project': info, 'observed_at': datetime.fromtimestamp(now, timezone.utc).isoformat(),
                'updated_at': updated, 'state': state, 'current': current, 'jobs': [*jobs.values(), *external],
                'steps': {'done': done, 'total': len(planned) if planned else None,
                          'scope': 'selected local steps' if planned else 'recorded completed steps; full run plan unavailable'},
                'parts': part_rows, 'attention': attention, 'events': events,
                'media': media, 'cast': cast,
                'remaining_local': remaining_estimate(planned, jobs, timings, run.get('status'),
                                                     any(part['images']['done'] < part['images']['total'] for part in part_rows)),
                'run': {key: run.get(key) for key in ('profile', 'status', 'started_at', 'finished_at')},
                'since_intake_seconds': age(source.get('copied_at_utc'), now),
                'production_clock': {'started_at': source.get('copied_at_utc'), 'finished_at': finished_at,
                                     'elapsed_seconds': production_elapsed, 'scope': 'Recorded part production, including creative work and waiting'},
                'story_review_recorded': ledger.get('review_coverage', {}).get('full_read_complete') is True,
                'assets': {'images': sum(p['images']['done'] for p in part_rows), 'shots': sum(p['images']['total'] for p in part_rows),
                           'reviewed_images': sum(p['images']['reviewed'] for p in part_rows),
                           'clips': sum(p['voice']['done'] for p in part_rows),
                           'planned_clips': sum(p['voice']['total'] or 0 for p in part_rows) or None,
                           'provider_requests': len(image_requests) + len(speech_requests), 'deliveries': len(deliveries)},
                'warnings': warnings, 'read_only': True,
                'eta_note': 'Ranges cover the current operation. Creative work, provider queues and human decisions may have unknown duration.'}

    @staticmethod
    def job(identity, raw, now, live):
        state = raw.get('status', 'unknown')
        heartbeat_age = age(raw.get('heartbeat_at'), now)
        if state == 'running':
            state = 'running' if live and heartbeat_age is not None and heartbeat_age <= 15 else 'stale' if live else 'reported'
        end = timestamp(raw.get('finished_at')) if state in ('complete', 'cached', 'failed', 'interrupted') else now
        start = timestamp(raw.get('started_at'))
        elapsed = max(0, end - start) if start is not None and end is not None else None
        if state in ('complete', 'failed', 'interrupted') and finite(raw.get('elapsed_seconds')):
            elapsed = max(0, raw['elapsed_seconds'])
        done, total = raw.get('completed'), raw.get('total')
        percent = min(100, 100 * done / total) if finite(done) and finite(total) and total > 0 and done >= 0 else None
        return {'id': identity, 'label': label(identity), 'part': next((p for p in identity.split(':') if p.startswith('part_')), None),
                'state': state, 'message': public_text(raw.get('message') or label(identity)),
                'started_at': raw.get('started_at'), 'finished_at': raw.get('finished_at'), 'heartbeat_at': raw.get('heartbeat_at'),
                'heartbeat_age_seconds': heartbeat_age, 'elapsed_seconds': elapsed, 'run_id': raw.get('run_id'),
                'progress_age_seconds': age(raw.get('progress_at'), now),
                'completed': done if finite(done) else None, 'total': total if finite(total) else None,
                'unit': public_text(raw.get('unit'), 40), 'percent': percent,
                'attempt': raw.get('attempt'), 'origin': raw.get('origin', 'legacy-record'), 'instrumented': live}
