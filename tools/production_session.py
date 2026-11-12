"""One continuing production coordinator per project, including across processes."""
import contextlib
from contextvars import ContextVar
from functools import wraps
import os
from pathlib import Path

ACTIVE = ContextVar('studio_coordinators', default=frozenset())

@contextlib.contextmanager
def session_lock(project):
    project = Path(project).resolve()
    if project in ACTIVE.get():
        yield
        return
    path = project / 'production/progress/coordinator.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    # Keep the inode: unlinking a held lock permits two different lock files on POSIX.
    with path.open('a+b') as stream:
        if path.stat().st_size == 0:
            stream.write(b'\0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ValueError('Another production coordinator is active for this project; follow its progress instead') from error
        try:
            token = ACTIVE.set(ACTIVE.get() | {project})
            yield
        finally:
            ACTIVE.reset(token)
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def coordinated(function):
    @wraps(function)
    def wrapped(project, *args, **kwargs):
        with session_lock(project):
            return function(project, *args, **kwargs)
    return wrapped
