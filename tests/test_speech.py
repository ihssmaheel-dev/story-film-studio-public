"""Synthetic speech contracts only: no paid requests or claimed voice auditions."""
import base64
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import test_workflow as fixture_support
from image_jobs import compile_request, queue_request
from speech import SpeechSession, current_problems, plan_speech
from speech_providers import (NoRedirect, decode_audio, fetch_audio, http_request, ready_problems,
                              remote, validate_profile, voice_config)
from studio import run_project
from studio_common import atomic_json, atomic_text, read_json, sha256_file
from workflow import authorize, delegation_status
from provider_budget import reconcile_speech


def wav_bytes(rate=24000, frames=2400):
    import numpy as np
    import soundfile as sf
    output = io.BytesIO()
    sf.write(output, np.zeros(frames, dtype=np.float32), rate, format='WAV', subtype='PCM_16')
    return output.getvalue()


class RequestContracts(unittest.TestCase):
    def test_native_provider_payloads_keep_speaker_and_performance_separate(self):
        profile = {'provider': 'elevenlabs', 'voice': 'speaker/A', 'language': 'en-us', 'providers': {}}
        recipe = http_request(voice_config(profile), 'Come home.', 'whispering', 'x' * 120, 'y' * 120)
        self.assertIn('/text-to-dialogue?', recipe['url'])
        self.assertEqual(recipe['body']['model_id'], 'eleven_v4')
        self.assertEqual(recipe['body']['inputs'], [{'text': '[whispering] Come home.', 'voice_id': 'speaker/A'}])
        self.assertEqual(len(recipe['body']['previous_text']), 100)
        profile['model'] = 'eleven_multilingual_v2'
        self.assertIn('speaker%2FA', http_request(voice_config(profile), 'Come home.')['url'])
        with self.assertRaisesRegex(ValueError, 'does not support'):
            http_request(voice_config(profile), 'Come home.', 'whispering')
        profile.update(provider='inworld', voice='Dennis', model=None)
        recipe = http_request(voice_config(profile), 'Come home.', 'gently')
        self.assertEqual(recipe['auth'], ('Authorization', 'Basic '))
        self.assertEqual(recipe['body']['voiceId'], 'Dennis')
        self.assertEqual(recipe['base64_field'], 'audioContent')
        self.assertEqual(recipe['body']['audioConfig']['audioEncoding'], 'LINEAR16')
        with self.assertRaisesRegex(ValueError, 'UTF-16'):
            http_request(voice_config(profile), '\U0001f600' * 1001)
        profile['model'] = 'inworld-tts-2-flash'
        with self.assertRaisesRegex(ValueError, 'supported model/control'):
            http_request(voice_config(profile), 'Come home.', 'gently')
        profile['model'] = None
        profile.update(provider='cartesia', voice='voice-id')
        profile['providers'] = {'cartesia': {'api_version': '2026-08-14'}}
        recipe = http_request(voice_config(profile), 'Come home.', 'calm')
        self.assertEqual(recipe['body']['voice'], 'voice-id')
        self.assertEqual(recipe['headers']['Cartesia-Version'], '2026-08-14')
        self.assertEqual(recipe['body']['generation_config']['emotion'], 'calm')

    def test_unknown_providers_and_embedded_credentials_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown speech provider'):
            validate_profile({'provider': 'unimplemented'})
        with self.assertRaisesRegex(ValueError, 'credentials'):
            validate_profile({'provider': 'inworld', 'providers': {'inworld': {'request_extra': {'api_key': 'not-a-real-key'}}}})
        self.assertEqual(voice_config({'voice': 'am_michael'})['provider'], 'kokoro')

    def test_local_gateway_is_an_explicit_choice_not_a_cloud_fallback(self):
        profile = {'provider': 'custom-http', 'model': 'local-model', 'voice': 'voice',
                   'providers': {'custom-http': {'endpoint': 'http://127.0.0.1:8091/speech'}}}
        config = voice_config(profile)
        self.assertTrue(remote(config))  # A loopback proxy could forward to a paid service.
        profile['providers']['custom-http']['local_only'] = True
        config = voice_config(profile)
        self.assertFalse(remote(config))
        profile['providers']['custom-http']['endpoint'] = 'https://example.invalid/speech'
        self.assertTrue(any('loopback' in item for item in ready_problems(ROOT, voice_config(profile))))
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.invalid'))

    def test_credentials_are_attached_only_to_the_outgoing_request(self):
        recipe = http_request(voice_config({'provider': 'inworld', 'voice': 'Dennis'}), 'Hello.')
        class Response:
            headers = {'x-request-id': 'synthetic-request'}
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, size): return b'{"audioContent":"V0FW"}'
        class Opener:
            def open(self, request, timeout):
                self.request = request
                return Response()
        opener = Opener()
        with patch.dict('os.environ', {'INWORLD_API_KEY': 'SYNTHETIC-BASE64-CREDENTIAL'}), patch('speech_providers.build_opener', return_value=opener):
            payload, metadata = fetch_audio(recipe)
        self.assertEqual(opener.request.get_header('Authorization'), 'Basic SYNTHETIC-BASE64-CREDENTIAL')
        self.assertEqual(decode_audio(recipe, payload), b'WAV')
        self.assertNotIn('SYNTHETIC-BASE64-CREDENTIAL', json.dumps(recipe))
        self.assertEqual(metadata['provider_request_id'], 'synthetic-request')
        with patch.dict('os.environ', {'INWORLD_API_KEY': 'SYNTHETIC-SECRET'}), patch('speech_providers.build_opener') as factory:
            factory.return_value.open.side_effect = HTTPError(recipe['url'], 401, 'SYNTHETIC-SECRET', {}, None)
            with self.assertRaisesRegex(RuntimeError, 'HTTP 401') as caught:
                fetch_audio(recipe)
            self.assertNotIn('SYNTHETIC-SECRET', str(caught.exception))


