"""Verification for bug fixes, portability, runtime checks, technical sample and alignment."""
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

import test_workflow as fixtures
from studio_common import JobStore, atomic_json, atomic_text, executable, read_json, sha256_file
from test_studio import write_tone


class BugFixAndPortabilityTests(unittest.TestCase):
    setUp = fixtures.FastFixture.setUp
    authorize = fixtures.FastFixture.authorize

    def test_strict_g5_allows_non_kokoro_and_validates_kokoro_conditionally(self):
        from project_records import record_gate
        value = read_json(self.project / 'production/workflow.json')
        value['mode'] = 'strict'
        atomic_json(self.project / 'production/workflow.json', value)
        atomic_json(self.project / 'creative/intake.json', {
            'schema_version': 1, 'title': 'Strict Non-Kokoro', 'story_complete': True,
            'mode': 'single', 'duration_policy': {'flexible': True},
            'frame_format': 'landscape', 'performance': 'narration', 'language': 'en-us',
            'visual_style': 'Realistic Cinema',
        })
        atomic_json(self.project / 'audio/narrator.json', {
            'schema_version': 1, 'provider': 'inworld', 'model': 'inworld-tts-2',
            'voice': 'Dennis', 'language': 'en-us', 'speed': 1.0, 'providers': {}, 'cast': {},
        })
        source_sha = sha256_file(self.project / 'creative/original.md')
        atomic_json(self.project / 'continuity/story-ledger.json', {
            'source_sha256': source_sha, 'scenes': [{'id': 'SCENE-001'}],
            'review_coverage': {'full_read_complete': True, 'second_pass_complete': True, 'reviewed_scene_ids': ['SCENE-001']},
        })
        atomic_json(self.project / 'continuity/dependencies.json', {'review_status': 'complete'})
        entities = read_json(self.project / 'continuity/entities.json')
        entities['styles']['STYLE-001']['reference_paths'] = ['references/style/fixture.png']
        atomic_json(self.project / 'continuity/entities.json', entities)
        for gate in ('G1', 'G2', 'G3', 'G4'):
            record_gate(self.project, gate, 'r1', f'SYNTHETIC {gate}', 'unit test')
        record_gate(self.project, 'G5', 'r1', 'SYNTHETIC G5 inworld', 'unit test')
        self.assertEqual(read_json(self.project / 'approvals.json')['gates']['G5']['status'], 'approved')

        atomic_json(self.project / 'audio/narrator.json', {
            'schema_version': 1, 'provider': 'kokoro', 'voice': 'am_michael',
            'language': 'en-us', 'speed': 1.0, 'providers': {}, 'cast': {},
        })
        with self.assertRaisesRegex(ValueError, 'Kokoro|model/voice'):
            record_gate(self.project, 'G5', 'r2', 'SYNTHETIC G5 kokoro', 'unit test')

    def test_configure_preset_with_voice_references_and_settings_schema_version(self):
        import subprocess
        from workflow import load_preset, save_preset
        with tempfile.TemporaryDirectory(prefix='studio-preset-cli-') as temporary:
            root = Path(temporary).resolve()
            shutil.copytree(ROOT / 'tools', root / 'tools', ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copytree(ROOT / 'templates', root / 'templates')
            shutil.copytree(ROOT / 'presets', root / 'presets')
            for name in ('studio.json', 'requirements.lock.txt'):
                shutil.copy2(ROOT / name, root / name)
            shutil.copy2(ROOT / '.gitignore', root / '.gitignore')
            atomic_text(root / 'story.md', 'A synthetic story with an ending.\n')
            subprocess.run(['git', 'init', '-b', 'main', str(root)], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=Studio Test', '-c', 'user.email=test@example.invalid',
                            'commit', '-m', 'Base'], check=True, capture_output=True)
            def run_cli(*args):
                res = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(root / 'tools/studio.py'), *map(str, args)],
                                     cwd=root, capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(res.returncode, 0, res.stderr)
                return res
            run_cli('init', 'Preset Source', '--task', 'story', '--style', 'Realistic Cinema')
            src_proj = root / 'stories/preset-source'
            ref = src_proj / 'audio/voice-references/chatterbox-ref.wav'
            write_tone(ref, 0.5)
            narrator = read_json(src_proj / 'audio/narrator.json')
            narrator.update(provider='chatterbox', model='turbo', voice='actor',
                            providers={'chatterbox': {'reference_audio': 'audio/voice-references/chatterbox-ref.wav'}})
            atomic_json(src_proj / 'audio/narrator.json', narrator)
            self.assertEqual(read_json(src_proj / 'production/settings.json').get('schema_version'), 1)
            run_cli('preset', 'save', 'chatter', '--from-project', src_proj)
            preset_bytes = (root / 'presets/chatter.json').read_bytes()
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=Studio Test', '-c', 'user.email=test@example.invalid',
                            'commit', '-m', 'Commit source story'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), 'checkout', 'main'], check=True, capture_output=True)
            (root / 'presets/chatter.json').write_bytes(preset_bytes)
            subprocess.run(['git', '-C', str(root), 'add', 'presets/chatter.json'], check=True, capture_output=True)
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=Studio Test', '-c', 'user.email=test@example.invalid',
                            'commit', '-m', 'Save preset on main'], check=True, capture_output=True)
            run_cli('init', 'Preset Consumer', '--task', 'story', '--style', 'Realistic Cinema')
            dst_proj = root / 'stories/preset-consumer'
            run_cli('configure', dst_proj, '--preset', 'chatter')
            copied = read_json(dst_proj / 'audio/narrator.json')['providers']['chatterbox']['reference_audio']
            self.assertEqual(sha256_file(dst_proj / copied), sha256_file(ref))

    def test_minor_workflow_timeline_and_draft_mix_fixes(self):
        from build_timeline import build
        from workflow import configuration_problems, image_problems
        intake = read_json(self.project / 'creative/intake.json')
        intake['subtitles'] = 'burnin-typo'
        atomic_json(self.project / 'creative/intake.json', intake)
        self.assertTrue(any('Subtitles must be' in err for err in configuration_problems(self.project)))

        (self.part / 'images/shot_001.png').unlink()
        issues = image_problems(self.project, ['part_001'])
        self.assertTrue(any('SHOT-001' in err for err in issues))

        audio = self.part / 'audio/narration.wav'
        write_tone(audio, 1.0)
        digest = sha256_file(audio)
        atomic_json(audio.with_suffix('.chunks.json'), {'audio_sha256': digest, 'duration': 1.0})
        atomic_json(audio.with_suffix('.alignment.json'), {
            'source_sha256': digest,
            'words': [{'text': 'Hello.', 'display': 'Hello.', 'start': 0.0, 'end': 0.5, 'chunk': 0}],
            'uncertain_ranges': [], 'subtitles': [{'start': 0.0, 'end': 0.5, 'text': 'Hello.'}],
        })
        tl = read_json(self.part / 'timeline.json')
        tl.update(narration_file='audio/narration.wav', audio_cues=[{'id': 'CUE-OLD', 'asset_id': 'AUD-001', 'start': 0, 'end': 1}])
        atomic_json(self.part / 'timeline.json', tl)
        shot = dict(self.shot, narration='Hello.')
        atomic_json(self.part / 'shots.json', {'part_id': 'part_001', 'shots': [shot], 'audio_cues': []})
        built = build(self.project, 'part_001')
        self.assertEqual(built['audio_cues'], [])

    @unittest.skipUnless(executable('ffmpeg'), 'Actual FFmpeg required')
    def test_speech_only_listening_export_and_draft_mix_cache_key_and_portability(self):
        from delivery import export_part, record_playback
        from monitor_media import part_view
        from production_next import media_state
        from progress_snapshot import Reader
        from quality import record_image_review
        import studio
        from workflow import preview_inputs, record_preview
        self.authorize()
        draft = studio.run_project(self.project, profile='preview', stages=('mix', 'images', 'render', 'qa'))
        self.assertFalse(draft[0]['waiting_for'])
        self.assertTrue(read_json(self.part / 'audio/final_mix.mix-log.json')['draft_preview_pending_listening'])
        record_image_review(self.project, 'part_001', 'SHOT-001', 'passed', 'SYNTHETIC inspection', 'unit test')
        record_preview(self.project, 'part_001', 'SYNTHETIC preview listening', 'unit test', listening_reviewed=True)
        self.assertTrue((self.project / 'production/preview-listening.json').is_file())
        with patch('studio.invoke', wraps=studio.invoke) as invoke:
            studio.run_project(self.project, profile='final', stages=('mix', 'images', 'render', 'qa'))
            self.assertIn('mix_audio.py', [c.args[0] for c in invoke.call_args_list])
        self.assertFalse(read_json(self.part / 'audio/final_mix.mix-log.json')['draft_preview_pending_listening'])
        record_playback(self.project, 'part_001', 'unit test', 'SYNTHETIC playback notes', True)
        exported = export_part(self.project, 'part_001', 'r1')
        manifest = read_json(exported / 'manifest.json')
        self.assertIn('production/preview-listening.json', manifest['files'])
        self.assertTrue((exported / 'production/preview-listening.json').is_file())

        # Cross-checkout portability: moving project path must keep hashes & caches valid.
        moved = self.base / 'moved-checkout/story'
        shutil.move(str(self.project), str(moved))
        moved_part = moved / 'parts/part_001'
        preview_inputs(moved, 'part_001')
        state = media_state(moved, moved_part)
        self.assertTrue(state['preview_current'])
        self.assertTrue(state['master_current'])
        self.assertTrue(state['delivered'])
        view = part_view(Reader(), {'id': 'moved', 'path': str(moved)}, moved_part, read_json(moved_part / 'timeline.json'), [])
        self.assertTrue(view['preview']['current'])
        self.assertTrue(view['master_current'])
        from production_inputs import mix_plan
        from studio_common import configuration
        store = JobStore(moved)
        moved_tl = read_json(moved_part / 'timeline.json')
        reused = store.run('mix:part_001', [ROOT / 'tools/mix_audio.py', ROOT / 'tools/audio_check.py', ROOT / 'tools/studio_common.py',
                                            *(Path(p) for n in ('ffmpeg', 'ffprobe') if (p := executable(n)))],
                           {'profile': 'final', 'draft_preview': False, 'assets': {},
                            'plan': mix_plan(moved_tl), 'settings': configuration(moved)['mix']},
                           [moved_part / 'audio/final_mix.wav', moved_part / 'audio/final_mix.mix-log.json'],
                           lambda: (_ for _ in ()).throw(AssertionError('Should reuse portable JobStore entry')))
        self.assertTrue(reused['cached'])


