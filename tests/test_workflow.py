"""Isolated Fast-policy fixtures; no real user's media permission or review."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from image_jobs import compile_reference, compile_request, queue_request
from quality import record_image_review
from review_pack import decision_pack, focused_audit_view, intake_view
from studio import add_part, run_project
from studio_common import atomic_json, atomic_text, executable, fingerprint, hash_session, read_json, sha256_file
from workflow import (AUDIT_AREAS, apply_preferences, authorize, delegation_status, delivery_outputs, load_preset,
                      policy, presentation, questions, record_preview, record_revision,
                      require_download, require_preview, require_stage, save_preset)
from test_studio import write_tone


class FastFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='studio-fast-fixture-')
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.assertEqual(self.base.parent, Path(tempfile.gettempdir()).resolve())
        self.project = self.base / 'story'
        shutil.copytree(ROOT / 'templates/story', self.project)
        self.part = self.project / 'parts/part_001'
        atomic_text(self.project / 'creative/original.md', 'A quiet room.\n')
        digest = sha256_file(self.project / 'creative/original.md')
        atomic_json(self.project / 'creative/source.json', {'sha256': digest})
        intake = read_json(self.project / 'creative/intake.json')
        intake.update(story_complete=True, mode='single', duration_policy={'flexible': True},
                      performance='none', visual_style='Synthetic fixture',
                      frame_format={'width': 64, 'height': 96, 'fps': 24}, subtitles=False)
        atomic_json(self.project / 'creative/intake.json', intake)
        value = policy(self.project)
        value['scope'].update(tools=['codex-imagegen'], external_upload=['codex-imagegen'],
                              budget={'limit': 1, 'currency': 'USD'})
        atomic_json(self.project / 'production/workflow.json', value)
        atomic_json(self.project / 'continuity/story-ledger.json', {
            'source_sha256': digest, 'scenes': [{'id': 'SCENE-001'}],
            'review_coverage': {'full_read_complete': True, 'focused_check_complete': True,
                'second_pass_complete': False, 'checked_story_sha256': digest,
                'reviewed_scene_ids': ['SCENE-001'], 'audit_areas_reviewed': list(AUDIT_AREAS)}})
        atomic_json(self.project / 'creative/audit-issues.json', {
            'source_sha256': digest, 'final_story_sha256': digest, 'assessment': 'Synthetic fixture review.',
            'verdict': 'Synthetic fixture only.', 'findings': []})
        atomic_json(self.project / 'continuity/dependencies.json', {'review_status': 'complete', 'events': [], 'links': []})
        from PIL import Image
        reference = self.project / 'references/style/fixture.png'
        Image.new('RGB', (64, 96), 'red').save(reference)
        registry = read_json(self.project / 'continuity/entities.json')
        registry['styles']['STYLE-001']['reference_paths'] = ['references/style/fixture.png']
        atomic_json(self.project / 'continuity/entities.json', registry)
        self.shot = {'id': 'SHOT-001', 'style_id': 'STYLE-001', 'style_revision': 'r1',
                     'character_ids': [], 'prop_ids': [], 'narration': '',
                     'story_time': 0, 'entity_states': {}, 'no_characters_reason': 'Synthetic background-only technical test frame.',
                     'visual_description': 'Synthetic red image.', 'camera_direction': 'Facing north.'}
        atomic_json(self.part / 'shots.json', {'part_id': 'part_001', 'shots': [self.shot]})
        atomic_text(self.part / 'narration.txt', '')
        (self.part / 'images').mkdir(exist_ok=True)
        shutil.copy2(reference, self.part / 'images/shot_001.png')
        atomic_json(self.part / 'timeline.json', {
            'schema_version': 2, 'part_id': 'part_001', 'width': 64, 'height': 96, 'fps': 24,
            'duration': 1, 'narration_file': None, 'audio_file': 'audio/final_mix.wav',
            'shots': [dict(self.shot, image='images/shot_001.png', start=0, end=1)],
            'subtitles': [], 'audio_cues': []})

    def authorize(self):
        return authorize(self.project, 'SYNTHETIC TEST AUTHORIZATION ONLY', 'isolated unit fixture')

    def fixture_preview(self):
        write_tone(self.part / 'audio/final_mix.wav', 1)
        atomic_text(self.part / 'preview.mp4', 'Synthetic byte-binding fixture, not a media render.')
        data = read_json(self.part / 'timeline.json')
        atomic_json(self.part / 'preview.render-log.json', {
            'presentation_fingerprint': fingerprint(presentation(data)),
            'output_sha256': sha256_file(self.part / 'preview.mp4'),
            'audio_sha256': sha256_file(self.part / data['audio_file']),
            'source_image_hashes': {str((self.part / shot['image']).resolve()): sha256_file(self.part / shot['image'])
                                    for shot in data['shots']}})

    def test_fast_grant_is_scoped_and_never_approves_six_gates(self):
        with self.assertRaisesRegex(ValueError, 'authorization is missing'):
            require_stage(self.project, 'render', ['part_001'])
        self.authorize()
        require_stage(self.project, 'render', ['part_001'])
        self.assertTrue(all(record['status'] == 'draft' for record in read_json(self.project / 'approvals.json')['gates'].values()))
        intake = read_json(self.project / 'creative/intake.json')
        intake['visual_style'] = 'Changed configuration'
        atomic_json(self.project / 'creative/intake.json', intake)
        self.assertEqual(delegation_status(self.project)[0], 'stale')
        with self.assertRaisesRegex(ValueError, 'authorization is stale'):
            require_stage(self.project, 'render', ['part_001'])

    def test_delivery_routing_single_parts_and_legacy_scope(self):
        intake = read_json(self.project / 'creative/intake.json')
        self.assertIs(intake['continuous_edition'], True)
        for mode, full_cut, expected in [
            ('single', True, ['one complete full-length video']),
            ('single', False, ['one complete full-length video']),
            ('parts', True, ['individual part videos', 'one continuous full-length video']),
            ('parts', False, ['individual part videos']),
        ]:
            with self.subTest(mode=mode, full_cut=full_cut):
                intake.update(mode=mode, continuous_edition=full_cut)
                atomic_json(self.project / 'creative/intake.json', intake)
                self.assertEqual(delivery_outputs(self.project), expected)
                intake_view(self.project)
                decision_pack(self.project)
                for name in ('creative/intake.md', 'production/review-summary.md'):
                    text = (self.project / name).read_text(encoding='utf-8')
                    for output in expected:
                        self.assertIn(output, text)
                    if len(expected) == 1:
                        self.assertNotIn('one continuous full-length video', text)
        intake.pop('continuous_edition')
        atomic_json(self.project / 'creative/intake.json', intake)
        self.assertEqual(delivery_outputs(self.project), ['individual part videos'])

    def test_full_cut_choice_is_bound_only_when_it_changes_requested_outputs(self):
        self.authorize()
        intake = read_json(self.project / 'creative/intake.json')
        intake['continuous_edition'] = False
        atomic_json(self.project / 'creative/intake.json', intake)
        self.assertEqual(delegation_status(self.project)[0], 'authorized')
        intake.update(mode='parts', continuous_edition=True)
        atomic_json(self.project / 'creative/intake.json', intake)
        self.authorize()
        intake['continuous_edition'] = False
        atomic_json(self.project / 'creative/intake.json', intake)
        self.assertEqual(delegation_status(self.project)[0], 'stale')

    def test_single_video_cannot_expand_into_parts_after_authorization(self):
        self.authorize()
        with self.assertRaisesRegex(ValueError, 'single video uses only part_001'):
            add_part(self.project, 'part_002')
        extra = self.project / 'parts/part_002'
        self.assertFalse(extra.exists())
        extra.mkdir()
        atomic_json(extra / 'part.json', {'part_id': 'part_002'})
        with self.assertRaisesRegex(ValueError, 'single video must use exactly one planned part'):
            require_stage(self.project, 'render', ['part_001'])

    def test_known_delivery_mode_is_not_asked_again_for_a_missing_duration(self):
        intake = read_json(self.project / 'creative/intake.json')
        intake['duration_policy'] = None
        for mode, target in [('single', 'the complete video'), ('parts', 'each part')]:
            with self.subTest(mode=mode):
                intake['mode'] = mode
                atomic_json(self.project / 'creative/intake.json', intake)
                pending = questions(self.project, include_authorization=False)
                self.assertEqual(len(pending), 1)
                self.assertIn(target, pending[0])
                self.assertNotIn('one video or parts', pending[0])

    def test_full_cut_preference_requires_an_actual_boolean(self):
        intake = read_json(self.project / 'creative/intake.json')
        intake.update(mode='parts', continuous_edition='false')
        atomic_json(self.project / 'creative/intake.json', intake)
        with self.assertRaisesRegex(ValueError, 'continuous_edition must be'):
            self.authorize()

    def test_existing_project_without_policy_stays_strict(self):
        (self.project / 'production/workflow.json').unlink()
        self.assertEqual(policy(self.project)['mode'], 'strict')
        with self.assertRaisesRegex(ValueError, 'approval'):
            require_stage(self.project, 'render')

    def test_agent_voice_selection_and_review_metadata_do_not_repeat_authorization(self):
        self.authorize()
        narrator = read_json(self.project / 'audio/narrator.json')
        narrator['voice'] = 'synthetic-selected-voice'
        narrator['pronunciations'] = {'synthetic': 'S IH N TH EH T IH K'}
        atomic_json(self.project / 'audio/narrator.json', narrator)
        intake = read_json(self.project / 'creative/intake.json')
        intake['unanswered_questions'] = ['Internal progress metadata only']
        intake['sound_preferences'] = 'Agent-selected within previously unconfigured sound preference'
        atomic_json(self.project / 'creative/intake.json', intake)
        source = read_json(self.project / 'creative/source.json'); source['audit_status'] = 'complete'
        atomic_json(self.project / 'creative/source.json', source)
        settings = read_json(self.project / 'production/settings.json')
        settings['image_provider']['estimated_cost_per_image'] = 0.1
        settings['jobs'] = {'timeout_seconds': 1200}
        atomic_json(self.project / 'production/settings.json', settings)
        self.assertEqual(delegation_status(self.project)[0], 'authorized')
        self.authorize()  # Selecting this concrete voice in a new configuration now binds it.
        narrator['voice'] = 'different-explicit-choice'
        atomic_json(self.project / 'audio/narrator.json', narrator)
        self.assertEqual(delegation_status(self.project)[0], 'stale')

    def test_authorization_needs_actual_decision_and_material_choices(self):
        with self.assertRaisesRegex(ValueError, 'actual user'):
            authorize(self.project, '', '')
        intake = read_json(self.project / 'creative/intake.json')
        intake['duration_policy'] = None
        atomic_json(self.project / 'creative/intake.json', intake)
        with self.assertRaisesRegex(ValueError, 'target length'):
            self.authorize()
        self.assertFalse((self.project / 'production/delegation.json').exists())

    def test_invalid_output_configuration_cannot_be_authorized(self):
        path = self.project / 'creative/intake.json'
        original = read_json(path)
        for changes in ({'mode': 'unknown'}, {'frame_format': {'width': 63, 'height': 96}},
                        {'performance': 'unknown'}, {'duration_policy': {'flexible': False}}):
            with self.subTest(changes=changes):
                atomic_json(path, dict(original, **changes))
                with self.assertRaises(ValueError):
                    self.authorize()

    def test_full_read_areas_and_focused_check_remain_real_prerequisites(self):
        self.authorize()
        path = self.project / 'continuity/story-ledger.json'
        data = read_json(path)
        data['review_coverage']['audit_areas_reviewed'].remove('knowledge')
        atomic_json(path, data)
        with self.assertRaisesRegex(ValueError, 'twelve internal'):
            require_stage(self.project, 'render', ['part_001'])

    def test_material_findings_are_reportable_but_block_dependent_production(self):
        self.authorize()
        path = self.project / 'creative/audit-issues.json'
        data = read_json(path)
        data['findings'] = [{'id': 'AUDIT-001', 'classification': 'confirmed issue', 'severity': 'HIGH',
                             'problem': 'Synthetic missing cause.', 'recommended_fix': 'Ask the actual author.'}]
        atomic_json(path, data)
        focused_audit_view(self.project)
        self.assertIn('AUDIT-001', (self.project / 'creative/audit-report.md').read_text(encoding='utf-8'))
        with self.assertRaisesRegex(ValueError, 'material story decision'):
            require_stage(self.project, 'render', ['part_001'])

    def test_revision_needs_exact_edit_scope_and_current_recheck(self):
        self.authorize()
        atomic_text(self.project / 'creative/story-revised.md', 'A quiet room!\n')
        with self.assertRaisesRegex(ValueError, 'issue-specific'):
            record_revision(self.project, 'major', 'Synthetic major change')
        record_revision(self.project, 'minor', 'Synthetic punctuation correction')
        with self.assertRaisesRegex(ValueError, 'consistency check'):
            require_stage(self.project, 'render', ['part_001'])
        digest = sha256_file(self.project / 'creative/story-revised.md')
        audit = read_json(self.project / 'creative/audit-issues.json'); audit['final_story_sha256'] = digest
        atomic_json(self.project / 'creative/audit-issues.json', audit)
        ledger = read_json(self.project / 'continuity/story-ledger.json')
        ledger['review_coverage']['checked_story_sha256'] = digest
        atomic_json(self.project / 'continuity/story-ledger.json', ledger)
        require_stage(self.project, 'render', ['part_001'])
        atomic_text(self.project / 'creative/story-revised.md', 'Another unrecorded revision.\n')
        with self.assertRaisesRegex(ValueError, 'receipt'):
            require_stage(self.project, 'render', ['part_001'])

    def test_future_parts_do_not_block_selected_part_or_its_image_request(self):
        target = self.project / 'parts/part_002'
        shutil.copytree(ROOT / 'templates/story/parts/part_001', target)
        for name in ('part.json', 'shots.json', 'timeline.json'):
            data = read_json(target / name); data['part_id'] = 'part_002'; atomic_json(target / name, data)
        atomic_json(target / 'shots.json', {'part_id': 'part_002', 'shots': [
            {'id': 'SHOT-DRAFT', 'prop_ids': ['PROP-NOT-YET-DESIGNED']} ]})
        intake = read_json(self.project / 'creative/intake.json'); intake['mode'] = 'parts'
        atomic_json(self.project / 'creative/intake.json', intake)
        self.authorize()
        require_stage(self.project, 'images', ['part_001'])
        request = compile_request(self.project, 'part_001', 'SHOT-001', 0)
        queue_request(self.project, request)
        with self.assertRaisesRegex(ValueError, 'part_002'):
            require_stage(self.project, 'images')

    def test_reference_and_final_requests_share_the_budget(self):
        self.authorize()
        reference = compile_reference(self.project, 'STYLE-001', 0.6)
        queue_request(self.project, reference)
        final = compile_request(self.project, 'part_001', 'SHOT-001', 0.6)
        with self.assertRaisesRegex(ValueError, 'Combined'):
            queue_request(self.project, final)

    def test_uploads_and_download_hosts_are_explicit(self):
        value = policy(self.project)
        value['scope']['external_upload'] = []
        value['scope']['tools'].append('https-audio')
        value['scope']['download_domains'] = ['audio.example.test']
        atomic_json(self.project / 'production/workflow.json', value)
        self.authorize()
        with self.assertRaisesRegex(ValueError, 'privacy scope'):
            compile_request(self.project, 'part_001', 'SHOT-001', 0)
        self.assertEqual(require_download(self.project, 'https://audio.example.test/a.wav'), ['audio.example.test'])
        with self.assertRaisesRegex(ValueError, 'source scope'):
            require_download(self.project, 'https://other.example.test/a.wav')

    def test_sound_redirect_cannot_escape_source_host_scope(self):
        from setup_studio import download
        from types import SimpleNamespace
        def opener(handler):
            def redirect(url, timeout):
                return handler.redirect_request(None, None, 302, '', {}, 'https://outside.example.test/a.wav')
            return SimpleNamespace(open=redirect)
        with patch('setup_studio.urllib.request.build_opener', side_effect=opener):
            with self.assertRaisesRegex(ValueError, 'redirect host'):
                download('https://audio.example.test/a.wav', self.base / 'download.wav',
                         allowed_hosts=['audio.example.test'])
        self.assertFalse((self.base / 'download.wav').exists())

    def test_preset_copies_preferences_and_exact_style_snapshot_never_permissions(self):
        self.authorize()
        source = self.project / 'references/style/fixture.png'
        atomic_json(self.project / 'references/style/manifest.json', {'status': 'draft', 'references': [{
            'snapshot_path': 'references/style/fixture.png', 'sha256': sha256_file(source)}]})
        with patch('workflow.ROOT', self.base):
            path = save_preset(self.project, 'usual')
            data = load_preset('usual')
        self.assertNotIn('decision_quote', path.read_text(encoding='utf-8'))
        self.assertNotIn('title', data['intake'])
        target = self.base / 'next'
        shutil.copytree(ROOT / 'templates/story', target)
        apply_preferences(target, data)
        self.assertFalse((target / 'production/delegation.json').exists())
        snapshot = read_json(target / 'references/style/manifest.json')['references'][0]
        self.assertEqual(sha256_file(target / snapshot['snapshot_path']), sha256_file(source))
        before = (target / 'creative/intake.json').read_bytes()
        with self.assertRaises(ValueError):
            apply_preferences(target, {'intake': {'title': 'Forbidden story data'}})
        self.assertEqual((target / 'creative/intake.json').read_bytes(), before)

    def test_preview_decision_binds_content_but_not_alignment_review_metadata(self):
        self.authorize(); self.fixture_preview()
        with self.assertRaisesRegex(ValueError, 'present the preview'):
            require_stage(self.project, 'master', ['part_001'])
        record_preview(self.project, 'part_001', 'SYNTHETIC preview acceptance', 'unit fixture')
        data = read_json(self.part / 'timeline.json')
        data['alignment'] = {'manual_checks': ['synthetic metadata only']}
        atomic_json(self.part / 'timeline.json', data)
        atomic_text(self.project / 'world/visual-bible.md', 'Updated internal documentation; actual preview is unchanged.\n')
        require_preview(self.project, 'part_001')
        with self.assertRaisesRegex(ValueError, 'image/reference inspection'):
            require_stage(self.project, 'master', ['part_001'])
        record_image_review(self.project, 'part_001', 'SHOT-001', 'passed', 'SYNTHETIC current-context record', 'unit test')
        require_stage(self.project, 'master', ['part_001'])
        atomic_text(self.part / 'preview.mp4', 'Changed synthetic output')
        with self.assertRaisesRegex(ValueError, 'bytes'):
            require_preview(self.project, 'part_001')

    def test_story_only_review_asks_no_film_questions_and_blocks_media(self):
        value = policy(self.project); value['task'] = 'story'
        atomic_json(self.project / 'production/workflow.json', value)
        self.authorize()
        self.assertEqual(questions(self.project), [])
        decision_pack(self.project)
        self.assertNotIn('| G1 |', (self.project / 'production/review-summary.md').read_text(encoding='utf-8'))
        with self.assertRaisesRegex(ValueError, 'outside its configuration'):
            require_stage(self.project, 'render', ['part_001'])

    @unittest.skipUnless(executable('ffmpeg'), 'Real FFmpeg unavailable')
    def test_real_fast_preview_master_and_export_preserve_actual_review_boundaries(self):
        from delivery import export_part, record_playback
        self.authorize()
        preview = run_project(self.project, stages=('mix', 'images', 'render', 'qa'))
        self.assertFalse(preview[0]['waiting_for'])
        blocked = run_project(self.project, profile='final', stages=('images', 'render'))
        self.assertTrue(any(action['actor'] == 'user' for action in blocked[0]['next_actions']))
        self.assertFalse((self.part / 'final.mp4').exists())
        record_image_review(self.project, 'part_001', 'SHOT-001', 'passed', 'SYNTHETIC fixture inspection record', 'unit test')
        record_preview(self.project, 'part_001', 'SYNTHETIC test preview decision', 'unit fixture')
        final = run_project(self.project, profile='final', stages=('mix', 'images', 'render', 'qa'))
        self.assertFalse(final[0]['waiting_for'])
        with self.assertRaises((ValueError, OSError)):
            export_part(self.project, 'part_001', 'test-r1')
        record_playback(self.project, 'part_001', 'synthetic fixture', 'SYNTHETIC review record only', True)
        output = export_part(self.project, 'part_001', 'test-r1')
        manifest = read_json(output / 'manifest.json')
        self.assertIn('production/delegation.json', manifest['files'])
        self.assertIn('production/preview-decisions.json', manifest['files'])
        self.assertTrue(all(record['status'] == 'draft' for record in read_json(output / 'approvals.json')['gates'].values()))


class HashSessionTests(unittest.TestCase):
    def test_digest_reuse_rechecks_metadata_and_does_not_persist_between_operations(self):
        import hashlib
        with tempfile.TemporaryDirectory(prefix='studio-hash-fixture-') as temporary:
            path = Path(temporary) / 'input'
            atomic_text(path, 'first')
            with patch('studio_common.hashlib.sha256', wraps=hashlib.sha256) as hashed:
                with hash_session():
                    first = sha256_file(path)
                    self.assertEqual(sha256_file(path), first)
                    self.assertEqual(hashed.call_count, 1)
                    atomic_text(path, 'changed bytes')
                    self.assertNotEqual(sha256_file(path), first)
                    self.assertEqual(hashed.call_count, 2)
                sha256_file(path)
                self.assertEqual(hashed.call_count, 3)


class WorkflowCommandTests(unittest.TestCase):
    def test_default_init_configuration_authorization_and_preset_reuse(self):
        with tempfile.TemporaryDirectory(prefix='studio-cli-fixture-') as temporary:
            root = Path(temporary).resolve()
            self.assertEqual(root.parent, Path(tempfile.gettempdir()).resolve())
            shutil.copytree(ROOT / 'tools', root / 'tools', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(ROOT / 'templates', root / 'templates')
            shutil.copytree(ROOT / 'presets', root / 'presets')
            for name in ('studio.json', 'requirements.lock.txt'):
                shutil.copy2(ROOT / name, root / name)
            shutil.copy2(ROOT / '.gitignore', root / '.gitignore')
            atomic_text(root / 'story.md', 'A synthetic source and its ending.\n')
            subprocess.run(['git', 'init', '-b', 'main', str(root)], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=Studio Test', '-c', 'user.email=studio-test@example.invalid',
                            'commit', '-m', 'Synthetic studio fixture'], check=True, capture_output=True)
            def command(*args):
                result = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(root / 'tools/studio.py'), *map(str, args)],
                                        cwd=root, capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(result.returncode, 0, result.stderr)
                return result
            command('init', 'First', '--task', 'story', '--style', 'Synthetic style')
            project = root / 'stories/first'
            self.assertEqual(read_json(project / 'production/workflow.json')['mode'], 'fast')
            configuration = root / 'configuration.json'
            atomic_json(configuration, {'intake': {'story_complete': True, 'visual_style': 'Saved synthetic style',
                                                  'continuous_edition': False}})
            command('configure', project, '--file', configuration)
            command('authorize', project, '--decision', 'SYNTHETIC authorization only', '--decision-reference', 'unit test')
            command('preset', 'save', 'usual', '--from-project', project)
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=Studio Test', '-c', 'user.email=studio-test@example.invalid',
                            'commit', '-m', 'Synthetic first story and shared preferences'], check=True, capture_output=True)
            command('init', 'Second', '--preset', 'usual')
            next_project = root / 'stories/second'
            intake = read_json(next_project / 'creative/intake.json')
            self.assertIsNone(intake['story_complete'])
            self.assertEqual(intake['visual_style'], 'Saved synthetic style')
            self.assertIs(intake['continuous_edition'], False)
            self.assertFalse((next_project / 'production/delegation.json').exists())
            self.assertIn('Saved synthetic style', (next_project / 'world/visual-bible.md').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