class SpeechFixture(unittest.TestCase):
    def setUp(self):
        fixture_support.FastFixture.setUp(self)
        self.output = self.part / 'audio/narration.wav'
        self.profile = read_json(self.project / 'audio/narrator.json')
        self.profile.update(provider='inworld', voice='narrator-voice', model='inworld-tts-2',
                            providers={'inworld': {'price_per_1000_characters': 0.01, 'currency': 'USD'}}, cast={})
        self.text = 'Hello.'
        self.update_script()
        workflow = read_json(self.project / 'production/workflow.json')
        workflow['scope'].update(tools=['inworld', 'elevenlabs', 'cartesia', 'custom-http', 'chatterbox', 'provided', 'codex-imagegen'],
                                 external_upload=['inworld', 'elevenlabs', 'cartesia', 'custom-http', 'codex-imagegen'])
        atomic_json(self.project / 'production/workflow.json', workflow)
        intake = read_json(self.project / 'creative/intake.json')
        intake.update(performance='narration', language='en-us')
        atomic_json(self.project / 'creative/intake.json', intake)

    def update_script(self, utterances=None):
        atomic_json(self.project / 'audio/narrator.json', self.profile)
        atomic_text(self.part / 'narration.txt', self.text)
        self.shot['narration'] = self.text
        atomic_json(self.part / 'shots.json', {'part_id': 'part_001', 'shots': [self.shot]})
        timeline = read_json(self.part / 'timeline.json')
        timeline['narration_file'] = 'audio/narration.wav'
        timeline['shots'][0]['narration'] = self.text
        atomic_json(self.part / 'timeline.json', timeline)
        atomic_json(self.part / 'speech.json', {'schema_version': 1, 'utterances': utterances or []})

    def grant(self):
        return authorize(self.project, 'SYNTHETIC TEST ONLY', 'isolated speech fixture')

    def cloud_response(self, recipe, **kwargs):
        payload = wav_bytes()
        if recipe['base64_field']:
            payload = json.dumps({'audioContent': base64.b64encode(payload).decode('ascii')}).encode('utf-8')
        return payload, {'provider_request_id': 'synthetic-provider-request'}

    def render(self):
        return SpeechSession(self.project, self.profile).render(self.text, self.output, script=self.part / 'speech.json', part_id='part_001')

    def test_cloud_cast_runs_without_kokoro_and_reuses_measured_clips(self):
        self.text = 'Hello. Come home.'
        self.profile['cast'] = {'CHAR-001': {'provider': 'inworld', 'voice': 'character-voice'}}
        turns = [{'id': 'UTT-1', 'speaker': 'NARRATOR', 'text': 'Hello.', 'pause_after': 0.2},
                 {'id': 'UTT-2', 'speaker': 'CHAR-001', 'text': 'Come home.', 'direction': 'gently'}]
        self.update_script(turns)
        self.grant()
        with patch.dict('os.environ', {'INWORLD_API_KEY': 'SYNTHETIC-KEY'}), patch('speech.fetch_audio', side_effect=self.cloud_response) as fetch, patch('narration.NarrationSession', side_effect=AssertionError('No Kokoro fallback')):
            run_project(self.project, stages=['narration'])
            self.assertEqual(fetch.call_count, 2)
            voices = [call.args[0]['body']['voiceId'] for call in fetch.call_args_list]
            self.assertEqual(voices, ['narrator-voice', 'character-voice'])
            manifest = read_json(self.output.with_suffix('.chunks.json'))
            self.assertAlmostEqual(manifest['duration'], 0.4, places=5)
            self.assertEqual([item['speaker'] for item in manifest['chunks']], ['NARRATOR', 'CHAR-001'])
            self.assertEqual(manifest['alignment_status'], 'word_alignment_pending')
            run_project(self.project, stages=['narration'])
            self.assertEqual(fetch.call_count, 2)
            # Damage only a derivative clip: recover from the retained response,
            # even with no credentials, without another potentially paid request.
            clip = self.output.parent / manifest['chunks'][0]['file']
            clip.write_bytes(b'corrupted derivative')
            with patch.dict('os.environ', {}, clear=True):
                run_project(self.project, stages=['narration'])
            self.assertEqual(fetch.call_count, 2)
            self.assertEqual(sha256_file(clip), manifest['chunks'][0]['sha256'])

    def test_voice_change_reuses_other_speaker_and_rebuilds_only_changed_performance(self):
        from voice_cast import set_voice
        from speech import current_problems
        self.text = 'Hello. Come home.'
        self.profile['cast'] = {'CHAR-001': {'provider': 'inworld', 'voice': 'character-A'}}
        turns = [{'id': 'UTT-1', 'speaker': 'NARRATOR', 'text': 'Hello.'},
                 {'id': 'UTT-2', 'speaker': 'CHAR-001', 'text': 'Come home.'}]
        self.update_script(turns)
        entities = read_json(self.project / 'continuity/entities.json')
        entities['characters'] = {'CHAR-001': {'canonical_file': 'world/characters/CHAR-001.md'}}
        atomic_json(self.project / 'continuity/entities.json', entities)
        self.grant()
        with patch.dict('os.environ', {'INWORLD_API_KEY': 'SYNTHETIC-KEY'}), patch('speech.fetch_audio', side_effect=self.cloud_response) as fetch:
            original = self.render()
            self.assertEqual(fetch.call_count, 2)
            set_voice(self.project, 'CHAR-001', 'character-B', 'User prefers the gentler performance',
                      decision='SYNTHETIC: use character-B', reference='unit test')
            self.assertTrue(any('rebuild speech' in issue for issue in current_problems(self.project, [self.part])))
            self.profile = read_json(self.project / 'audio/narrator.json')
            changed = self.render()
            self.assertEqual(fetch.call_count, 3)
            self.assertEqual(changed['chunks'][0]['file'], original['chunks'][0]['file'])
            self.assertNotEqual(changed['chunks'][1]['file'], original['chunks'][1]['file'])
            self.assertEqual(fetch.call_args.args[0]['body']['voiceId'], 'character-B')
            self.assertEqual(current_problems(self.project, [self.part]), [])

    def test_other_cloud_adapters_execute_the_same_audio_contract(self):
        for provider in ('elevenlabs', 'cartesia'):
            with self.subTest(provider=provider):
                self.profile.update(provider=provider, model=None, voice='synthetic-voice',
                                    providers={provider: {'price_per_1000_characters': 0.01, 'currency': 'USD'}})
                if provider == 'cartesia':
                    self.profile['providers'][provider]['api_version'] = '2026-08-14'
                self.update_script()
                self.grant()
                key = 'ELEVENLABS_API_KEY' if provider == 'elevenlabs' else 'CARTESIA_API_KEY'
                with patch.dict('os.environ', {key: 'SYNTHETIC-KEY'}), patch('speech.fetch_audio', side_effect=self.cloud_response) as fetch:
                    result = self.render()
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(result['chunks'][0]['provider'], provider)

    def test_imported_dialogue_supports_mixed_rates_and_checks_source_hashes(self):
        self.text = 'Hello. Come home.'
        self.profile.update(provider='provided', voice=None, model=None, providers={},
                            cast={'CHAR-001': {'provider': 'provided', 'voice': 'actor-A'}})
        source = self.project / 'audio/actor.wav'
        source.write_bytes(wav_bytes(48000, 9600))
        turns = [{'id': 'UTT-1', 'speaker': 'NARRATOR', 'text': 'Hello.', 'audio_file': 'audio/actor.wav', 'sha256': sha256_file(source), 'pause_after': 0.3},
                 {'id': 'UTT-2', 'speaker': 'CHAR-001', 'text': 'Come home.', 'audio_file': 'audio/actor.wav', 'sha256': sha256_file(source)}]
        self.update_script(turns)
        self.grant()
        with patch('speech.fetch_audio', side_effect=AssertionError('No provider request')):
            result = self.render()
        self.assertAlmostEqual(result['duration'], 0.7, places=5)
        self.assertEqual(result['sample_rate'], 48000)
        source.write_bytes(wav_bytes())
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.render()

    def test_script_mismatch_or_missing_cast_stops_before_generation(self):
        self.update_script([{'id': 'UTT-1', 'text': 'Wrong words.'}])
        self.grant()
        with patch('speech.fetch_audio') as fetch, self.assertRaisesRegex(ValueError, 'match narration.txt'):
            self.render()
        fetch.assert_not_called()
        self.update_script([{'id': 'UTT-1', 'speaker': 'CHAR-001', 'text': 'Hello.'}])
        with self.assertRaisesRegex(ValueError, 'explicit cast voice'):
            self.render()

    def test_paid_calls_require_price_credentials_upload_scope_and_budget(self):
        self.profile['providers']['inworld'].pop('price_per_1000_characters')
        self.update_script()
        self.grant()
        with patch.dict('os.environ', {'INWORLD_API_KEY': 'SYNTHETIC-KEY'}), patch('speech.fetch_audio') as fetch:
            with self.assertRaisesRegex(ValueError, 'price_per_1000'):
                self.render()
        fetch.assert_not_called()
        self.profile['providers']['inworld']['price_per_1000_characters'] = 100
        self.update_script()
        self.grant()
        with patch.dict('os.environ', {}, clear=True), self.assertRaisesRegex(ValueError, 'credential'):
            self.render()
        workflow = read_json(self.project / 'production/workflow.json')
        workflow['scope']['external_upload'] = ['codex-imagegen']
        atomic_json(self.project / 'production/workflow.json', workflow)
        self.grant()
        with patch.dict('os.environ', {'INWORLD_API_KEY': 'SYNTHETIC-KEY'}), self.assertRaisesRegex(ValueError, 'upload scope'):
            self.render()

    def test_speech_and_images_share_one_budget_in_both_directions(self):
        self.profile['providers']['inworld']['price_per_1000_characters'] = 100
        self.update_script()
        self.grant()
        request = compile_request(self.project, 'part_001', 'SHOT-001', 0.6)
        path, _ = queue_request(self.project, request)
        with patch.dict('os.environ', {'INWORLD_API_KEY': 'SYNTHETIC-KEY'}), patch('speech.fetch_audio') as fetch:
            with self.assertRaisesRegex(ValueError, 'combined provider budget'):
                self.render()
        fetch.assert_not_called()
        record = read_json(path)
        record['actual_cost'] = 0  # Known zero-cost synthetic fixture, never a real invoice.
        atomic_json(path, record)
        with patch.dict('os.environ', {'INWORLD_API_KEY': 'SYNTHETIC-KEY'}), patch('speech.fetch_audio', side_effect=self.cloud_response):
            self.render()
        other = copy.deepcopy(request)
        other['estimated_cost'] = 0.7
        with self.assertRaisesRegex(ValueError, 'Combined known/reserved'):
            queue_request(self.project, other)

    def test_timeout_is_never_repeated_by_the_coordinator_retry_loop(self):
        self.grant()
        with patch.dict('os.environ', {'INWORLD_API_KEY': 'SYNTHETIC-KEY'}), patch('speech.fetch_audio', side_effect=RuntimeError('Synthetic uncertain provider outcome')) as fetch:
            with self.assertRaisesRegex(ValueError, 'unresolved'):
                run_project(self.project, stages=['narration'])
            self.assertEqual(fetch.call_count, 1)
            with self.assertRaisesRegex(ValueError, 'unresolved'):
                run_project(self.project, stages=['narration'])
            self.assertEqual(fetch.call_count, 1)
        records = list((self.project / 'production/speech-jobs').glob('*.json'))
        self.assertEqual(len(records), 1)
        self.assertEqual(read_json(records[0])['status'], 'needs_attention')

    def test_delegated_cast_progress_does_not_reauthorize_but_explicit_choices_stay_bound(self):
        self.grant()
        self.profile['cast'] = {'CHAR-001': {'provider': 'inworld', 'voice': 'chosen-within-scope'}}
        self.update_script()
        self.assertEqual(delegation_status(self.project)[0], 'authorized')
        self.grant()
        self.profile['cast']['CHAR-001']['voice'] = 'different-explicit-voice'
        self.update_script()
        self.assertEqual(delegation_status(self.project)[0], 'stale')

    def test_changed_provider_or_voice_cannot_release_old_audio(self):
        self.grant()
        with patch.dict('os.environ', {'INWORLD_API_KEY': 'SYNTHETIC-KEY'}), patch('speech.fetch_audio', side_effect=self.cloud_response):
            self.render()
        self.assertEqual(current_problems(self.project, [self.part]), [])
        self.profile['voice'] = 'a-different-voice'
        self.update_script()
        self.assertTrue(any('rebuild speech' in item for item in current_problems(self.project, [self.part])))

    def test_recovered_provider_audio_resumes_without_a_second_request(self):
        self.grant()
        with patch.dict('os.environ', {'INWORLD_API_KEY': 'SYNTHETIC-KEY'}), patch('speech.fetch_audio', side_effect=RuntimeError('Synthetic uncertain outcome')):
            with self.assertRaises(RuntimeError):
                self.render()
        request = next((self.project / 'production/speech-jobs').glob('*.json'))
        recovered = self.project / 'audio/recovered.wav'
        recovered.write_bytes(wav_bytes())
        reconcile_speech(self.project, request.stem, 'received', 0.001, 'SYNTHETIC provider history evidence only', recovered)
        with patch.dict('os.environ', {}, clear=True), patch('speech.fetch_audio', side_effect=AssertionError('No second paid request')):
            result = self.render()
        self.assertAlmostEqual(result['duration'], 0.1, places=5)
        self.assertEqual(read_json(request)['actual_cost'], 0.001)

    def test_known_failure_retry_keeps_prior_charges_and_unknown_retake_is_blocked(self):
        turn = {'id': 'UTT-1', 'text': self.text}
        self.update_script([turn])
        self.grant()
        with patch.dict('os.environ', {'INWORLD_API_KEY': 'SYNTHETIC-KEY'}), patch('speech.fetch_audio', side_effect=RuntimeError('Synthetic uncertain outcome')):
            with self.assertRaises(RuntimeError):
                self.render()
        request = next((self.project / 'production/speech-jobs').glob('*.json'))
        self.update_script([dict(turn, take=2)])
        with patch.dict('os.environ', {'INWORLD_API_KEY': 'SYNTHETIC-KEY'}), patch('speech.fetch_audio') as fetch:
            with self.assertRaisesRegex(ValueError, 'unresolved provider outcome'):
                self.render()
        fetch.assert_not_called()
        reconcile_speech(self.project, request.stem, 'failed', 0.001, 'SYNTHETIC known failure and billing evidence only')
        self.update_script([turn])
        with patch.dict('os.environ', {'INWORLD_API_KEY': 'SYNTHETIC-KEY'}), patch('speech.fetch_audio', side_effect=self.cloud_response) as fetch:
            self.render()
        self.assertEqual(fetch.call_count, 1)
        record = read_json(request)
        self.assertEqual(record['status'], 'received')
        self.assertEqual(record['history'][0]['actual_cost'], 0.001)

    def test_non_english_default_alignment_stops_before_a_cloud_request(self):
        self.profile['language'] = 'es-ES'
        self.update_script()
        self.grant()
        with patch('speech.fetch_audio') as fetch, self.assertRaisesRegex(ValueError, 'automatic aligner is English'):
            run_project(self.project, stages=['narration', 'alignment'])
        fetch.assert_not_called()

    def test_explicit_local_gateway_uses_zero_cost_without_cloud_credentials(self):
        self.profile.update(provider='custom-http', model='local-model', providers={'custom-http': {
            'endpoint': 'http://127.0.0.1:8091/speech', 'local_only': True}})
        self.update_script()
        workflow = read_json(self.project / 'production/workflow.json')
        workflow['scope']['external_upload'] = []
        workflow['scope']['budget']['limit'] = 0
        atomic_json(self.project / 'production/workflow.json', workflow)
        self.grant()
        with patch.dict('os.environ', {}, clear=True), patch('speech.fetch_audio', side_effect=self.cloud_response) as fetch:
            result = self.render()
        self.assertEqual(fetch.call_count, 1)
        self.assertAlmostEqual(result['duration'], 0.1, places=5)
        record = read_json(next((self.project / 'production/speech-jobs').glob('*.json')))
        self.assertEqual(record['estimated_cost'], 0)

    def test_legacy_kokoro_command_cannot_override_another_selected_provider(self):
        import tts_kokoro
        workflow = read_json(self.project / 'production/workflow.json')
        workflow['scope']['tools'].append('kokoro')
        atomic_json(self.project / 'production/workflow.json', workflow)
        self.grant()
        args = ['tts_kokoro.py', '--text', self.text, '--output', str(self.output)]
        with patch.object(sys, 'argv', args), patch('tts_kokoro.NarrationSession') as engine, self.assertRaises(SystemExit):
            tts_kokoro.main()
        engine.assert_not_called()

    def test_delegated_custom_gateway_does_not_add_an_unapproved_external_endpoint(self):
        self.grant()
        self.profile.update(provider='custom-http', model='gateway-model', providers={'custom-http': {
            'endpoint': 'https://example.invalid/speech', 'price_per_1000_characters': 0.01, 'currency': 'USD',
            'api_key_env': 'SYNTHETIC_GATEWAY_KEY'}})
        self.update_script()
        self.grant()
        # New cast choices are delegated, but a different external route is not.
        self.profile['cast'] = {'CHAR-001': {'provider': 'custom-http', 'voice': 'actor',
                                          'options': {'endpoint': 'https://other.invalid/speech'}}}
        self.update_script([{'id': 'UTT-1', 'speaker': 'CHAR-001', 'text': self.text}])
        self.assertEqual(delegation_status(self.project)[0], 'authorized')
        with patch.dict('os.environ', {'SYNTHETIC_GATEWAY_KEY': 'SYNTHETIC-KEY'}), patch('speech.fetch_audio') as fetch:
            with self.assertRaisesRegex(ValueError, 'actual custom speech endpoint'):
                self.render()
        fetch.assert_not_called()

    def test_new_narrator_cast_entry_cannot_bypass_an_explicit_voice_choice(self):
        self.grant()
        self.profile['cast'] = {'NARRATOR': {'provider': 'inworld', 'voice': 'different-narrator'}}
        self.update_script()
        self.assertEqual(delegation_status(self.project)[0], 'stale')

    def test_voice_presets_snapshot_exact_audio_without_copying_story_cast(self):
        import shutil
        from workflow import apply_preferences, load_preset, save_preset
        reference = self.project / 'audio/voice-input.wav'
        reference.write_bytes(wav_bytes())
        self.profile['providers']['chatterbox'] = {'reference_audio': 'audio/voice-input.wav', 'model': 'turbo'}
        self.profile['cast'] = {'CHAR-001': {'provider': 'inworld', 'voice': 'story-specific-character'}}
        self.update_script()
        with patch('workflow.ROOT', self.base):
            save_preset(self.project, 'saved-voices')
            data = load_preset('saved-voices')
            self.assertNotIn('cast', data['narrator'])
            next_project = self.base / 'next-story'
            shutil.copytree(ROOT / 'templates/story', next_project)
            apply_preferences(next_project, data, replace=True)
            selected = read_json(next_project / 'audio/narrator.json')
            copied = next_project / selected['providers']['chatterbox']['reference_audio']
            self.assertEqual(sha256_file(copied), sha256_file(reference))
            self.assertEqual(selected['cast'], {})
            self.assertFalse((next_project / 'production/delegation.json').exists())
            reference.write_bytes(wav_bytes(frames=4800))
            with self.assertRaisesRegex(ValueError, 'missing, changed'):
                load_preset('saved-voices')

    def test_actual_legacy_kokoro_route_keeps_local_cache_and_measured_output(self):
        from studio_common import configuration
        runtime = configuration(self.project)['runtime']
        model, voices = ROOT / runtime['model'], ROOT / runtime['voices']
        if not model.is_file() or not voices.is_file():
            self.skipTest('Optional Kokoro runtime weights are not installed')
        self.profile.update(provider='kokoro', model=None, voice='am_michael', providers={}, cast={},
                            model_sha256=sha256_file(model), voices_sha256=sha256_file(voices))
        self.update_script()
        workflow = read_json(self.project / 'production/workflow.json')
        workflow['scope']['tools'].append('kokoro')
        atomic_json(self.project / 'production/workflow.json', workflow)
        self.grant()
        with patch('speech.fetch_audio', side_effect=AssertionError('No cloud fallback')):
            first = self.render()
            second = self.render()
        self.assertGreater(first['duration'], 0)
        self.assertEqual(first['audio_sha256'], second['audio_sha256'])
        self.assertEqual(first['provider'], 'kokoro')


