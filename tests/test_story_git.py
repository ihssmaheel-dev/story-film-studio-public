"""Real temporary Git checkouts; no production branches or story approvals are created."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from story_git import (create_story_branch, current_branch, plan_story_branch, require_story_branch,
                       rollback_empty_branch, slugify, git as story_git_command)


class StoryBranchTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='studio-story-git-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / 'studio'
        self.root.mkdir()
        for directory in ('tools', 'templates', 'presets'):
            shutil.copytree(ROOT / directory, self.root / directory, ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('.gitignore', 'studio.json', 'requirements.lock.txt', 'story.md'):
            shutil.copy2(ROOT / name, self.root / name)
        self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Studio Test')
        self.git('config', 'user.email', 'studio-test@example.invalid')
        self.commit('Synthetic studio base')
        self.base_commit = self.git('rev-parse', 'HEAD').stdout.strip()

    def git(self, *arguments):
        return subprocess.run(['git', '-C', str(self.root), *arguments], check=True,
                              capture_output=True, text=True, encoding='utf-8')

    def commit(self, message):
        self.git('add', '.')
        self.git('commit', '-m', message)

    def command(self, *arguments, success=True):
        result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(self.root / 'tools/studio.py'), *map(str, arguments)],
                                cwd=self.root, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode == 0, success, result.stderr)
        return result

    def source(self, text='A synthetic beginning.\r\nThe synthetic ending.\r\n'):
        path = self.root / 'story.md'
        path.write_bytes(text.encode('utf-8'))
        return path

    def test_fresh_clone_and_paste_creates_story_branch_and_exact_source(self):
        clone = self.base / 'clone'
        subprocess.run(['git', 'clone', str(self.root), str(clone)], check=True, capture_output=True)
        self.root = clone
        source = self.source()
        original = source.read_bytes()
        result = self.command('init', 'The Last Train', '--task', 'story')
        project = self.root / 'stories/the-last-train'
        record = json.loads((project / 'production/git.json').read_text(encoding='utf-8'))
        self.assertEqual(current_branch(self.root), 'story/the-last-train')
        self.assertIn('Branch: story/the-last-train', result.stdout)
        self.assertEqual(record['base_ref'], 'main')
        self.assertEqual(record['base_commit'], self.base_commit)
        self.assertEqual(record['project_path'], 'stories/the-last-train')
        self.assertEqual((project / 'creative/original.md').read_bytes(), original)
        self.assertEqual(self.git('rev-parse', 'main').stdout.strip(), self.base_commit)
        self.assertEqual(self.git('ls-tree', '--name-only', 'main', 'stories/the-last-train').stdout.strip(), '')
        self.assertEqual(self.git('diff', '--cached', '--name-only').stdout.strip(), '')
        require_story_branch(project)

    def test_second_story_starts_from_main_and_does_not_inherit_first(self):
        self.source('First story. Its ending.\n')
        self.command('init', 'First')
        self.commit('Synthetic first story')
        self.source('Second story. Its own ending.\n')
        self.command('init', 'Second')
        self.assertEqual(current_branch(self.root), 'story/second')
        self.assertFalse((self.root / 'stories/first/creative/original.md').exists())
        self.assertEqual(self.git('rev-parse', 'HEAD').stdout.strip(), self.base_commit)
        self.assertIn('stories/first', self.git('ls-tree', '--name-only', 'story/first', 'stories/first').stdout)
        self.assertEqual((self.root / 'stories/second/creative/original.md').read_text(), 'Second story. Its own ending.\n')

    def test_new_source_and_distinct_staged_bytes_survive_different_story_bases(self):
        self.source('Committed first story.\n')
        self.command('init', 'First')
        self.commit('Synthetic first story')
        self.source('Staged second draft.\n')
        self.git('add', 'story.md')
        self.source('Working second draft. Its ending.\r\n')
        expected = (self.root / 'story.md').read_bytes()
        self.command('init', 'Second')
        self.assertEqual(self.git('show', ':story.md').stdout, 'Staged second draft.\n')
        self.assertEqual((self.root / 'story.md').read_bytes(), expected)
        self.assertEqual((self.root / 'stories/second/creative/original.md').read_bytes(), expected)

    def test_story_pasted_below_template_marker_is_accepted(self):
        template = (self.root / 'story.md').read_text(encoding='utf-8')
        self.source(template + '\nA real supplied synthetic story with its ending.\n')
        self.command('init', 'Pasted Below')
        self.assertEqual(current_branch(self.root), 'story/pasted-below')

    def test_unrelated_dirty_files_are_preserved_and_branch_is_not_created(self):
        source = self.source()
        unrelated = self.root / 'tools/check_env.py'
        unrelated.write_text('# synthetic unrelated change\n', encoding='utf-8')
        before = self.git('status', '--porcelain=v1').stdout
        result = self.command('init', 'Blocked', success=False)
        self.assertIn('unrelated changes are preserved', result.stderr)
        self.assertEqual(self.git('status', '--porcelain=v1').stdout, before)
        self.assertEqual(source.read_bytes(), b'A synthetic beginning.\r\nThe synthetic ending.\r\n')
        self.assertEqual(current_branch(self.root), 'main')
        self.assertEqual(self.git('branch', '--list', 'story/blocked').stdout.strip(), '')
        self.assertFalse((self.root / 'stories/blocked').exists())

    def test_untracked_and_staged_unrelated_work_block_switching(self):
        self.source()
        unrelated = self.root / 'notes.txt'
        unrelated.write_text('Actual user notes', encoding='utf-8')
        self.command('init', 'Untracked', success=False)
        self.git('add', 'notes.txt')
        before = self.git('diff', '--cached').stdout
        self.command('init', 'Staged', success=False)
        self.assertEqual(self.git('diff', '--cached').stdout, before)
        self.assertEqual(current_branch(self.root), 'main')

    def test_staged_story_source_is_allowed_and_index_is_preserved(self):
        self.source()
        self.git('add', 'story.md')
        before = self.git('diff', '--cached').stdout
        self.command('init', 'Staged Source')
        self.assertEqual(self.git('diff', '--cached').stdout, before)
        self.assertEqual(current_branch(self.root), 'story/staged-source')

    def test_existing_local_and_remote_branches_are_never_replaced(self):
        self.source()
        self.git('branch', 'story/existing')
        result = self.command('init', 'Existing', success=False)
        self.assertIn('already exists', result.stderr)
        self.git('update-ref', 'refs/remotes/origin/story/remote', self.base_commit)
        result = self.command('init', 'Remote', success=False)
        self.assertIn('known remote', result.stderr)
        self.assertEqual(current_branch(self.root), 'main')
        self.assertEqual(self.git('branch', '--list', 'story/remote').stdout.strip(), '')

    def test_missing_empty_and_template_sources_leave_git_unchanged(self):
        self.command('init', 'Missing', '--story-file', 'missing.txt', success=False)
        self.command('init', 'Template', success=False)
        self.source(' \n ')
        self.command('init', 'Empty', success=False)
        self.assertEqual(self.git('branch', '--list', 'story/*').stdout.strip(), '')
        self.assertEqual(current_branch(self.root), 'main')

    def test_invalid_template_fails_before_branch_switch(self):
        (self.root / 'templates/story/creative/intake.json').write_text('{', encoding='utf-8')
        self.commit('Synthetic broken template')
        self.source()
        self.command('init', 'Invalid', success=False)
        self.assertEqual(current_branch(self.root), 'main')
        self.assertEqual(self.git('branch', '--list', 'story/*').stdout.strip(), '')
        self.assertFalse((self.root / 'stories/invalid').exists())

    def test_resume_switches_to_committed_story_when_folder_is_absent(self):
        self.source()
        self.command('init', 'Return')
        self.commit('Synthetic saved story')
        self.git('switch', 'main')
        self.assertFalse((self.root / 'stories/return/production/git.json').exists())
        self.command('resume', 'stories/return')
        self.assertEqual(current_branch(self.root), 'story/return')
        self.assertTrue((self.root / 'stories/return/creative/original.md').is_file())
        self.command('resume', 'stories/return')
        self.assertEqual(current_branch(self.root), 'story/return')

    def test_resume_preserves_unrelated_edits_and_stays_on_current_branch(self):
        self.source()
        self.command('init', 'Return')
        self.commit('Synthetic saved story')
        self.git('switch', 'main')
        source = self.source('Do not lose this new story.\n')
        self.command('resume', 'stories/return', success=False)
        self.assertEqual(source.read_text(), 'Do not lose this new story.\n')
        self.assertEqual(current_branch(self.root), 'main')

    def test_wrong_branch_blocks_configuration_and_production(self):
        self.source()
        self.command('init', 'Guarded')
        project = self.root / 'stories/guarded'
        record = (project / 'production/git.json').read_bytes()
        self.commit('Synthetic saved story')
        self.git('switch', 'main')
        # Simulate a copied/stale project directory on the wrong branch.
        (project / 'production').mkdir(parents=True, exist_ok=True)
        (project / 'production/git.json').write_bytes(record)
        with self.assertRaisesRegex(ValueError, 'belongs to story/guarded'):
            require_story_branch(project)
        for command in [('configure', project, '--task', 'story'), ('run', project), ('add-part', project, 'part_002')]:
            result = self.command(*command, success=False)
            self.assertIn('belongs to story/guarded', result.stderr)
        self.assertFalse((project / 'production/workflow.json').exists())

    def test_empty_branch_rollback_restores_checkout_and_source(self):
        source = self.source()
        original = source.read_bytes()
        plan = plan_story_branch(self.root, 'rollback', source)
        create_story_branch(self.root, plan)
        rollback_empty_branch(self.root, plan)
        self.assertEqual(current_branch(self.root), 'main')
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(self.git('branch', '--list', 'story/rollback').stdout.strip(), '')

    def test_checkout_failure_restores_exact_source_and_staging(self):
        self.source('Staged source.\n')
        self.git('add', 'story.md')
        source = self.source('Working source.\r\n')
        expected = source.read_bytes()
        plan = plan_story_branch(self.root, 'failed-switch', source)
        def fail_switch(root, *arguments, **kwargs):
            if arguments[0] == 'switch':
                raise ValueError('Synthetic checkout failure')
            return story_git_command(root, *arguments, **kwargs)
        with patch('story_git.git', side_effect=fail_switch):
            with self.assertRaisesRegex(ValueError, 'Synthetic checkout failure'):
                create_story_branch(self.root, plan)
        self.assertEqual(source.read_bytes(), expected)
        self.assertEqual(self.git('show', ':story.md').stdout, 'Staged source.\n')
        self.assertEqual(current_branch(self.root), 'main')
        self.assertEqual(self.git('branch', '--list', 'story/failed-switch').stdout.strip(), '')

    def test_changed_source_and_active_git_operations_stop_before_switch(self):
        source = self.source()
        plan = plan_story_branch(self.root, 'changing', source)
        self.source('A newer source.\n')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            create_story_branch(self.root, plan)
        (self.root / '.git/MERGE_HEAD').write_text(self.base_commit + '\n', encoding='ascii')
        self.command('init', 'Merging', success=False)
        self.assertEqual(current_branch(self.root), 'main')
        self.assertEqual(self.git('branch', '--list', 'story/*').stdout.strip(), '')

    def test_safe_unicode_reserved_and_long_title_names(self):
        for title in ('नदी', 'CON', '../../A / Film: [One]', 'A' * 180):
            slug = slugify(title)
            self.assertLessEqual(len(slug), 80)
            self.assertRegex(slug, r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
            self.assertEqual(slugify(slug), slug)
        self.source()
        self.command('init', 'नदी')
        self.assertEqual(current_branch(self.root), 'story/' + slugify('नदी'))

    def test_non_clone_and_story_base_are_rejected(self):
        self.source()
        self.git('branch', 'story/previous')
        self.command('init', 'Wrong Base', '--base', 'story/previous', success=False)
        self.git('update-ref', 'refs/remotes/other/story/previous', self.base_commit)
        for base in ('other/story/previous', 'refs/remotes/other/story/previous'):
            result = self.command('init', 'Wrong Remote Base', '--base', base, success=False)
            self.assertIn('not another story branch', result.stderr)
        archive = self.base / 'archive'
        shutil.copytree(self.root, archive, ignore=shutil.ignore_patterns('.git', '.runtime'))
        self.root = archive
        result = self.command('init', 'Archive', success=False)
        self.assertIn('Git clone', result.stderr)
        self.assertFalse((self.root / 'stories/archive').exists())


if __name__ == '__main__':
    unittest.main()
