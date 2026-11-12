"""Synthetic fixtures for speed, invalidation and genuine review boundaries."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_workflow as fixtures
from test_studio import write_tone
from studio_common import atomic_json, atomic_text, executable, read_json, sha256_file
from studio import run_project
from workflow import record_preview, require_preview, require_stage


class FastExecution(unittest.TestCase):
    setUp = fixtures.FastFixture.setUp
    authorize = fixtures.FastFixture.authorize

    def sound(self, pending=False):
        source = self.project / 'audio/sfx/fixture.wav'
        write_tone(source, 1, 719)
        asset = {'file': 'sfx/fixture.wav', 'sha256': sha256_file(source), 'duration': 1,
                 'source': {'method': 'synthetic test waveform'}, 'rights_status': 'verified',
                 'rights_evidence': 'Synthetic fixture, no third-party audio.',
                 'qa_status': 'pending' if pending else 'passed',
                 'qa_notes': '' if pending else 'Synthetic mechanical fixture; no real listening claim.'}
        atomic_json(self.project / 'audio/assets.json', {'assets': {'AUD-001': asset}})
        timeline = read_json(self.part / 'timeline.json')
        timeline['audio_manifest'] = '../../audio/assets.json'
        timeline['audio_cues'] = [{'id': 'CUE-001', 'asset_id': 'AUD-001', 'role': 'sfx',
                                  'start': 0, 'end': 1, 'gain_db': -8}]
        atomic_json(self.part / 'timeline.json', timeline)
        return source

    @unittest.skipUnless(executable('ffmpeg'), 'Actual FFmpeg required')
    def test_review_metadata_reuses_mix_and_video_but_picture_change_renders(self):
        from quality import record_image_review
        import studio
        self.authorize()
        stages = ('mix', 'render', 'qa')
        run_project(self.project, stages=stages)
        video_hash = sha256_file(self.part / 'preview.mp4')
        record_preview(self.project, 'part_001', 'SYNTHETIC PREVIEW FIXTURE', 'unit test only')
        timeline = read_json(self.part / 'timeline.json')
        timeline.update(alignment={'uncertain_ranges': [], 'manual_checks': ['SYNTHETIC']}, timing_source={'review': 'metadata only'})
        atomic_json(self.part / 'timeline.json', timeline)
        settings = read_json(self.project / 'production/settings.json')
        settings['image_provider']['estimated_cost_per_image'] = 0.5
        atomic_json(self.project / 'production/settings.json', settings)
        with patch('studio.invoke', wraps=studio.invoke) as invoke:
            result = run_project(self.project, stages=stages)
            self.assertEqual(invoke.call_count, 0, 'Review metadata must not launch any media subprocess')
        self.assertEqual(sha256_file(self.part / 'preview.mp4'), video_hash)
        self.assertIsNotNone(result[0]['output'])
        require_preview(self.project, 'part_001')
        self.assertEqual(read_json(self.part / 'preview.render-log.json')['timeline_sha256'], sha256_file(self.part / 'timeline.json'))
        from PIL import Image
        Image.new('RGB', (64, 96), 'blue').save(self.part / 'images/shot_001.png')
        with patch('studio.invoke', wraps=studio.invoke) as invoke:
            run_project(self.project, stages=stages)
            self.assertEqual([call.args[0] for call in invoke.call_args_list], ['render_part.py'])
        with self.assertRaises(ValueError):
            require_preview(self.project, 'part_001')

    @unittest.skipUnless(executable('ffmpeg'), 'Actual FFmpeg required')
    def test_changed_cue_rebuilds_audio_and_picture(self):
        import studio
        self.sound()
        self.authorize()
        run_project(self.project, stages=('mix', 'render'))
        from studio_common import process
        video = self.part / 'preview.mp4'
        def picture_hash():
            return process([executable('ffmpeg'), '-v', 'error', '-i', str(video), '-map', '0:v:0',
                            '-c', 'copy', '-f', 'hash', '-hash', 'sha256', '-']).stdout
        before = picture_hash()
        data = read_json(self.part / 'timeline.json')
        data['audio_cues'][0]['gain_db'] = -12
        atomic_json(self.part / 'timeline.json', data)
        with patch('studio.invoke', wraps=studio.invoke) as invoke:
            run_project(self.project, stages=('mix', 'render'))
            self.assertEqual([call.args[0] for call in invoke.call_args_list], ['mix_audio.py', 'render_part.py'])
        self.assertEqual(read_json(self.part / 'preview.render-log.json')['mode'], 'audio_remux')
        self.assertEqual(picture_hash(), before)

    @unittest.skipUnless(executable('ffmpeg'), 'Actual FFmpeg required')
    def test_one_complete_preview_can_cover_pending_listening_without_global_auto_pass(self):
        from listening import current
        from quality import record_image_review
        from delivery import record_playback, export_part
        self.sound(pending=True)
        self.authorize()
        self.assertIsNotNone(run_project(self.project, stages=('mix', 'render'))[0]['output'])
        record_image_review(self.project, 'part_001', 'SHOT-001', 'passed', 'Synthetic red fixture only.', 'unit fixture')
        record_preview(self.project, 'part_001', 'SYNTHETIC picture-only decision', 'unit fixture')
        self.assertFalse(current(self.project, 'part_001'))
        with self.assertRaisesRegex(ValueError, 'listening'):
            require_stage(self.project, 'master', ['part_001'])
        record_preview(self.project, 'part_001', 'SYNTHETIC complete-preview listening decision', 'unit fixture', listening_reviewed=True)
        self.assertTrue(current(self.project, 'part_001'))
        self.assertEqual(read_json(self.project / 'audio/assets.json')['assets']['AUD-001']['qa_status'], 'pending')
        require_stage(self.project, 'master', ['part_001'])
        run_project(self.project, profile='final', stages=('mix', 'render', 'qa'))
        record_playback(self.project, 'part_001', 'synthetic fixture', 'Synthetic mechanical regression; no real human listening.', True)
        exported = export_part(self.project, 'part_001', 'fixture')
        self.assertTrue((exported / 'production/preview-listening.json').is_file())
        data = read_json(self.part / 'timeline.json')
        data['audio_cues'][0]['gain_db'] = -7
        atomic_json(self.part / 'timeline.json', data)
        self.assertFalse(current(self.project, 'part_001'))
        with self.assertRaises(ValueError):
            require_stage(self.project, 'master', ['part_001'])

    def test_draft_never_bypasses_rights_or_failed_sound(self):
        from listening import problems
        from mix_audio import build_mix
        self.sound(pending=True)
        registry = read_json(self.project / 'audio/assets.json')
        registry['assets']['AUD-001']['rights_status'] = 'pending'
        atomic_json(self.project / 'audio/assets.json', registry)
        self.assertIn('rights', problems(self.project, 'part_001', True)[0])
        with self.assertRaisesRegex(ValueError, 'rights'):
            build_mix(self.part / 'timeline.json', draft_preview=True)
        registry['assets']['AUD-001'].update(rights_status='verified', qa_status='failed')
        atomic_json(self.project / 'audio/assets.json', registry)
        with self.assertRaisesRegex(ValueError, 'failed'):
            build_mix(self.part / 'timeline.json', draft_preview=True)

    def test_strict_cannot_use_pending_listening_draft(self):
        from mix_audio import build_mix
        self.sound(pending=True)
        policy = read_json(self.project / 'production/workflow.json')
        policy['mode'] = 'strict'
        atomic_json(self.project / 'production/workflow.json', policy)
        with self.assertRaisesRegex(ValueError, 'Fast'):
            build_mix(self.part / 'timeline.json', draft_preview=True)

    def test_missing_cue_tail_is_found_before_render(self):
        import numpy as np
        import soundfile as sf
        from audio_check import mix_coverage_errors
        self.sound()
        sf.write(self.part / 'audio/final_mix.wav', np.zeros((48000, 2)), 48000, subtype='PCM_16')
        self.assertIn('missing', mix_coverage_errors(self.part / 'timeline.json')[0])
        self.authorize()
        from studio import invoke
        with self.assertRaisesRegex(RuntimeError, 'missing'):
            invoke('render_part.py', self.part / 'timeline.json', '--output', self.part / 'preview.mp4', '--profile', 'preview')
        self.assertFalse((self.part / 'preview.mp4').exists())

    def test_measurements_reuse_actual_bytes_and_recover_bad_cache(self):
        import media_cache
        import quality
        source = self.project / 'audio/measurement.wav'
        write_tone(source, 1.113, 977)
        with patch('media_cache.ROOT', self.base), patch('quality._audio_metrics', wraps=quality._audio_metrics) as calculate:
            first = quality.audio_metrics(source)
            self.assertEqual(quality.audio_metrics(source), first)
            self.assertEqual(calculate.call_count, 1)
            cache = next((self.base / '.runtime/cache/measurements/audio').glob('*.json'))
            atomic_text(cache, '{invalid cache')
            quality.audio_metrics(source)
            self.assertEqual(calculate.call_count, 2)
            write_tone(source, 1.113, 655)
            quality.audio_metrics(source)
            self.assertEqual(calculate.call_count, 3)

    def test_dictionary_check_catches_unknown_word_before_synthesis(self):
        from align_audio import validate_alignment_text
        turns = [{'id': 'UTT-X', 'text': 'The qzztoken moved.'}]
        with self.assertRaisesRegex(ValueError, 'UTT-X.*qzztoken'):
            validate_alignment_text(turns, {})
        validate_alignment_text(turns, {'pronunciations': {'qzztoken': 'W ER D'}})

    def test_cached_speech_does_not_start_runtime_and_damaged_clip_does(self):
        source = self.project / 'audio/actor.wav'
        write_tone(source, .4)
        profile = read_json(self.project / 'audio/narrator.json')
        profile.update(provider='provided', model=None, voice=None, providers={}, cast={})
        atomic_json(self.project / 'audio/narrator.json', profile)
        policy = read_json(self.project / 'production/workflow.json')
        policy['scope']['tools'].append('provided')
        atomic_json(self.project / 'production/workflow.json', policy)
        intake = read_json(self.project / 'creative/intake.json')
        intake.update(performance='narration', language='en-us')
        atomic_json(self.project / 'creative/intake.json', intake)
        data = read_json(self.part / 'timeline.json')
        data['narration_file'] = 'audio/narration.wav'
        data['shots'][0]['narration'] = 'A quiet room.'
        atomic_json(self.part / 'timeline.json', data)
        atomic_text(self.part / 'narration.txt', 'A quiet room.')
        atomic_json(self.part / 'shots.json', {'part_id': 'part_001', 'shots': [dict(self.shot, narration='A quiet room.')]})
        atomic_json(self.part / 'speech.json', {'utterances': [
            {'id': 'UTT-1', 'text': 'A quiet room.', 'audio_file': 'audio/actor.wav',
             'sha256': sha256_file(source), 'pause_after': 0}]})
        self.authorize()
        run_project(self.project, stages=('narration',))
        with patch('speech.SpeechSession.prepare', side_effect=AssertionError('Runtime must stay offline')):
            run_project(self.project, stages=('narration',))
        manifest = read_json(self.part / 'audio/narration.chunks.json')
        cached = self.part / 'audio' / manifest['chunks'][0]['file']
        atomic_text(cached, 'damaged')
        with patch('speech.SpeechSession.prepare', side_effect=AssertionError('Runtime preparation required')):
            with self.assertRaisesRegex(AssertionError, 'required'):
                run_project(self.project, stages=('narration',))

    def test_caption_break_preserves_childhood_home_phrase(self):
        from align_audio import subtitle_cues
        text = 'His hands began shaking. It was his childhood home.'
        words = [{'text': word, 'display': word + ' ', 'start': i * 0.4, 'end': (i + 1) * 0.4, 'chunk': 0}
                 for i, word in enumerate(text.split())]
        cues = subtitle_cues(words)
        self.assertEqual(cues[1]['text'], 'It was his childhood home.')
        self.assertEqual(cues[1]['start'], 1.6)

    def test_preflight_reports_missing_pronunciation_without_cloud_or_synthesis(self):
        from preflight import inspect
        atomic_text(self.part / 'narration.txt', 'The qzztoken moved.')
        config = {'provider': 'custom', 'model': 'fixture', 'language': 'en-us', 'options': {}}
        turns = [{'id': 'UTT-X', 'text': 'The qzztoken moved.', 'config': config}]
        with patch('speech.plan_speech', return_value=turns), patch('preflight.local_info') as network:
            report = inspect(self.project)
        self.assertFalse(report['ready'])
        self.assertIn('qzztoken', report['problems'][0])
        network.assert_not_called()

    def test_live_preflight_rejects_non_loopback_before_network(self):
        from preflight import local_info
        with patch('preflight.build_opener') as network:
            with self.assertRaisesRegex(ValueError, 'loopback'):
                local_info({'options': {'endpoint': 'https://example.com/speech'}})
            network.assert_not_called()

    def test_explicit_builtin_call_budget_preserves_unknown_cost_and_blocks_unknown_retries(self):
        from image_jobs import compile_request, compile_reference, queue_request, start_request, import_result, reserved_calls
        from provider_budget import spent_or_reserved
        from workflow import validate_policy
        self.authorize()
        with self.assertRaisesRegex(ValueError, 'price estimate'):
            compile_request(self.project, 'part_001', 'SHOT-001', None)
        value = read_json(self.project / 'production/workflow.json')
        value['scope']['builtin_images'] = {'max_calls': 2, 'unreported_cost_accepted': True}
        atomic_json(self.project / 'production/workflow.json', value)
        self.authorize()
        reference = compile_reference(self.project, 'STYLE-001', None)
        reference_path, _ = queue_request(self.project, reference)
        start_request(self.project, reference_path)
        request = compile_request(self.project, 'part_001', 'SHOT-001', None)
        with self.assertRaisesRegex(ValueError, 'outstanding'):
            queue_request(self.project, request)
        with self.assertRaisesRegex(ValueError, 'pending'):
            start_request(self.project, reference_path)
        import_result(self.project, reference_path, self.project / 'references/style/fixture.png', 'synthetic fixture')
        self.assertEqual(reserved_calls(self.project), 1)
        path, record = queue_request(self.project, request)
        self.assertIsNone(record['estimated_cost'])
        self.assertIsNone(record['actual_cost'])
        self.assertEqual(record['cost_mode'], 'unreported_builtin')
        self.assertEqual(spent_or_reserved(self.project, 'USD'), 0)
        record.update(status='failed', attempts=1)
        atomic_json(path, record)
        with self.assertRaisesRegex(ValueError, 'call cap'):
            queue_request(self.project, request)
        value['scope']['builtin_images']['max_calls'] = True
        with self.assertRaisesRegex(ValueError, 'call cap'):
            validate_policy(value)

    def test_known_image_retry_reserves_another_call_and_its_known_cost(self):
        from image_jobs import compile_request, queue_request
        from provider_budget import spent_or_reserved
        self.authorize()
        request = compile_request(self.project, 'part_001', 'SHOT-001', .3)
        path, first = queue_request(self.project, request)
        first.update(status='failed', attempts=1)
        atomic_json(path, first)
        _, retried = queue_request(self.project, request)
        self.assertEqual(retried['status'], 'pending')
        self.assertEqual(retried['reserved_calls'], 2)
        self.assertAlmostEqual(spent_or_reserved(self.project, 'USD'), .6)

    def test_known_exhaustion_allows_real_alternative_but_unknown_result_blocks_it(self):
        from image_jobs import compile_request, queue_request
        self.authorize()
        first = compile_request(self.project, 'part_001', 'SHOT-001', .1)
        path, record = queue_request(self.project, first)
        record.update(status='needs_attention', attempts=3)
        atomic_json(path, record)
        shot = dict(self.shot, visual_description='A different SYNTHETIC test view.')
        atomic_json(self.part / 'shots.json', {'part_id': 'part_001', 'shots': [shot]})
        timeline = read_json(self.part / 'timeline.json')
        timeline['shots'][0]['visual_description'] = shot['visual_description']
        atomic_json(self.part / 'timeline.json', timeline)
        changed = compile_request(self.project, 'part_001', 'SHOT-001', .1)
        with self.assertRaisesRegex(ValueError, 'outstanding'):
            queue_request(self.project, changed)
        record['outcome_known'] = True
        atomic_json(path, record)
        self.assertEqual(queue_request(self.project, changed)[1]['status'], 'pending')

    def test_speech_turn_timeline_uses_measured_boundaries_and_blackout_hold(self):
        from build_timeline import build
        audio = self.part / 'audio/narration.wav'
        write_tone(audio, 1.2)
        digest = sha256_file(audio)
        atomic_json(audio.with_suffix('.chunks.json'), {'audio_sha256': digest, 'duration': 1.2,
            'chunks': [{'id': 'UTT-1', 'text': 'A quiet', 'start': 0, 'end': 0.5},
                       {'id': 'UTT-2', 'text': 'room.', 'start': 0.7, 'end': 1.0}]})
        words = [{'text': word, 'display': word + ' ', 'start': start, 'end': end, 'chunk': chunk}
                 for word, start, end, chunk in [('A', 0, .1, 0), ('quiet', .1, .4, 0), ('room.', .7, 1., 1)]]
        atomic_json(audio.with_suffix('.alignment.json'), {'source_sha256': digest, 'words': words,
            'uncertain_ranges': [], 'subtitles': []})
        data = read_json(self.part / 'timeline.json')
        data['narration_file'] = 'audio/narration.wav'
        atomic_json(self.part / 'timeline.json', data)
        shots = [dict(self.shot, narration='A quiet'),
                 dict(self.shot, id='SHOT-002', narration='room.', start_anchor={'utterance_id': 'UTT-2'}),
                 dict(self.shot, id='SHOT-003', narration='', start_anchor={'utterance_id': 'UTT-2', 'edge': 'end'})]
        atomic_json(self.part / 'shots.json', {'part_id': 'part_001', 'timing_mode': 'speech_turns',
                    'audio_tail_seconds': .3, 'shots': shots})
        built = build(self.project, 'part_001')
        self.assertEqual([(shot['start'], shot['end']) for shot in built['shots']], [(0., .7), (.7, 1.), (1., 1.5)])
        shots[1]['start_anchor']['utterance_id'] = 'missing'
        atomic_json(self.part / 'shots.json', {'timing_mode': 'speech_turns', 'shots': shots})
        with self.assertRaisesRegex(ValueError, 'Unknown measured'):
            build(self.project, 'part_001')


if __name__ == '__main__':
    unittest.main()