class RuntimeAndAlignmentToolsTests(unittest.TestCase):
    def test_check_env_report_handles_project_provider_without_kokoro(self):
        from check_env import report
        with tempfile.TemporaryDirectory(prefix='studio-env-') as temporary:
            project = Path(temporary).resolve()
            shutil.copytree(ROOT / 'templates/story', project, dirs_exist_ok=True)
            narrator = read_json(project / 'audio/narrator.json')
            narrator.update(provider='provided', model='provided-recording', voice=None, speed=1.0)
            atomic_json(project / 'audio/narrator.json', narrator)
            status = report(project)
            self.assertEqual(status['selected_speech'][0]['provider'], 'provided')
            self.assertFalse(any('kokoro' in err.lower() for err in status['problems']))
            self.assertFalse(status['models']['kokoro-v1.0.onnx']['checksum_checked'])
            self.assertIsNone(status['models']['kokoro-v1.0.onnx']['upstream_checksum_verified'])

    @unittest.skipUnless(executable('ffmpeg'), 'Actual FFmpeg required')
    def test_align_chunk_corroboration_and_review_flags_with_mocked_decoder(self):
        from align_audio import align_chunk
        with tempfile.TemporaryDirectory(prefix='studio-align-') as temporary:
            wav = Path(temporary) / 'speech.wav'
            write_tone(wav, 1.0, rate=16000)
            segs = [
                SimpleNamespace(word='hello', start_frame=0, end_frame=1),    # 0.02s (<0.03s -> flagged)
                SimpleNamespace(word='world', start_frame=10, end_frame=49),  # 0.40s
            ]
            class FakeDecoder:
                calls = 0
                def __init__(self, **kwargs):
                    FakeDecoder.calls += 1
                    self.mode = FakeDecoder.calls
                    self.words_added = {}
                def add_word(self, word, phones): self.words_added[word] = phones
                def lookup_word(self, word): return word in ('hello', 'world') or word in self.words_added
                def set_align_text(self, text): self.aligned = text
                def start_utt(self): pass
                def process_raw(self, samples, full_utt=True): pass
                def end_utt(self): pass
                def hyp(self): return SimpleNamespace(hypstr='world')
                def seg(self): return [SimpleNamespace(word='<s>', start_frame=0, end_frame=0), *segs]

            with patch('pocketsphinx.Decoder', FakeDecoder):
                results, hyp = align_chunk(wav, 'Hello world')
                self.assertEqual(hyp, 'world')
                self.assertTrue(results[0]['requires_review'])
                self.assertIn('independent recognition differs', results[0]['reasons'])
                self.assertIn('unusual word duration', results[0]['reasons'])
                self.assertFalse(results[1]['requires_review'])
                with self.assertRaisesRegex(ValueError, 'dictionary lacks'):
                    align_chunk(wav, 'Hello unknownword')
                segs.pop()
                with self.assertRaisesRegex(ValueError, 'Forced alignment did not cover'):
                    align_chunk(wav, 'Hello world')

    @unittest.skipUnless(executable('ffmpeg'), 'Actual FFmpeg required')
    def test_technical_sample_run_creates_valid_fixture_outputs(self):
        import technical_sample
        with tempfile.TemporaryDirectory(prefix='studio-tech-') as temporary:
            runtime_root = Path(temporary).resolve()
            shutil.copytree(ROOT / 'tools', runtime_root / 'tools', ignore=shutil.ignore_patterns('__pycache__'))
            (runtime_root / 'references/style/visual-preferences/images').mkdir(parents=True)
            shutil.copy2(ROOT / 'studio.json', runtime_root / 'studio.json')
            for img in ('realistic-cinema.png', 'cel-shaded-anime.png'):
                shutil.copy2(ROOT / 'references/style/visual-preferences/images' / img,
                             runtime_root / 'references/style/visual-preferences/images' / img)

            class FakeSession:
                identity = 'fake-kokoro'
                def __init__(self, cache=None):
                    self.cache_hits = 0
                    self.generated_chunks = 0
                def render(self, text, output):
                    output = Path(output)
                    write_tone(output, 1.0)
                    self.generated_chunks += 1
                    manifest = {'duration': 1.0, 'chunks': [{'start': 0.0, 'end': 0.4}, {'start': 0.4, 'end': 1.0}]}
                    atomic_json(output.with_suffix('.chunks.json'), manifest)
                    return manifest

            def fake_align(audio):
                return {
                    'source_sha256': sha256_file(audio),
                    'words': [{'text': 'Test', 'display': 'Test', 'start': 0.0, 'end': 0.4, 'chunk': 0}],
                    'uncertain_ranges': [],
                    'subtitles': [{'start': 0.0, 'end': 0.4, 'text': 'Test'}],
                }

            with patch.object(technical_sample, 'ROOT', runtime_root), \
                 patch('studio_common.ROOT', runtime_root), \
                 patch.object(technical_sample, 'NarrationSession', FakeSession), \
                 patch.object(technical_sample, 'align_file', side_effect=fake_align):
                report = technical_sample.run()
            self.assertEqual(report['technical_errors'], [])
            demo = runtime_root / '.runtime/checks/technical-demo'
            self.assertTrue((demo / 'qa-report.json').is_file())
            self.assertTrue((demo / 'manifest.json').is_file())
            self.assertTrue((demo / 'final.mp4').is_file())


if __name__ == '__main__':
    unittest.main()
