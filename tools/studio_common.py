"""Shared local configuration, atomic records, streaming hashes and timed processes."""
import contextlib
from contextvars import ContextVar
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
_HASH_MEMO = ContextVar('studio_hash_memo', default=None)


@contextlib.contextmanager
def hash_session():
    """Reuse digests within one operation; stat each file again before every reuse."""
    token = _HASH_MEMO.set(_HASH_MEMO.get() if _HASH_MEMO.get() is not None else {})
    try:
        yield
    finally:
        _HASH_MEMO.reset(token)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def read_json(path, default=None):
    path = Path(path)
    if not path.is_file() and default is not None:
        return default
    return json.loads(path.read_text(encoding='utf-8-sig'))


def atomic_text(path, content):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', suffix='.tmp', dir=path.parent)
    temporary = Path(temporary).resolve()
    if temporary.parent != path.parent:
        raise RuntimeError('Temporary path escaped its output directory')
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path, data):
    atomic_text(path, json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def sha256_file(path, memo=None):
    memo = memo if memo is not None else _HASH_MEMO.get()
    path = Path(path).resolve()
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    if memo is not None and key in memo:
        return memo[key]
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    result = digest.hexdigest()
    if memo is not None:
        memo[key] = result
    return result


def fingerprint(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def configuration(project=None):
    config = read_json(ROOT / 'studio.json')
    if project:
        overrides = read_json(Path(project) / 'production/settings.json', {})
        for section, values in overrides.items():
            if isinstance(values, dict) and isinstance(config.get(section), dict):
                config[section].update(values)
            else:
                config[section] = values
    return config


def executable(name, explicit=None):
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return str(path.resolve())
        found = shutil.which(str(explicit))
        if found:
            return found
        raise ValueError(f'{name} executable not found: {explicit}')
    configured = configuration().get('runtime', {}).get(name)
    if configured:
        path = ROOT / configured
        if path.is_file():
            return str(path.resolve())
    return shutil.which(name)


def find_project(path):
    path = Path(path).resolve()
    for parent in (path, *path.parents):
        if (parent / 'approvals.json').is_file() or (parent / 'approvals.md').is_file():
            return parent
    # A damaged real project must not silently lose its approval requirement.
    try:
        relative = path.relative_to(ROOT / 'stories')
        if relative.parts and relative.parts[0] != 'README.md':
            return ROOT / 'stories' / relative.parts[0]
    except ValueError:
        pass
    return None


def require_production(path, stage='production', tool=None):
    project = find_project(path)
    if project:
        from workflow import part_for_path, require_stage
        require_stage(project, stage, part_for_path(project, path), tool)
    return project


def require_authorized_work(path, purpose, tool):
    project = find_project(path)
    if project:
        from workflow import part_for_path, policy, require_stage
        if policy(project)['mode'] == 'fast':
            from speech_providers import PROVIDERS
            stage = ('narration' if tool in PROVIDERS else 'sound' if tool == 'procedural-audio' else 'production') if purpose == 'final' else purpose
            require_stage(project, stage, part_for_path(project, path), tool)
            return project
    if purpose == 'final':
        return require_production(path)
    if not project:
        return None
    from project_records import require_gates
    prerequisites = ['G1', 'G2', 'G3', 'G4'] if purpose == 'audition' else ['G1', 'G2']
    require_gates(project, prerequisites)
    authorization = read_json(project / 'production/authorizations.json').get(purpose + '_work', {})
    if authorization.get('status') != 'approved' or not authorization.get('decision_quote'):
        raise ValueError(f'{purpose} tool/expense authorization is missing')
    if tool not in authorization.get('tools', []):
        raise ValueError(f'{tool} is not included in the approved {purpose} tool scope')
    return project


def process(command, timeout=900, cwd=None, progress_seconds=None):
    """Bounded subprocess execution with child cleanup on timeout and readable errors."""
    try:
        from progress_records import child_environment
        if progress_seconds:
            from progress_process import measured_process
            return measured_process(command, timeout, cwd, progress_seconds)
        result = subprocess.run(command, cwd=cwd, timeout=timeout, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', env=child_environment())
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f'Command timed out after {timeout}s: {command[0]}; child process stopped') from error
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}): {command[0]}\n{result.stderr[-6000:]}')
    return result