class ChatterboxBridgeContracts(unittest.TestCase):
    def test_local_model_always_uses_the_explicit_role_reference_and_supported_controls(self):
        import tempfile
        import numpy as np
        from chatterbox_server import synthesize
        class Samples:
            def detach(self): return self
            def cpu(self): return self
            def numpy(self): return np.zeros((1, 2400), dtype=np.float32)
        class Model:
            sr = 24000
            def __init__(self): self.calls = []
            def generate(self, text, **kwargs):
                self.calls.append((text, kwargs))
                return Samples()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            first, second = root / 'first.wav', root / 'second.wav'
            first.write_bytes(wav_bytes())
            second.write_bytes(wav_bytes(frames=4800))
            model = Model()
            body = {'model': 'turbo', 'voice': 'actor', 'text': 'Hello.', 'speed': 1, 'language': 'en-US', 'reference_audio': str(first), 'direction': 'laugh'}
            audio = synthesize(model, 'turbo', root, body)
            self.assertTrue(audio.startswith(b'RIFF'))
            body['reference_audio'] = str(second)
            synthesize(model, 'turbo', root, body)
            self.assertEqual([call[1]['audio_prompt_path'] for call in model.calls], [str(first), str(second)])
            self.assertEqual(model.calls[0][0], '[laugh] Hello.')
            with self.assertRaisesRegex(ValueError, 'do not support'):
                synthesize(model, 'turbo', root, dict(body, exaggeration=0.5))
            with self.assertRaisesRegex(ValueError, 'English only'):
                synthesize(model, 'turbo', root, dict(body, language='es-ES'))


if __name__ == '__main__':
    unittest.main()
