"""Small observational progress records. No approvals, retries or media mutations."""
import contextlib
from contextvars import ContextVar
import hashlib
from functools import wraps
import json
import math
import os
from pathlib import Path
import threading
import time
import uuid

from studio_common import atomic_json, read_json, record_lock, utc_now

ACTIVE = ContextVar('studio_progress', default=None)
ENV_KEY = 'STUDIO_PROGRESS_CONTEXT'
LABELS = {'cast': 'Cast sheets', 'preflight': 'Production readiness', 'story': 'Story review', 'world': 'World and cast', 'shots': 'Shot planning',
          'run': 'Checking production', 'voice_setup': 'Voice runtime setup', 'audition': 'Voice audition',
          'narration': 'Voice performance', 'alignment': 'Speech alignment', 'timeline': 'Timeline',
          'images': 'Story images', 'sound': 'Sound preparation', 'mix': 'Sound mix',
          'subtitles': 'Captions', 'render': 'Video rendering', 'qa': 'Quality checks',
          'review': 'Preview review', 'delivery': 'Delivery'}


def optional_record(path):
    try:
        value = read_json(path, {})
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def optional_write(path, value):
    try:
        atomic_json(path, value)
    except (OSError, ValueError):
        pass


def label(identity):
    fields = identity.split(':')
    result = LABELS.get(fields[0], fields[0].replace('_', ' ').title())
    if 'final' in fields:
        result = 'Master rendering' if fields[0] == 'render' else result
    elif 'preview' in fields and fields[0] == 'render':
        result = 'Preview rendering'
    return result


def location(project, identity):
    return Path(project) / 'production/progress/jobs' / (hashlib.sha256(identity.encode()).hexdigest()[:24] + '.json')


def event(project, kind, identity, message, **fields):
    path = Path(project) / 'production/progress/events.jsonl'
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {'at': utc_now(), 'kind': kind, 'job': identity, 'message': str(message)[:500], **fields}
    with record_lock(path.with_suffix('.lock')):
        with path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')


def observe(project, kind, identity, message, **fields):
    """Telemetry failures must not fail a valid production operation."""
    try:
        event(project, kind, identity, message, **fields)
    except (OSError, ValueError, TimeoutError):
        pass


def context():
    value = ACTIVE.get()
    if value:
        return value
    try:
        value = json.loads(os.environ.get(ENV_KEY, '{}'))
        if set(value) == {'project', 'job', 'token'} and isinstance(value['job'], str):
            return value
    except (ValueError, TypeError):
        pass
    return None


def child_environment():
    current = context()
    if current:
        return dict(os.environ, **{ENV_KEY: json.dumps(current)})
    return None


def advance(completed, total, unit='items', message=None, **details):
    current = context()
    if not current or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
                          for x in (completed, total)) or total <= 0 or completed < 0:
        return
    path = location(current['project'], current['job'])
    try:
        with record_lock(path.with_suffix('.lock'), timeout=1):
            record = read_json(path, {})
            if record.get('token') != current['token'] or record.get('status') != 'running':
                return
            moved = record.get('completed') != min(completed, total) or record.get('total') != total
            record.update(completed=min(completed, total), total=total, unit=unit, heartbeat_at=utc_now())
            if moved:
                record['progress_at'] = utc_now()
            if message:
                record['message'] = str(message)[:300]
            record['details'] = {key: value for key, value in details.items() if key in ('frame', 'speed', 'fps')}
            atomic_json(path, record)
    except (OSError, ValueError, TimeoutError):
        pass


class Task:
    def __init__(self, project, identity, run_id=None, interval=3, origin='local'):
        self.project, self.identity = Path(project).resolve(), identity
        self.path, self.interval = location(project, identity), interval
        self.token = uuid.uuid4().hex
        self.value = {'schema_version': 1, 'job': identity, 'label': label(identity), 'status': 'running',
                      'token': self.token, 'run_id': run_id or optional_record(self.project / 'production/progress/run.json').get('run_id'), 'pid': os.getpid(), 'origin': origin,
                      'started_at': utc_now(), 'heartbeat_at': utc_now(), 'message': label(identity),
                      'completed': None, 'total': None, 'unit': None}
        self.stop = threading.Event()

    def write(self, **fields):
        try:
            with record_lock(self.path.with_suffix('.lock'), timeout=1):
                old = read_json(self.path, {})
                if old.get('token') not in (None, self.token):
                    return
                # Child-process counters and the heartbeat thread share one record.
                self.value.update(old)
                self.value.update(fields)
                atomic_json(self.path, self.value)
        except (OSError, ValueError, TimeoutError):
            pass

    def beat(self):
        while not self.stop.wait(self.interval):
            self.write(heartbeat_at=utc_now())

    def __enter__(self):
        # A new attempt intentionally replaces a previous task of the same identity.
        try:
            atomic_json(self.path, self.value)
        except OSError:
            pass
        self.started = time.monotonic()
        self.ctx = ACTIVE.set({'project': str(self.project), 'job': self.identity, 'token': self.token})
        self.thread = threading.Thread(target=self.beat, name='studio-progress-heartbeat', daemon=True)
        self.thread.start()
        observe(self.project, 'started', self.identity, label(self.identity), run_id=self.value['run_id'])
        return self

    def __exit__(self, kind, error, traceback):
        self.stop.set()
        self.thread.join(timeout=2)
        status = 'complete' if kind is None else 'interrupted' if kind in (KeyboardInterrupt, SystemExit) else 'failed'
        self.write(status=status, finished_at=utc_now(), heartbeat_at=utc_now(),
                   elapsed_seconds=round(time.monotonic() - self.started, 3),
                   message=label(self.identity) + (' completed' if kind is None else ' interrupted' if status == 'interrupted' else ' failed'))
        observe(self.project, status, self.identity, self.value['message'], run_id=self.value['run_id'],
                elapsed_seconds=self.value.get('elapsed_seconds'))
        ACTIVE.reset(self.ctx)


