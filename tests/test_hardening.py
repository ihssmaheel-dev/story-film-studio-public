"""Maintenance fixtures only: these tests never approve a real story or claim human inspection."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from align_audio import normalize, reviewed_alignment
from audio_assets import generated_sound, make_loop
from generate_sound import pcm_blocks
from image_jobs import compile_request, import_result, queue_request
from mix_audio import probe_duration
from project_records import GATES, approval_status, artifact_path, record_gate, require_gates, snapshot, validate_continuity
from quality import image_review_context, record_image_review
from review_pack import audit_view
from studio import run_project
from studio_common import JobStore, atomic_json, atomic_text, executable, process, read_json, require_production, sha256_file
from test_studio import StudioFixture, write_json, write_tone


class HardenedProject(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='studio-hardening-')
        self.base = Path(self.temporary.name).resolve()
        self.assertEqual(self.base.parent, Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.temporary.cleanup)
        self.project = self.base / 'fixture'
        shutil.copytree(ROOT / 'templates/story', self.project)
        workflow = read_json(self.project / 'production/workflow.json')
        workflow['mode'] = 'strict'
        atomic_json(self.project / 'production/workflow.json', workflow)
        self.part = self.project / 'parts/part_001'
        atomic_text(self.project / 'creative/original.md', 'A lamp lights a quiet room.\n')
        atomic_text(self.project / 'world/visual-bible.md', 'Test fixture: preserve the lamp at frame left.\n')
        reference = self.project / 'references/style/fixture.png'
        shutil.copy2(ROOT / 'references/style/visual-preferences/images/realistic-cinema.png', reference)
        registry = read_json(self.project / 'continuity/entities.json')
        registry['styles']['STYLE-001']['reference_paths'] = ['references/style/fixture.png']
        registry['props']['PROP-001'] = {'canonical_file': 'world/props/PROP-001.md', 'revision': 'r1',
                                        'initial_state': {'position': 'left'}, 'reference_paths': []}
        atomic_text(self.project / 'world/props/PROP-001.md', 'Lamp at frame left.\n')
        atomic_json(self.project / 'continuity/entities.json', registry)
        atomic_json(self.project / 'continuity/dependencies.json', {'events': [], 'links': [], 'review_status': 'complete'})
        self.shot = {'id': 'SHOT-001', 'style_id': 'STYLE-001', 'style_revision': 'r1', 'prop_ids': ['PROP-001'],
                     'character_ids': [], 'narration': 'A lamp lights a quiet room.', 'story_time': 0,
                     'entity_states': {'PROP-001': {'position': 'left'}},
                     'visual_description': 'A quiet room and lamp.', 'camera_direction': 'View north; lamp left.'}
        atomic_json(self.part / 'shots.json', {'shots': [self.shot], 'part_id': 'part_001'})
        atomic_text(self.part / 'narration.txt', self.shot['narration'] + '\n')
        atomic_json(self.part / 'timeline.json', {'schema_version': 2, 'part_id': 'part_001', 'width': 64, 'height': 96,
                    'fps': 24, 'duration': 1.0, 'audio_file': 'audio/final_mix.wav', 'narration_file': None,
                    'shots': [dict(self.shot, image='images/shot_001.png', start=0.0, end=1.0)],
                    'subtitles': [], 'audio_cues': []})
        auth = read_json(self.project / 'production/authorizations.json')
        auth.update(final_production_budget={'limit': 1.0, 'currency': 'USD'},
                    external_upload={'status': 'approved', 'decision_quote': 'SYNTHETIC TEST FIXTURE ONLY', 'tools': ['codex-imagegen']})
        atomic_json(self.project / 'production/authorizations.json', auth)

    def seed_fixture_gates(self):
        atomic_json(self.project / 'approvals.json', {'gates': {
            gate: {'status': 'approved', 'revision': 'test-fixture', 'decision_quote': 'SYNTHETIC TEST ONLY; no human story approval',
                   'artifacts': snapshot(self.project, gate)} for gate in GATES}, 'history': []})

    def test_missing_or_changed_approvals_block_actual_work(self):
        with self.assertRaises(ValueError):
            require_production(self.part)
        self.seed_fixture_gates()
        require_gates(self.project, GATES)
        atomic_text(self.project / 'world/visual-bible.md', 'Changed canon')
        with self.assertRaises(ValueError):
            require_gates(self.project, GATES)
        log = read_json(self.project / 'approvals.json')
        self.assertEqual(log['gates']['G3']['status'], 'stale')
        self.assertEqual(log['gates']['G4']['status'], 'stale')
        self.assertEqual(log['gates']['G1']['status'], 'approved')
        self.assertEqual(log['gates']['G5']['status'], 'approved')

    def test_artifact_additions_stale_only_dependent_gates(self):
        self.seed_fixture_gates()
        atomic_text(self.part / 'storyboard.md', 'New written shot content')
        log, changed = approval_status(self.project, refresh=True)
        self.assertEqual(set(changed), {'G4', 'G6'})
        self.assertTrue(log['history'])

    def test_changed_input_marks_only_affected_jobs_stale(self):
        self.seed_fixture_gates()
        a, b = self.base / 'a.txt', self.base / 'b.txt'
        atomic_text(a, 'a'); atomic_text(b, 'b')
        atomic_json(self.project / 'production/status.json', {'jobs': {
            'affected': {'status': 'complete', 'inputs': {str(a): sha256_file(a)}},
            'retained': {'status': 'complete', 'inputs': {str(b): sha256_file(b)}}}})
        atomic_text(a, 'changed')
        atomic_text(self.project / 'world/visual-bible.md', 'changed')
        approval_status(self.project, refresh=True)
        jobs = read_json(self.project / 'production/status.json')['jobs']
        self.assertEqual(jobs['affected']['status'], 'stale')
        self.assertEqual(jobs['retained']['status'], 'complete')
        self.assertIn('G3', jobs['retained']['approval_blocked'])

    def test_full_read_and_second_pass_required_before_g1(self):
        with self.assertRaisesRegex(ValueError, 'full-read'):
            record_gate(self.project, 'G1', 'r1', 'test fixture', 'unit test')
        with self.assertRaisesRegex(ValueError, 'actual human'):
            record_gate(self.project, 'G1', 'r1', '', '')

    def test_written_narration_mismatch_blocks_g4(self):
        self.seed_fixture_gates()
        atomic_text(self.part / 'narration.txt', 'Unapproved extra narration.')
        with self.assertRaisesRegex(ValueError, 'narration.txt'):
            record_gate(self.project, 'G4', 'fixture', 'SYNTHETIC TEST ONLY', 'unit test')

    def test_canon_is_checked_before_timeline_exists(self):
        atomic_json(self.part / 'timeline.json', {'part_id': 'part_001', 'shots': []})
        self.shot['prop_ids'] = ['PROP-999']
        atomic_json(self.part / 'shots.json', {'shots': [self.shot]})
        self.assertTrue(any('PROP-999' in error for error in validate_continuity(self.project)))

    def test_historical_state_contradiction_and_unknown_dependencies(self):
        atomic_json(self.project / 'continuity/state-ledger.json', {'changes': [
            {'id': 'EVENT-001', 'entity_id': 'PROP-001', 'story_time': 1, 'before': {'position': 'right'}, 'after': {'position': 'left'}}]})
        atomic_json(self.project / 'continuity/dependencies.json', {'links': [{'source': 'PROP-001', 'target': 'MISSING'}]})
        issues = validate_continuity(self.project)
        self.assertTrue(any('historical' in issue for issue in issues))
        self.assertTrue(any('unknown ID' in issue for issue in issues))

    def test_composite_shot_ids_allow_reuse_across_parts(self):
        target = self.project / 'parts/part_002'
        shutil.copytree(self.part, target)
        data = read_json(target / 'timeline.json'); data['part_id'] = 'part_002'
        atomic_json(target / 'timeline.json', data)
        self.assertEqual(validate_continuity(self.project), [])

    def test_paths_cannot_escape_canonical_root(self):
        with self.assertRaises(ValueError):
            artifact_path(self.project, '../outside.txt')
        with self.assertRaises(ValueError):
            artifact_path(self.project, '@studio/../outside.txt')

    def test_queue_is_idempotent_and_reserves_cumulative_budget(self):
        self.seed_fixture_gates()
        request = compile_request(self.project, 'part_001', 'SHOT-001', 0.6)
        path, record = queue_request(self.project, request)
        self.assertEqual(queue_request(self.project, request)[0], path)
        self.assertEqual(len(list(path.parent.glob('*.json'))), 1)
        second = dict(request, shot_id='SHOT-002')
        with self.assertRaisesRegex(ValueError, 'Combined'):
            queue_request(self.project, second)
        record['status'] = 'needs_attention'; atomic_json(path, record)
        with self.assertRaisesRegex(ValueError, 'unknown outcome'):
            queue_request(self.project, request)

    def test_image_privacy_decision_is_enforced(self):
        self.seed_fixture_gates()
        request = compile_request(self.project, 'part_001', 'SHOT-001', 0.0)
        auth = read_json(self.project / 'production/authorizations.json')
        auth['external_upload']['status'] = 'draft'
        atomic_json(self.project / 'production/authorizations.json', auth)
        with self.assertRaisesRegex(ValueError, 'privacy decision'):
            queue_request(self.project, request)

    def test_real_result_import_records_bytes_and_never_fabricates_metadata(self):
        self.seed_fixture_gates()
        request = compile_request(self.project, 'part_001', 'SHOT-001', 0.0)
        self.assertIn('Lamp at frame left', request['tool_request']['arguments']['prompt'])
        path, _ = queue_request(self.project, request)
        result = import_result(self.project, path,
                               ROOT / 'references/style/visual-preferences/images/realistic-cinema.png',
                               'synthetic-test-fixture')
        self.assertIsNone(result['model']); self.assertIsNone(result['actual_cost'])
        self.assertEqual(result['image_sha256'], sha256_file(self.project / result['image']))
        self.assertIn('revisions/', result['image'])
        self.assertEqual(read_json(self.part / 'timeline.json')['shots'][0]['image'],
                         (self.project / result['image']).relative_to(self.part).as_posix())
        # Same result is idempotent; different bytes cannot replace its immutable revision.
        import_result(self.project, path,
                      ROOT / 'references/style/visual-preferences/images/realistic-cinema.png',
                      'synthetic-test-fixture')
        with self.assertRaises(ValueError):
            import_result(self.project, path,
                          ROOT / 'references/style/visual-preferences/images/cel-shaded-anime.png',
                          'synthetic-test-fixture')

    def test_visual_review_tracks_canon_and_image_bytes(self):
        (self.part / 'images').mkdir(exist_ok=True)
        shutil.copy2(ROOT / 'references/style/visual-preferences/images/realistic-cinema.png',
                     self.part / 'images/shot_001.png')
        before = image_review_context(self.project, 'part_001', self.shot)
        record_image_review(self.project, 'part_001', 'SHOT-001', 'passed', 'SYNTHETIC review fixture only', 'unit test')
        review = read_json(self.project / 'production/image-reviews.json')['reviews']['part_001/SHOT-001']
        self.assertEqual(review['context'], before)
        atomic_text(self.project / 'world/props/PROP-001.md', 'Lamp moved right.')
        self.assertNotEqual(image_review_context(self.project, 'part_001', self.shot), before)

    def test_partial_audit_never_becomes_complete_report(self):
        report = self.project / 'creative/audit-report.md'
        before = report.read_bytes()
        with self.assertRaisesRegex(ValueError, 'Full source read'):
            audit_view(self.project)
        self.assertEqual(report.read_bytes(), before)

    def test_complete_audit_view_contains_every_scene_and_all_sections(self):
        source = sha256_file(self.project / 'creative/original.md')
        atomic_json(self.project / 'continuity/story-ledger.json', {'source_sha256': source,
                    'scenes': [{'id': 'SCENE-001', 'heading': 'Test room'}],
                    'review_coverage': {'full_read_complete': True, 'second_pass_complete': True, 'reviewed_scene_ids': ['SCENE-001']}})
        atomic_json(self.project / 'creative/audit-issues.json', {'source_sha256': source, 'assessment': 'Synthetic test assessment',
                    'findings': [], 'scene_reviews': {'SCENE-001': 'Synthetic scene review'}, 'global_continuity': 'Synthetic test continuity',
                    'runtime_assessment': 'Duration remains undecided in this fixture.', 'verdict': 'Synthetic test verdict'})
        audit_view(self.project)
        content = (self.project / 'creative/audit-report.md').read_text(encoding='utf-8')
        for letter in 'ABCDEFGHI':
            self.assertIn('## ' + letter + '.', content)
        self.assertIn('SCENE-001', content)
        self.assertIn('Explicit permission', content)

    def test_timeline_uses_actual_words_and_preserves_previous_on_mismatch(self):
        from build_timeline import build
        audio = self.part / 'audio/narration.wav'
        write_tone(audio, 1.4)
        timeline = read_json(self.part / 'timeline.json'); timeline['narration_file'] = 'audio/narration.wav'
        atomic_json(self.part / 'timeline.json', timeline)
        words = [{'text': word, 'display': word + ' ', 'start': index * 0.2, 'end': index * 0.2 + 0.18, 'chunk': 0}
                 for index, word in enumerate(['A', 'lamp', 'lights', 'a', 'quiet', 'room.'])]
        atomic_json(audio.with_suffix('.alignment.json'), {'source_sha256': sha256_file(audio), 'words': words,
                    'subtitles': [{'start': 0.0, 'end': 1.18, 'text': self.shot['narration']}], 'uncertain_ranges': []})
        atomic_json(audio.with_suffix('.chunks.json'), {'duration': 1.4})
        first, second = dict(self.shot, narration='A lamp lights'), dict(self.shot, id='SHOT-002', narration='a quiet room.')
        atomic_json(self.part / 'shots.json', {'shots': [first, second]})
        result = build(self.project, 'part_001')
        self.assertAlmostEqual(result['duration'], 1.7)
        self.assertAlmostEqual(result['shots'][0]['end'], 0.6)
        self.assertAlmostEqual(result['shots'][1]['start'], 0.6)
        previous = (self.part / 'timeline.json').read_bytes()
        first['narration'] = 'Unapproved different words'
        atomic_json(self.part / 'shots.json', {'shots': [first, second]})
        with self.assertRaisesRegex(ValueError, 'differs'):
            build(self.project, 'part_001')
        self.assertEqual((self.part / 'timeline.json').read_bytes(), previous)

    def test_coordinator_requires_gates_even_outside_stories(self):
        with self.assertRaisesRegex(ValueError, 'approval'):
            run_project(self.project)

    @unittest.skipUnless(executable('ffmpeg'), 'Real FFmpeg unavailable')
    def test_review_to_export_checks_exact_bytes_and_blocks_stale_review(self):
        from delivery import export_part, record_playback
        intake = read_json(self.project / 'creative/intake.json')
        intake.update(performance='none', subtitles=False)
        atomic_json(self.project / 'creative/intake.json', intake)
        (self.part / 'images').mkdir(exist_ok=True)
        shutil.copy2(ROOT / 'references/style/visual-preferences/images/realistic-cinema.png',
                     self.part / 'images/shot_001.png')
        self.seed_fixture_gates()
        preview = run_project(self.project, stages=('mix', 'images', 'render', 'qa'))
        self.assertFalse(preview[0]['waiting_for'])
        # The fixture's master must wait for an explicit image review record.
        blocked = run_project(self.project, profile='final', stages=('images', 'render'))
        self.assertTrue(blocked[0]['waiting_for'])
        self.assertFalse((self.part / 'final.mp4').exists())
        record_image_review(self.project, 'part_001', 'SHOT-001', 'passed', 'SYNTHETIC maintenance fixture only', 'unit test')
        final = run_project(self.project, profile='final', stages=('mix', 'images', 'render', 'qa'))
        self.assertFalse(final[0]['waiting_for'])
        self.assertFalse(final[0]['release_ready'])
        with self.assertRaises((ValueError, OSError)):
            export_part(self.project, 'part_001', 'test-r1')
        record_playback(self.project, 'part_001', 'synthetic test reviewer', 'SYNTHETIC fixture; no human film approval', True)
        delivery = export_part(self.project, 'part_001', 'test-r1')
        manifest = read_json(delivery / 'manifest.json')
        self.assertTrue(manifest['release_ready'])
        for relative, digest in manifest['files'].items():
            self.assertEqual(sha256_file(delivery / relative), digest)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            export_part(self.project, 'part_001', 'test-r1')
        original_mix = (self.part / 'audio/final_mix.wav').read_bytes()
        write_tone(self.part / 'audio/final_mix.wav', 1.0)
        with self.assertRaisesRegex(ValueError, 'different audio mix'):
            export_part(self.project, 'part_001', 'test-r2')
        (self.part / 'audio/final_mix.wav').write_bytes(original_mix)
        shutil.copy2(ROOT / 'references/style/visual-preferences/images/cel-shaded-anime.png',
                     self.part / 'images/shot_001.png')
        with self.assertRaisesRegex(ValueError, 'different source images|visual/reference review'):
            export_part(self.project, 'part_001', 'test-r2')


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='studio-cache-')
        self.base = Path(self.temporary.name).resolve()
        self.assertEqual(self.base.parent, Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.temporary.cleanup)
        self.source, self.output = self.base / 'source', self.base / 'output'
        atomic_text(self.source, 'input')
        self.store = JobStore(self.base)
        self.calls = 0

    def action(self):
        self.calls += 1
        atomic_text(self.output, self.source.read_text())

    def run_job(self):
        return self.store.run('fixture', [self.source], {}, [self.output], self.action)

    def test_cache_reuses_and_recovers_corrupt_outputs_and_changed_sources(self):
        self.assertFalse(self.run_job()['cached'])
        self.assertTrue(self.run_job()['cached'])
        atomic_text(self.output, 'corrupt')
        self.assertFalse(self.run_job()['cached'])
        atomic_text(self.source, 'new input')
        self.assertFalse(self.run_job()['cached'])
        self.assertEqual(self.calls, 3)
        self.assertEqual(self.output.read_text(), 'new input')

    def test_interrupted_local_job_is_rerun_and_failure_is_persisted(self):
        self.run_job()
        status = read_json(self.store.path); status['jobs']['fixture']['status'] = 'running'
        atomic_json(self.store.path, status)
        self.assertFalse(self.run_job()['cached'])
        def fail():
            raise OSError('synthetic interrupted writer')
        with self.assertRaises(OSError):
            self.store.run('failure', [self.source], {}, [self.output], fail, max_attempts=2)
        record = read_json(self.store.path)['jobs']['failure']
        self.assertEqual((record['status'], record['attempt']), ('failed', 2))
        self.assertTrue((self.base / 'production/logs/timings.jsonl').is_file())

    def test_subprocess_timeout_is_bounded(self):
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            process([sys.executable, '-c', 'import time; time.sleep(3)'], timeout=0.1)

    def test_procedural_audio_streams_bounded_blocks(self):
        blocks = list(pcm_blocks('rain', 2.4, 8000, 7, 220, -18))
        self.assertEqual(sum(map(len, blocks)), round(2.4 * 8000) * 4)
        self.assertLessEqual(max(map(len, blocks)), 8000 * 4)

    def test_generated_cache_recovers_changed_bytes(self):
        params = {'kind': 'tone', 'duration': 0.2, 'frequency': 330}
        output = generated_sound(self.base / 'sounds', params)
        digest = sha256_file(output)
        self.assertEqual(generated_sound(self.base / 'sounds', params), output)
        atomic_text(output, 'corrupt')
        self.assertEqual(sha256_file(generated_sound(self.base / 'sounds', params)), digest)

    def test_manual_alignment_checks_are_scoped_to_audio_and_engine_result(self):
        audio = self.base / 'speech.wav'
        write_tone(audio, 1)
        raw = audio.with_suffix('.alignment.json')
        atomic_json(raw, {'source_sha256': sha256_file(audio), 'words': [
            {'text': 'test', 'display': 'test', 'start': 0.0, 'end': 0.8, 'chunk': 0}], 'uncertain_ranges': [{'word_index': 0}], 'subtitles': []})
        atomic_json(audio.with_suffix('.alignment-review.json'), {'audio_sha256': sha256_file(audio),
                    'alignment_sha256': sha256_file(raw), 'reviewed_indices': [0], 'notes': 'test fixture only',
                    'corrections': [{'word_index': 0, 'start': 0.05, 'end': 0.9}]})
        result = reviewed_alignment(audio)
        self.assertTrue(result['uncertain_ranges'][0]['reviewed'])
        self.assertEqual(result['words'][0]['start'], 0.05)
        atomic_json(raw, dict(read_json(raw), changed=True))
        self.assertIn('review_warning', reviewed_alignment(audio))
        write_tone(audio, 1.1)
        with self.assertRaisesRegex(ValueError, 'current speech'):
            reviewed_alignment(audio)

    def test_numeral_alignment_requires_explicit_spoken_form(self):
        with self.assertRaises(ValueError):
            normalize('It is 12.')
        self.assertEqual(normalize('It is 12.', {'12': 'twelve'})[0], ['it', 'is', 'twelve'])


@unittest.skipUnless(executable('ffmpeg'), 'Real FFmpeg unavailable')
class MediaHardeningTests(StudioFixture):
    def test_mixed_source_sizes_preserve_first_shot_and_full_frame_count(self):
        from PIL import Image
        images = self.part / 'images'; images.mkdir()
        Image.new('RGB', (64, 96), 'red').save(images / 'shot_001.png')
        Image.new('RGB', (96, 64), 'blue').save(images / 'shot_002.png')
        self.data['shots'][0]['end'] = 1.0
        self.data['shots'].append(dict(self.data['shots'][0], id='SHOT-002', image='images/shot_002.png', start=1.0, end=3.0))
        write_json(self.timeline, self.data)
        write_tone(self.part / 'audio/final_mix.wav', 3.0)
        output = self.base / 'mixed-sizes.mp4'
        self.command(ROOT / 'tools/render_part.py', self.timeline, '--output', output)
        info = json.loads(process([executable('ffprobe'), '-v', 'error', '-show_streams', '-of', 'json', str(output)]).stdout)
        stream = next(item for item in info['streams'] if item['codec_type'] == 'video')
        self.assertAlmostEqual(float(stream['start_time']), 0.0, places=3)
        self.assertEqual(int(stream['nb_frames']), 72)
        for label, when, channel in [('first', 0.2, 0), ('second', 1.5, 2)]:
            frame = self.base / (label + '.png')
            process([executable('ffmpeg'), '-v', 'error', '-ss', str(when), '-i', str(output), '-frames:v', '1', str(frame)])
            with Image.open(frame) as decoded:
                color = decoded.getpixel((32, 48))
            self.assertGreater(color[channel], 200)

    def test_fractional_duration_survives_two_pass_normalization(self):
        self.data['duration'] = self.data['shots'][0]['end'] = self.data['audio_cues'][0]['end'] = 3.163333
        write_json(self.timeline, self.data)
        self.command(ROOT / 'tools/mix_audio.py', self.timeline)
        self.assertAlmostEqual(probe_duration(self.part / 'audio/final_mix.wav'), self.data['duration'], places=4)

    def test_repeated_cues_share_audio_input(self):
        from mix_audio import build_mix
        second = dict(self.data['audio_cues'][0], id='CUE-002', start=0.5, end=2.5)
        self.data['audio_cues'].append(second)
        write_json(self.timeline, self.data)
        command, _ = build_mix(self.timeline, executable('ffmpeg'), executable('ffprobe'))
        self.assertEqual(command.count(str(self.asset)), 1)
        graph = command[command.index('-filter_complex') + 1]
        self.assertIn('asplit=2', graph)

    def test_crossfaded_loop_has_expected_length_and_provenance(self):
        target = self.base / 'loop.wav'
        make_loop(self.asset, target, 0.1)
        self.assertAlmostEqual(probe_duration(target), 0.4, places=4)
        self.assertEqual(read_json(target.with_suffix('.loop.json'))['qa_status'], 'listening_pending')
        with self.assertRaises(ValueError):
            make_loop(self.asset, target, 0.1)

    def test_silent_film_mix_is_valid_and_never_claims_loudness(self):
        self.data.update(narration_file=None, audio_cues=[], subtitles=[])
        write_json(self.timeline, self.data)
        self.command(ROOT / 'tools/mix_audio.py', self.timeline)
        log = read_json(self.part / 'audio/final_mix.mix-log.json')
        self.assertFalse(log['normalization']['applied'])
        self.assertEqual(log['normalization']['reason'], 'deliberately silent signal')


if __name__ == '__main__':
    unittest.main()
