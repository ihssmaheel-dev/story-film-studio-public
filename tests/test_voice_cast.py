"""Story voice changes, scoped decision history and character auditions; no live providers."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import test_workflow as fixture_support
from speech_providers import voice_config
from studio_common import atomic_json, atomic_text, read_json, sha256_file
from voice_cast import audition_profile, set_voice
from workflow import audit_problems, authorize, delegation_status, policy, record_revision, save_preset


class VoiceCastTests(unittest.TestCase):
    def setUp(self):
        fixture_support.FastFixture.setUp(self)
        self.profile = read_json(self.project / 'audio/narrator.json')
        self.profile.update(provider='inworld', voice=None,
                            providers={'inworld': {'price_per_1000_characters': 0.01, 'currency': 'USD'}})
        atomic_json(self.project / 'audio/narrator.json', self.profile)
        intake = read_json(self.project / 'creative/intake.json')
        intake.update(performance='mixed', language='en-us')
        atomic_json(self.project / 'creative/intake.json', intake)
        value = policy(self.project)
        value['scope']['tools'] += ['inworld', 'elevenlabs']
        value['scope']['external_upload'] += ['inworld', 'elevenlabs']
        atomic_json(self.project / 'production/workflow.json', value)
        entities = read_json(self.project / 'continuity/entities.json')
        entities['characters'] = {'CHAR-001': {'canonical_file': 'world/characters/CHAR-001.md'}}
        atomic_json(self.project / 'continuity/entities.json', entities)
        timeline = read_json(self.part / 'timeline.json')
        timeline['narration_file'] = 'audio/narration.wav'
        atomic_json(self.part / 'timeline.json', timeline)

    def grant(self):
        return authorize(self.project, 'SYNTHETIC TEST AUTHORIZATION ONLY', 'isolated voice fixture')

    def test_agent_selects_unset_narrator_and_can_refine_delegated_voice(self):
        grant = self.grant()
        for voice in ('warm-story-voice', 'clear-story-voice'):
            result = set_voice(self.project, 'NARRATOR', voice, 'Quiet intimate first-person story; restrained delivery')
            self.assertTrue(result['changed'])
            self.assertEqual(result['configuration_status'], 'authorized')
            self.assertFalse(result['speech_generated'])
        self.assertEqual(read_json(self.project / 'production/delegation.json'), grant)
        self.assertEqual(read_json(self.project / 'audio/voice-decisions.json')['changes'][-1]['decision_kind'], 'delegated')
        plan = read_json(self.project / 'audio/voice-plan.json')
        self.assertEqual(plan['status'], 'provisional')
        self.assertEqual(plan['roles']['NARRATOR']['selected']['voice'], 'clear-story-voice')
        self.assertIn('pending actual', plan['roles']['NARRATOR']['listening_status'])

    def test_explicit_change_keeps_scope_and_original_permission_history(self):
        self.profile['voice'] = 'old-voice'
        atomic_json(self.project / 'audio/narrator.json', self.profile)
        old_hash = sha256_file(self.project / 'audio/narrator.json')
        grant = self.grant()
        with self.assertRaisesRegex(ValueError, 'actual user change request'):
            set_voice(self.project, 'NARRATOR', 'new-voice', 'More restrained narration')
        result = set_voice(self.project, 'NARRATOR', 'new-voice', 'More restrained narration',
                           decision='SYNTHETIC: change narrator to new-voice', reference='unit test change')
        self.assertEqual(result['configuration_status'], 'authorized')
        current = read_json(self.project / 'production/delegation.json')
        self.assertEqual(current['scope'], grant['scope'])
        self.assertEqual(current['decision_quote'], grant['decision_quote'])
        self.assertEqual(current['history'][-1]['configuration'], grant['configuration'])
        self.assertIn('change narrator', current['voice_changes'][-1]['decision_quote'])
        self.assertEqual(sha256_file(self.project / 'audio/voice-revisions' / (old_hash + '.json')), old_hash)
        # A later unrecorded edit cannot change this user's newly explicit choice.
        profile = read_json(self.project / 'audio/narrator.json')
        profile['cast']['NARRATOR']['voice'] = 'unrequested-voice'
        atomic_json(self.project / 'audio/narrator.json', profile)
        self.assertEqual(delegation_status(self.project)[0], 'stale')

    def test_user_can_fix_a_previously_delegated_voice_without_reapproving_configuration(self):
        self.grant()
        set_voice(self.project, 'NARRATOR', 'agent-voice', 'Fits the gentle story')
        result = set_voice(self.project, 'NARRATOR', 'user-voice', 'User prefers a brighter timbre',
                           decision='SYNTHETIC: use user-voice', reference='unit test')
        self.assertEqual(result['configuration_status'], 'authorized')
        self.assertFalse(read_json(self.project / 'production/delegation.json')['delegate_voice'])

    def test_user_keeping_current_candidate_makes_that_choice_explicit(self):
        self.grant()
        set_voice(self.project, 'NARRATOR', 'candidate', 'A suitable quiet observer')
        result = set_voice(self.project, 'NARRATOR', 'candidate', 'User selected the auditioned candidate',
                           decision='SYNTHETIC: keep candidate', reference='unit test')
        self.assertEqual(result['affected_parts'], [])
        self.assertFalse(read_json(self.project / 'production/delegation.json')['delegate_voice'])
        with self.assertRaisesRegex(ValueError, 'actual user change request'):
            set_voice(self.project, 'NARRATOR', 'other-candidate', 'Another unrequested voice')

    def test_narrator_change_preserves_character_voice_and_reports_only_used_roles(self):
        self.profile.update(voice='narrator-A', cast={'CHAR-001': {'voice': 'character-A'}})
        atomic_json(self.project / 'audio/narrator.json', self.profile)
        atomic_json(self.part / 'speech.json', {'utterances': [
            {'id': 'UTT-1', 'speaker': 'NARRATOR', 'text': 'She waited.'},
            {'id': 'UTT-2', 'speaker': 'CHAR-001', 'text': 'Hello.'}]})
        previous_character = voice_config(self.profile, 'CHAR-001')
        self.grant()
        result = set_voice(self.project, 'NARRATOR', 'narrator-B', 'Closer emotional point of view',
                           decision='SYNTHETIC: change narrator', reference='unit test')
        profile = read_json(self.project / 'audio/narrator.json')
        self.assertEqual(voice_config(profile, 'CHAR-001'), previous_character)
        self.assertEqual(result['affected_parts'][0]['speakers'], ['NARRATOR'])
        self.assertIn('reuse unchanged source images', result['affected_parts'][0]['images'])

    def test_character_assignment_and_user_change_do_not_lock_other_delegated_roles(self):
        self.grant()
        set_voice(self.project, 'CHAR-001', 'character-A', 'Fits the cautious returning parent')
        set_voice(self.project, 'CHAR-001', 'character-B', 'User prefers this performance',
                  decision='SYNTHETIC: change character voice', reference='unit test')
        result = set_voice(self.project, 'NARRATOR', 'narrator-A', 'Quiet external observer')
        self.assertEqual(result['configuration_status'], 'authorized')
        with self.assertRaisesRegex(ValueError, 'Register the story character'):
            set_voice(self.project, 'CHAR-999', 'unknown', 'No actual role')

    def test_provider_switch_requires_existing_upload_scope_and_actual_request(self):
        self.profile['voice'] = 'narrator-A'
        atomic_json(self.project / 'audio/narrator.json', self.profile)
        self.grant()
        before = (self.project / 'audio/narrator.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'outside the authorized tools'):
            set_voice(self.project, 'NARRATOR', 'cartesia-voice', 'Alternate performance', provider='cartesia',
                      decision='SYNTHETIC voice request', reference='unit test')
        self.assertEqual((self.project / 'audio/narrator.json').read_bytes(), before)
        result = set_voice(self.project, 'NARRATOR', 'eleven-voice', 'User selected an alternative actor', provider='elevenlabs',
                           decision='SYNTHETIC: use ElevenLabs voice', reference='unit test')
        self.assertEqual(result['voice']['provider'], 'elevenlabs')
        self.assertEqual(result['voice']['model'], 'eleven_v4')
        self.assertEqual(result['configuration_status'], 'authorized')

    def test_stale_other_inputs_cannot_be_authorized_by_voice_change(self):
        self.grant()
        intake = read_json(self.project / 'creative/intake.json')
        intake['visual_style'] = 'Unapproved replacement'
        atomic_json(self.project / 'creative/intake.json', intake)
        before = (self.project / 'audio/narrator.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'stale configuration'):
            set_voice(self.project, 'NARRATOR', 'new-voice', 'Voice request', decision='SYNTHETIC: use voice', reference='test')
        self.assertEqual((self.project / 'audio/narrator.json').read_bytes(), before)

    def test_voice_change_does_not_revoke_existing_story_edit_permission(self):
        self.grant()
        revised = self.project / 'creative/story-revised.md'
        atomic_text(revised, 'A quiet room!\n')
        record_revision(self.project, 'minor', 'Synthetic punctuation correction')
        ledger = read_json(self.project / 'continuity/story-ledger.json')
        ledger['review_coverage']['checked_story_sha256'] = sha256_file(revised)
        atomic_json(self.project / 'continuity/story-ledger.json', ledger)
        audit = read_json(self.project / 'creative/audit-issues.json')
        audit['final_story_sha256'] = sha256_file(revised)
        atomic_json(self.project / 'creative/audit-issues.json', audit)
        self.assertEqual(audit_problems(self.project), [])
        set_voice(self.project, 'NARRATOR', 'user-choice', 'User prefers a softer narrator',
                  decision='SYNTHETIC: choose user-choice', reference='unit test')
        self.assertEqual(audit_problems(self.project), [])

    def test_character_audition_uses_its_actual_options_without_altering_configuration(self):
        self.profile.update(voice='narrator', cast={'CHAR-001': {'voice': 'character', 'speed': 0.9,
                            'options': {'delivery_mode': 'creative'}}})
        before = copy.deepcopy(self.profile)
        audition = audition_profile(self.profile, 'CHAR-001')
        self.assertEqual(audition['voice'], 'character')
        self.assertEqual(audition['speed'], 0.9)
        self.assertEqual(audition['providers']['inworld']['delivery_mode'], 'creative')
        self.assertEqual(audition['cast'], {})
        self.assertEqual(self.profile, before)
        other = audition_profile(self.profile, 'CHAR-001', provider='elevenlabs', voice='other-voice')
        self.assertIsNone(other['model'])
        self.assertEqual(voice_config(other)['model'], 'eleven_v4')
        with self.assertRaisesRegex(ValueError, 'Assign the character'):
            audition_profile(self.profile, 'CHAR-999')

    def test_saved_preset_uses_current_narrator_override_without_story_cast(self):
        self.grant()
        set_voice(self.project, 'NARRATOR', 'selected-narrator', 'A measured intimate voice')
        set_voice(self.project, 'CHAR-001', 'story-character', 'A contrasting character voice')
        with patch('workflow.ROOT', self.base):
            path = save_preset(self.project, 'selected-voice')
        saved = read_json(path)['narrator']
        self.assertEqual(saved['voice'], 'selected-narrator')
        self.assertEqual(saved['provider'], 'inworld')
        self.assertNotIn('cast', saved)

    def test_noop_preserves_bytes_and_requires_no_new_decision(self):
        self.profile['voice'] = 'same-voice'
        atomic_json(self.project / 'audio/narrator.json', self.profile)
        self.grant()
        before = (self.project / 'audio/narrator.json').read_bytes()
        result = set_voice(self.project, 'NARRATOR', 'same-voice', 'Retain current suitable selection')
        self.assertFalse(result['changed'])
        self.assertEqual((self.project / 'audio/narrator.json').read_bytes(), before)
        self.assertFalse((self.project / 'audio/voice-decisions.json').exists())

    def test_strict_change_stales_only_affected_voice_gates(self):
        from project_records import snapshot
        self.profile['voice'] = 'old-narrator'
        atomic_json(self.project / 'audio/narrator.json', self.profile)
        value = policy(self.project)
        value['mode'] = 'strict'
        atomic_json(self.project / 'production/workflow.json', value)
        gates = read_json(self.project / 'approvals.json')
        for gate in ('G5', 'G6'):
            gates['gates'][gate].update(status='approved', artifacts=snapshot(self.project, gate),
                                       decision_quote='SYNTHETIC FIXTURE ONLY')
        atomic_json(self.project / 'approvals.json', gates)
        set_voice(self.project, 'NARRATOR', 'new-narrator', 'User requests a calmer voice',
                  decision='SYNTHETIC: change voice', reference='unit test')
        current = read_json(self.project / 'approvals.json')['gates']
        self.assertEqual(current['G5']['status'], 'stale')
        self.assertEqual(current['G6']['status'], 'stale')
        self.assertTrue(all(current[gate]['status'] == 'draft' for gate in ('G1', 'G2', 'G3', 'G4')))


if __name__ == '__main__':
    unittest.main()