@contextlib.contextmanager
def task(project, identity, **kwargs):
    with Task(project, identity, **kwargs) as value:
        yield value


def note(project, stage, state, message, completed=None, total=None, unit='items', actor='agent'):
    from story_git import require_story_branch
    project = Path(project).resolve()
    require_story_branch(project)
    if stage not in LABELS or state not in ('running', 'waiting', 'complete', 'failed') or not message.strip() or actor not in ('agent', 'user', 'provider'):
        raise ValueError('Use a known stage, running/waiting/complete/failed and an actual progress message')
    if completed is not None or total is not None:
        if (any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x)
                for x in (completed, total)) or not 0 <= completed <= total or total <= 0):
            raise ValueError('Progress counts need 0 <= completed <= total with a positive total')
    record = {'schema_version': 1, 'stage': stage, 'label': LABELS[stage], 'status': state,
              'message': message.strip()[:500], 'at': utc_now(), 'origin': 'agent-note',
              'completed': completed, 'total': total, 'unit': unit, 'actor': actor}
    atomic_json(project / 'production/progress/agent.json', record)
    observe(project, 'note', stage, record['message'], status=state)
    return record


def cache_hit(project, identity):
    try:
        now = utc_now()
        atomic_json(location(project, identity), {'job': identity, 'label': label(identity), 'status': 'cached',
                    'started_at': now, 'finished_at': now, 'heartbeat_at': now,
                    'run_id': optional_record(Path(project) / 'production/progress/run.json').get('run_id'),
                    'origin': 'local', 'message': label(identity) + ' reused from verified cache'})
        observe(project, 'cached', identity, label(identity) + ' reused from verified cache')
    except (OSError, ValueError):
        pass


def observed_run(function):
    @wraps(function)
    def wrapped(project, part_selection='all', profile='preview', stages=None, force=False):
        project = Path(project).resolve()
        if not (project / 'production').is_dir():
            return function(project, part_selection, profile, stages, force)
        selected = set(stages or ('narration', 'alignment', 'timeline', 'sound', 'mix', 'subtitles', 'images', 'render', 'qa'))
        planned = []
        for part in sorted((project / 'parts').glob('part_*')):
            if part_selection != 'all' and part.name != part_selection:
                continue
            timeline = read_json(part / 'timeline.json', {})
            manual = read_json(part / 'shots.json', {}).get('timing_mode') == 'manual'
            for stage in ('narration', 'alignment', 'timeline', 'mix', 'subtitles', 'render', 'qa'):
                if stage not in selected or (stage in ('narration', 'alignment', 'timeline') and not timeline.get('narration_file')):
                    continue
                if manual and stage in ('alignment', 'timeline'):
                    continue
                if stage == 'subtitles' and read_json(project / 'creative/intake.json', {}).get('subtitles') is False:
                    continue
                planned.append(stage + ':' + part.name + (':' + profile if stage == 'render' else ''))
        path = project / 'production/progress/run.json'
        value = {'schema_version': 1, 'run_id': uuid.uuid4().hex, 'profile': profile, 'status': 'running',
                 'started_at': utc_now(), 'planned_jobs': planned, 'part_selection': part_selection,
                 'scope': 'Selected local media steps; image generation, creative work and human review have separate readiness.'}
        optional_write(path, value)
        with Task(project, 'run:' + profile, run_id=value['run_id']):
            try:
                result = function(project, part_selection, profile, stages, force)
                value.update(status='waiting' if any(item.get('waiting_for') for item in result) else 'local_complete',
                             finished_at=utc_now())
                optional_write(path, value)
                return result
            except BaseException as error:
                value.update(status='interrupted' if isinstance(error, (KeyboardInterrupt, SystemExit)) else 'failed',
                             finished_at=utc_now(), error_type=type(error).__name__)
                optional_write(path, value)
                raise
    return wrapped