@contextlib.contextmanager
def record_lock(path, timeout=10):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(descriptor, str(os.getpid()).encode('ascii'))
            os.close(descriptor)
            break
        except FileExistsError:
            # Only brief record transactions hold this lock; long jobs run outside it.
            if time.time() - path.stat().st_mtime > 60:
                path.unlink(missing_ok=True)
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError(f'Record is busy: {path}')
            time.sleep(0.05)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


class JobStore:
    def __init__(self, project):
        self.project = Path(project).resolve()
        self.path = self.project / 'production/status.json'
        self.hash_memo = {}

    def update(self, identity, record):
        with record_lock(self.path.with_suffix('.lock')):
            state = read_json(self.path, {'schema_version': 3, 'parts': {}, 'jobs': {}})
            state.setdefault('jobs', {})[identity] = record
            atomic_json(self.path, state)

    def reuse(self, identity, inputs, outputs, matches):
        """Reuse a verified complete job before starting an optional heavy runtime.

        The caller checks current semantic choices; every input/output is still
        checked by bytes. No output or provider result is manufactured here.
        """
        old = read_json(self.path, {'jobs': {}}).get('jobs', {}).get(identity, {})
        parameters = old.get('parameters')
        if old.get('status') != 'complete' or parameters is None or not matches(parameters):
            return None
        if old.get('inputs') != {str(Path(path).resolve()): sha256_file(path, self.hash_memo) for path in inputs}:
            return None
        if not all(Path(path).is_file() and old.get('outputs', {}).get(str(Path(path).resolve())) == sha256_file(path)
                   for path in outputs):
            return None
        self._timing(identity, 0.0, True)
        from progress_records import cache_hit
        cache_hit(self.project, identity)
        return parameters

    def run(self, identity, inputs, parameters, outputs, action, max_attempts=None, force=False,
            refresh_cached=None):
        max_attempts = max_attempts or configuration(self.project)['jobs']['max_attempts']
        if not 1 <= max_attempts <= 10:
            raise ValueError('Local job attempts must be between 1 and 10')
        source_hashes = {str(Path(path).resolve()): sha256_file(path, self.hash_memo) for path in inputs}
        signature = fingerprint({'inputs': source_hashes, 'parameters': parameters})
        state = read_json(self.path, {'jobs': {}})
        old = state.get('jobs', {}).get(identity, {})
        outputs = [Path(path).resolve() for path in outputs]
        if not force and old.get('fingerprint') == signature and old.get('status') == 'complete':
            if all(path.is_file() and old.get('outputs', {}).get(str(path)) == sha256_file(path) for path in outputs):
                if refresh_cached:
                    refresh_cached()
                    old['outputs'] = {str(path): sha256_file(path) for path in outputs}
                    old['metadata_checked_at'] = utc_now()
                    self.update(identity, old)
                self._timing(identity, 0.0, True)
                from progress_records import cache_hit
                cache_hit(self.project, identity)
                return {'cached': True, 'outputs': old['outputs']}
        started = time.monotonic()
        record = {'fingerprint': signature, 'inputs': source_hashes, 'parameters': parameters,
                  'started_at': utc_now(), 'status': 'running', 'previous_status': old.get('status')}
        for attempt in range(1, max_attempts + 1):
            record.update(attempt=attempt, status='running')
            self.update(identity, record)
            try:
                from progress_records import Task
                with Task(self.project, identity) as progress:
                    progress.write(attempt=attempt)
                    action()
                    missing = [str(path) for path in outputs if not path.is_file()]
                    if missing:
                        raise ValueError(f'Job completed without declared outputs: {missing}')
                record.update(status='complete', finished_at=utc_now(),
                              outputs={str(path): sha256_file(path) for path in outputs})
                self.update(identity, record)
                self._timing(identity, time.monotonic() - started, False)
                return {'cached': False, 'outputs': record['outputs']}
            except Exception as error:
                record.update(status='failed', error=str(error), finished_at=utc_now())
                self.update(identity, record)
                if attempt == max_attempts:
                    self._timing(identity, time.monotonic() - started, False, str(error))
                    raise

    def _timing(self, identity, seconds, cached, error=None):
        path = self.project / 'production/logs/timings.jsonl'
        path.parent.mkdir(parents=True, exist_ok=True)
        with record_lock(path.with_suffix('.lock')):
            with path.open('a', encoding='utf-8') as output:
                output.write(json.dumps({'job': identity, 'seconds': round(seconds, 4),
                                         'cache_hit': cached, 'at': utc_now(), 'error': error}) + '\n')
