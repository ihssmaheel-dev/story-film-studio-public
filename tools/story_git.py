"""Create isolated story branches without committing, stashing or discarding user work."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import unicodedata


def slugify(title):
    normalized = unicodedata.normalize('NFKD', title).encode('ascii', 'ignore').decode('ascii')
    slug = re.sub(r'[^a-z0-9]+', '-', normalized.lower()).strip('-')
    if not slug:
        if not title.strip():
            raise ValueError('Story title must not be empty')
        slug = 'story-' + hashlib.sha256(title.encode('utf-8')).hexdigest()[:12]
    if slug in {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))}:
        slug = 'story-' + slug
    if len(slug) > 80:
        slug = slug[:67].rstrip('-') + '-' + hashlib.sha256(title.encode('utf-8')).hexdigest()[:12]
    return slug


def git(root, *arguments, check=True):
    try:
        result = subprocess.run(['git', '-C', str(root), *arguments], capture_output=True,
                                encoding='utf-8', errors='replace', timeout=30)
    except FileNotFoundError:
        raise ValueError('Git is required. Clone the studio repository before starting a story.') from None
    except subprocess.TimeoutExpired:
        raise ValueError('Git timed out; inspect the checkout before continuing.') from None
    if check and result.returncode:
        raise ValueError('Git: ' + (result.stderr.strip() or result.stdout.strip()))
    return result


def repository(root):
    root = Path(root).resolve()
    result = git(root, 'rev-parse', '--show-toplevel', check=False)
    if result.returncode or Path(result.stdout.strip()).resolve() != root:
        raise ValueError('Start stories in a Git clone of the studio, not an archive or a folder inside another repository.')
    if git(root, 'rev-parse', '--verify', 'HEAD', check=False).returncode:
        raise ValueError('The studio repository needs a committed base before starting a story.')
    for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply', 'sequencer', 'BISECT_LOG'):
        marker_path = Path(git(root, 'rev-parse', '--git-path', marker).stdout.strip())
        if (marker_path if marker_path.is_absolute() else root / marker_path).exists():
            raise ValueError('Finish the current Git merge/rebase/cherry-pick/revert/bisect before starting or switching stories.')
    return root


def current_branch(root):
    result = git(root, 'symbolic-ref', '--quiet', '--short', 'HEAD', check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def safe_worktree(root, source=None):
    allowed = None
    if source is not None:
        source = Path(source).resolve()
        if source.is_relative_to(root):
            allowed = source.relative_to(root).as_posix()
    fields = git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all').stdout.split('\0')
    blocked, index = [], 0
    while index < len(fields):
        record = fields[index]
        index += 1
        if not record:
            continue
        status, path = record[:2], record[3:]
        if path != allowed or any(letter in status for letter in 'DRCU'):
            blocked.append(path)
        if any(letter in status for letter in 'RC') and index < len(fields):
            blocked.append(fields[index])
            index += 1
    if blocked:
        paths = ', '.join(blocked[:8]) + (' ...' if len(blocked) > 8 else '')
        raise ValueError('Save or commit the current work before switching story branches. '
                         'The selected story source may be edited; unrelated changes are preserved: ' + paths)


def branch_available(root, branch):
    if not git(root, 'show-ref', '--verify', '--quiet', 'refs/heads/' + branch, check=False).returncode:
        raise ValueError(f'Branch {branch} already exists; resume that story or use a distinct title.')
    remote_refs = git(root, 'for-each-ref', '--format=%(refname)', 'refs/remotes/').stdout.splitlines()
    if any(ref.split('/', 3)[-1] == branch for ref in remote_refs):
        raise ValueError(f'Branch {branch} already exists on a known remote; check out that existing story instead of replacing it.')


def switch_with_source(root, source, *arguments):
    """Carry only the selected source across bases, including its intentional staged bytes."""
    source = Path(source).resolve()
    if not source.is_relative_to(root):
        git(root, 'switch', *arguments)
        return
    relative = source.relative_to(root).as_posix()
    original = source.read_bytes()
    original_mode = stat.S_IMODE(source.stat().st_mode)
    index = git(root, 'ls-files', '--stage', '-z', '--', relative).stdout
    staged = bool(git(root, 'diff', '--cached', '--name-only', '--', relative).stdout.strip())
    dirty = bool(git(root, 'status', '--porcelain=v1', '-z', '--', relative).stdout)
    # A durable, ignored source copy also survives an interrupted checkout/write.
    backup = root / '.runtime/story-init/sources' / hashlib.sha256(original).hexdigest()
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        backup.write_bytes(original)
    if backup.read_bytes() != original:
        raise ValueError('The saved story source differs from its recovery copy; Git was left untouched.')

    def restore_file():
        source.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix='.story-source-', dir=source.parent)
        temporary = Path(name)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(original)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, original_mode)
            os.replace(temporary, source)
        finally:
            temporary.unlink(missing_ok=True)

    def restore_index():
        if index:
            mode, identity, stage = index.split('\t', 1)[0].split()
            git(root, 'update-index', '--add', '--cacheinfo', mode, identity, relative)
        else:
            git(root, 'update-index', '--force-remove', '--', relative)

    if dirty:
        if git(root, 'cat-file', '-e', 'HEAD:' + relative, check=False).returncode == 0:
            git(root, 'restore', '--source=HEAD', '--staged', '--worktree', '--', relative)
        else:
            git(root, 'update-index', '--force-remove', '--', relative)
            source.unlink()
    try:
        git(root, 'switch', *arguments)
    except (ValueError, OSError):
        try:
            restore_index()
        finally:
            restore_file()
        raise
    if staged:
        restore_index()
    restore_file()


def plan_story_branch(root, slug, source, base=None):
    root = repository(root)
    if slugify(slug) != slug:
        raise ValueError('Use the safe story slug for its branch name')
    branch = 'story/' + slug
    branch_available(root, branch)
    safe_worktree(root, source)
    previous = current_branch(root)
    if base is None:
        for candidate in ('main', 'master'):
            if not git(root, 'show-ref', '--verify', '--quiet', 'refs/heads/' + candidate, check=False).returncode:
                base = candidate
                break
        if base is None:
            remote_default = git(root, 'symbolic-ref', '--quiet', '--short', 'refs/remotes/origin/HEAD', check=False)
            if remote_default.returncode == 0:
                base = remote_default.stdout.strip()
        if base is None and previous and not previous.startswith('story/'):
            base = previous
    if not base:
        raise ValueError('No studio base branch found; select the committed studio revision with --base.')
    if str(base).startswith('-') or re.match(r'^(?:refs/heads/|(?:refs/remotes/)?[^/]+/)?story/', str(base)):
        raise ValueError('Choose a studio base, not another story branch')
    commit = git(root, 'rev-parse', '--verify', '--end-of-options', str(base) + '^{commit}').stdout.strip()
    return {'schema_version': 1, 'branch': branch, 'project_path': 'stories/' + slug,
            'base_ref': str(base), 'base_commit': commit, 'previous_branch': previous,
            'previous_commit': git(root, 'rev-parse', 'HEAD').stdout.strip(),
            'source_path': str(Path(source).resolve()),
            'source_sha256': hashlib.sha256(Path(source).read_bytes()).hexdigest()}


def create_story_branch(root, plan):
    root = repository(root)
    branch_available(root, plan['branch'])
    safe_worktree(root, plan['source_path'])
    if current_branch(root) != plan['previous_branch'] or git(root, 'rev-parse', 'HEAD').stdout.strip() != plan['previous_commit']:
        raise ValueError('The checkout changed during story initialization; retry after inspecting Git status.')
    if hashlib.sha256(Path(plan['source_path']).read_bytes()).hexdigest() != plan['source_sha256']:
        raise ValueError('The story source changed during preparation; retry with its current complete text.')
    switch_with_source(root, plan['source_path'], '-c', plan['branch'], plan['base_commit'])
    return {**{key: value for key, value in plan.items() if key != 'source_path'},
            'created_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds')}


def rollback_empty_branch(root, plan):
    """Undo only our still-empty branch if publishing the prepared directory failed."""
    if current_branch(root) != plan['branch'] or git(root, 'rev-parse', 'HEAD').stdout.strip() != plan['base_commit']:
        raise ValueError('The checkout changed; the new branch was retained for inspection.')
    safe_worktree(Path(root).resolve(), plan['source_path'])
    if plan['previous_branch']:
        switch_with_source(Path(root).resolve(), plan['source_path'], plan['previous_branch'])
    else:
        switch_with_source(Path(root).resolve(), plan['source_path'], '--detach', plan['previous_commit'])
    git(root, 'update-ref', '-d', 'refs/heads/' + plan['branch'], plan['base_commit'])


def require_story_branch(project):
    project = Path(project).resolve()
    record_path = project / 'production/git.json'
    if not record_path.is_file():
        return  # Existing projects are not silently migrated.
    record = json.loads(record_path.read_text(encoding='utf-8-sig'))
    root = repository(project.parent.parent)
    expected = 'story/' + project.name
    if record.get('branch') != expected or record.get('project_path') != project.relative_to(root).as_posix():
        raise ValueError('The story Git record does not match its project path.')
    actual = current_branch(root)
    if actual != expected:
        raise ValueError(f'This story belongs to {expected}; current branch is {actual or "detached HEAD"}. '
                         f'Run studio resume stories/{project.name} before changing or producing it.')


def resume_story(root, project):
    root = repository(root)
    project = Path(project)
    project = (project if project.is_absolute() else root / project).resolve()
    if project.parent != root / 'stories' or slugify(project.name) != project.name:
        raise ValueError('Resume a story by its stories/<safe-slug> project path.')
    branch = 'story/' + project.name
    if current_branch(root) == branch:
        if not (project / 'production/git.json').is_file():
            raise ValueError('This branch has no initialized story project to resume.')
        require_story_branch(project)
        return project
    if git(root, 'show-ref', '--verify', '--quiet', 'refs/heads/' + branch, check=False).returncode:
        raise ValueError(f'Local branch {branch} is missing; fetch/check out the existing branch first.')
    # Validate the committed project before switching, even when its folder is absent here.
    result = git(root, 'show', branch + ':' + project.relative_to(root).as_posix() + '/production/git.json', check=False)
    if result.returncode or json.loads(result.stdout).get('branch') != branch:
        raise ValueError('Commit the initialized story project on its own branch before switching away.')
    safe_worktree(root)
    git(root, 'switch', branch)
    require_story_branch(project)
    return project
