"""Batch planning, real handoff boundaries and efficient resumable production."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_workflow as fixtures
from studio_common import atomic_json, atomic_text, executable, read_json, sha256_file
from production_plan import apply, snapshot
from production_next import continue_project, next_work
from production_session import session_lock


class PlanTests(unittest.TestCase):
    setUp = fixtures.FastFixture.setUp

    def bundle(self, files):
        result = snapshot(self.project)
        result['artifacts'] = files
        return result

    def test_batch_writes_canonical_records_and_preserves_exact_prior_bytes(self):
        path = self.project / 'world/visual-bible.md'
        old = path.read_bytes()
        bundle = self.bundle({'world/visual-bible.md': '# Synthetic visual bible\n',
                              'parts/part_001/shots.json': read_json(self.part / 'shots.json')})
        result = apply(self.project, bundle)
        self.assertEqual(result['status'], 'applied')
        before = Path(result['receipt']).parent / 'before/world/visual-bible.md'
        self.assertEqual(before.read_bytes(), old)
        self.assertEqual(apply(self.project, bundle)['status'], 'unchanged')
        self.assertFalse((self.project / 'production/delegation.json').exists())

    def test_check_never_changes_canonical_records(self):
        bundle = self.bundle({'world/visual-bible.md': '# New synthetic bible\n'})
        old = (self.project / 'world/visual-bible.md').read_bytes()
        self.assertEqual(apply(self.project, bundle, check=True)['status'], 'checked')
        self.assertEqual((self.project / 'world/visual-bible.md').read_bytes(), old)

    def test_concurrent_edit_is_rejected_without_overwriting_it(self):
        bundle = self.bundle({'world/visual-bible.md': '# Proposed\n'})
        atomic_text(self.project / 'world/visual-bible.md', '# Actual concurrent edit\n')
        with self.assertRaisesRegex(ValueError, 'changed after'):
            apply(self.project, bundle)
        self.assertEqual((self.project / 'world/visual-bible.md').read_text(), '# Actual concurrent edit\n')

    def test_source_mismatch_and_protected_records_never_write(self):
        for name in ('creative/original.md', 'creative/story-revised.md', 'production/delegation.json',
                     'production/preview-decisions.json', 'audio/narrator.json', '../outside.md',
                     'world/../creative/original.md', 'WORLD/visual-bible.md'):
            bundle = self.bundle({name: {}})
            with self.subTest(name=name), self.assertRaises(ValueError):
                apply(self.project, bundle)
        bundle = self.bundle({'world/visual-bible.md': '# Proposed'})
        bundle['source_sha256'] = 'different story'
        with self.assertRaisesRegex(ValueError, 'different story'):
            apply(self.project, bundle)

    def test_invalid_cross_reference_rolls_back_the_whole_batch(self):
        registry = read_json(self.project / 'continuity/entities.json')
        registry['styles']['STYLE-001']['canonical_file'] = 'world/missing.md'
        bundle = self.bundle({'world/visual-bible.md': '# Proposed\n', 'continuity/entities.json': registry})
        old = {name: (self.project / name).read_bytes() for name in bundle['artifacts']}
        with self.assertRaisesRegex(ValueError, 'canonical file missing'):
            apply(self.project, bundle)
        for name, content in old.items():
            self.assertEqual((self.project / name).read_bytes(), content)

    def test_narration_is_derived_from_spoken_turns_and_labels_are_excluded(self):
        shots = read_json(self.part / 'shots.json')
        shots['timing_mode'] = 'speech_turns'
        shots['shots'][0]['narration'] = 'A quiet room.'
        bundle = self.bundle({'parts/part_001/shots.json': shots,
                              'parts/part_001/speech.json': {'utterances': [{'id': 'UTT-001', 'speaker': 'NARRATOR', 'text': 'A quiet room.'}]}})
        apply(self.project, bundle)
        self.assertEqual((self.part / 'narration.txt').read_text(), 'A quiet room.\n')
        bundle = self.bundle({'parts/part_001/shots.json': shots,
                              'parts/part_001/speech.json': {'utterances': [{'text': 'Different words.'}]}})
        with self.assertRaisesRegex(ValueError, 'differ'):
            apply(self.project, bundle)


class HandoffTests(unittest.TestCase):
    setUp = fixtures.FastFixture.setUp

    def plan(self):
        atomic_text(self.project / 'creative/original.md', 'The key is found.\nThe locked door opens.\n')
        shutil.copytree(self.part, self.project / 'parts/part_002', dirs_exist_ok=True)
        intake = read_json(self.project / 'creative/intake.json')
        intake.update(mode='parts', desired_part_count=2)
        atomic_json(self.project / 'creative/intake.json', intake)
        return {'schema_version': 1, 'story_file': 'creative/original.md',
                'story_sha256': sha256_file(self.project / 'creative/original.md'), 'parts': [
                    {'id': 'part_001', 'title': 'Key', 'start_line': 1, 'end_line': 1,
                     'opening_hook': 'Find the hidden key', 'dramatic_progress': 'The key is found', 'ending': 'The door remains locked',
                     'entry_state': {'STYLE-001': {'key': False}}, 'exit_state': {'STYLE-001': {'key': True}},
                     'continuation': {'id': 'PROMISE-001', 'next_part': 'part_002', 'promise': 'Where does the key fit?', 'payoff': 'Open the locked door'}},
                    {'id': 'part_002', 'title': 'Door', 'start_line': 2, 'end_line': 2,
                     'opening_hook': 'Try the key', 'dramatic_progress': 'The door opens', 'ending': 'The mystery resolves',
                     'entry_state': {'STYLE-001': {'key': True}}, 'exit_state': {'STYLE-001': {'key': True}},
                     'pays_off': ['PROMISE-001'], 'continuation': None}]}

    def errors(self, plan):
        from part_continuity import problems
        atomic_json(self.project / 'creative/part-plan.json', plan)
        return problems(self.project)

    def test_complete_story_and_state_are_carried_into_next_part(self):
        from part_continuity import handoff
        plan = self.plan()
        self.assertEqual(self.errors(plan), [])
        context = handoff(self.project, 'part_002')
        self.assertEqual(context['story_excerpt'], 'The locked door opens.\n')
        self.assertEqual(context['previous_ending'], plan['parts'][0]['ending'])
        self.assertEqual(context['entry_state'], plan['parts'][0]['exit_state'])

    def test_missing_payoff_or_inherited_fact_or_uncovered_ending_is_rejected(self):
        for mutation in ('payoff', 'state', 'span', 'final_promise', 'hook'):
            plan = self.plan()
            if mutation == 'payoff': plan['parts'][1]['pays_off'] = []
            if mutation == 'state': plan['parts'][1]['entry_state'] = {}
            if mutation == 'span': plan['parts'][1]['start_line'] = 1
            if mutation == 'final_promise': plan['parts'][1]['continuation'] = plan['parts'][0]['continuation']
            if mutation == 'hook': plan['parts'][0]['opening_hook'] = ''
            with self.subTest(mutation=mutation): self.assertTrue(self.errors(plan))

    def test_changed_story_and_changed_single_delivery_require_a_current_plan(self):
        plan = self.plan()
        atomic_text(self.project / 'creative/original.md', 'Changed story.\n')
        self.assertIn('different', ' '.join(self.errors(plan)))
        plan = self.plan()
        intake = read_json(self.project / 'creative/intake.json'); intake['mode'] = 'single'
        atomic_json(self.project / 'creative/intake.json', intake)
        self.assertIn('single', ' '.join(self.errors(plan)))

    def test_registered_state_transition_can_bridge_a_time_jump(self):
        plan = self.plan()
        plan['parts'][1]['entry_state']['STYLE-001']['key'] = False
        plan['parts'][1]['exit_state']['STYLE-001']['key'] = False
        plan['parts'][1]['handoff_events'] = ['EVENT-001']
        atomic_json(self.project / 'continuity/state-ledger.json', {'changes': [
            {'id': 'EVENT-001', 'entity_id': 'STYLE-001', 'story_time': 2,
             'before': {'key': True}, 'after': {'key': False}}]})
        self.assertEqual(self.errors(plan), [])


class NextWorkTests(unittest.TestCase):
    setUp = fixtures.FastFixture.setUp
    authorize = fixtures.FastFixture.authorize

    def ready(self):
        from preflight import inputs
        atomic_json(self.project / 'production/preflight.json', {'ready': True, 'inputs': inputs(self.project, self.part.name)})

    def test_dependency_line_endings_preserve_scope_but_changed_dependencies_do_not(self):
        from workflow import delegation_status
        root = self.base / 'lock-fixture'
        root.mkdir()
        lock = root / 'requirements.lock.txt'
        lock.write_bytes(b'fixture==1.0\n')
        with patch('workflow.ROOT', root):
            self.authorize()
            lock.write_bytes(b'fixture==1.0\r\n')
            self.assertEqual(delegation_status(self.project)[0], 'authorized')
            grant = read_json(self.project / 'production/delegation.json')
            grant['configuration']['@studio/requirements.lock.txt'] = hashlib.sha256(lock.read_bytes()).hexdigest()
            atomic_json(self.project / 'production/delegation.json', grant)
            lock.write_bytes(b'fixture==1.0\n')
            self.assertEqual(delegation_status(self.project)[0], 'authorized')
            lock.write_bytes(b'fixture==2.0\n')
            self.assertEqual(delegation_status(self.project)[0], 'stale')

    def test_questions_and_agent_work_remain_distinct_and_next_is_read_only(self):
        self.assertEqual(next_work(self.project)['actions'][0]['actor'], 'user')
        self.authorize()
        before = {str(p): p.read_bytes() for p in self.project.rglob('*') if p.is_file()}
        packet = next_work(self.project)
        self.assertEqual(packet['actions'][0]['kind'], 'preflight')
        self.assertEqual(packet['actions'][0]['actor'], 'agent')
        after = {str(p): p.read_bytes() for p in self.project.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_strict_uses_its_existing_sequence_without_requesting_all_gates_at_once(self):
        workflow = read_json(self.project / 'production/workflow.json'); workflow['mode'] = 'strict'
        atomic_json(self.project / 'production/workflow.json', workflow)
        packet = next_work(self.project)
        self.assertEqual(packet['actions'][0]['kind'], 'strict_workflow')
        self.assertEqual(packet['actions'][0]['actor'], 'agent')

    def test_unknown_provider_outcome_blocks_without_queue_or_generation(self):
        self.authorize()
        atomic_json(self.project / 'production/speech-jobs/unknown.json', {'status': 'requesting'})
        with patch('studio.run_project') as run, patch('image_jobs.queue_request') as queue:
            packet = continue_project(self.project)
        self.assertEqual(packet['actions'][0]['kind'], 'reconcile_provider')
        run.assert_not_called(); queue.assert_not_called()

    def test_reference_is_prepared_before_final_recurring_character_images(self):
        atomic_json(self.project / 'production/settings.json', {'image_provider': {'estimated_cost_per_image': 0.1, 'currency': 'USD'}})
        self.authorize(); self.ready()
        registry = read_json(self.project / 'continuity/entities.json')
        from cast_fixtures import install_profile
        install_profile(self.project)
        written = read_json(self.part / 'shots.json'); written['shots'][0]['character_ids'] = ['CHAR-001']
        written['shots'].append(dict(written['shots'][0], id='SHOT-002'))
        atomic_json(self.part / 'shots.json', written)
        timeline = read_json(self.part / 'timeline.json')
        timeline['shots'][0]['character_ids'] = ['CHAR-001']
        atomic_json(self.part / 'timeline.json', timeline)
        self.assertEqual(next_work(self.project)['actions'][0]['entity'], 'CHAR-001')

    @unittest.skipUnless(executable('ffmpeg'), 'Actual FFmpeg required')
    def test_preview_runs_once_then_waits_for_agent_inspection_and_real_decision(self):
        from quality import record_image_review
        self.authorize()
        packet = continue_project(self.project)
        self.assertEqual(packet['actions'][0]['kind'], 'image_inspection')
        self.assertTrue((self.part / 'preview.mp4').is_file())
        record_image_review(self.project, 'part_001', 'SHOT-001', 'passed', 'Synthetic test only.', 'unit fixture')
        with patch('studio.run_project') as run:
            packet = continue_project(self.project)
        run.assert_not_called()
        self.assertEqual(packet['actions'][0]['kind'], 'preview_decision')
        self.assertEqual(packet['actions'][0]['actor'], 'user')
        self.assertFalse((self.project / 'production/preview-decisions.json').exists())
        timeline = read_json(self.part / 'timeline.json')
        flagged = {'word': 'synthetic', 'start': 0.1, 'end': 0.5, 'reviewed': False}
        timeline['alignment'] = {'uncertain_ranges': [flagged]}
        atomic_json(self.part / 'timeline.json', timeline)
        self.assertEqual(next_work(self.project)['actions'][0]['alignment_checks'], [flagged])

    @unittest.skipUnless(executable('ffmpeg'), 'Actual FFmpeg required')
    def test_image_handoffs_reuse_local_work_and_do_not_reserve_again(self):
        atomic_json(self.project / 'production/settings.json', {'image_provider': {'estimated_cost_per_image': 0.1, 'currency': 'USD'}})
        self.authorize()
        (self.part / 'images/shot_001.png').unlink()
        first = continue_project(self.project)
        self.assertEqual(first['actions'][0]['kind'], 'execute_image')
        with patch('studio.run_project') as run:
            second = continue_project(self.project)
        run.assert_not_called()
        self.assertEqual(first['actions'][0]['request'], second['actions'][0]['request'])
        record = read_json(Path(second['actions'][0]['request']))
        self.assertEqual(record['reserved_calls'], 1)
        record.update(status='generated', image='parts/part_001/images/recorded-fixture.png', image_sha256='synthetic missing pixels')
        atomic_json(Path(second['actions'][0]['request']), record)
        third = continue_project(self.project)
        self.assertEqual(third['actions'][0]['kind'], 'inspect_image')
        self.assertEqual(read_json(Path(third['actions'][0]['request']))['reserved_calls'], 1)

    def test_coordinator_lock_is_reentrant_and_rejects_other_processes(self):
        with session_lock(self.project):
            with session_lock(self.project): pass
            script = 'import sys;sys.path.insert(0,sys.argv[1]);from production_session import session_lock\nwith session_lock(sys.argv[2]):print("unexpected")'
            result = subprocess.run([sys.executable, '-B', '-c', script, str(Path(__file__).resolve().parents[1] / 'tools'), str(self.project)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Another production coordinator', result.stderr)
        with session_lock(self.project): pass

    @unittest.skipUnless(executable('ffmpeg'), 'Actual FFmpeg required')
    def test_complete_resume_preserves_preview_decision_playback_and_immutable_delivery(self):
        from quality import record_image_review
        from workflow import record_preview
        from delivery import record_playback
        self.authorize()
        continue_project(self.project)
        record_image_review(self.project, 'part_001', 'SHOT-001', 'passed', 'Synthetic mechanical fixture.', 'unit fixture')
        record_preview(self.project, 'part_001', 'SYNTHETIC TEST DECISION ONLY', 'isolated unit fixture')
        packet = continue_project(self.project)
        self.assertEqual(packet['actions'][0]['kind'], 'playback')
        self.assertFalse((self.project / 'delivery/part_001-r1').exists())
        master_hash = sha256_file(self.part / 'final.mp4')
        timeline = read_json(self.part / 'timeline.json')
        timeline['timing_source'] = {'review': 'SYNTHETIC review-only metadata refresh'}
        atomic_json(self.part / 'timeline.json', timeline)
        self.assertEqual(next_work(self.project)['actions'][0]['kind'], 'run_master')
        with patch('studio.invoke', side_effect=AssertionError('Review metadata must reuse encoded media')):
            self.assertEqual(continue_project(self.project)['actions'][0]['kind'], 'playback')
        self.assertEqual(sha256_file(self.part / 'final.mp4'), master_hash)
        record_playback(self.project, 'part_001', 'unit fixture', 'Synthetic mechanical test only; not actual human artistic approval.', True)
        packet = continue_project(self.project)
        self.assertEqual(packet['actions'][0]['kind'], 'complete')
        manifest = self.project / 'delivery/part_001-r1/manifest.json'
        before = manifest.read_bytes()
        with patch('studio.run_project') as run:
            packet = continue_project(self.project)
        run.assert_not_called()
        self.assertEqual(manifest.read_bytes(), before)
        self.assertFalse((self.project / 'delivery/part_001-r2').exists())
        written = read_json(self.part / 'shots.json')
        written['shots'][0]['visual_description'] = 'Synthetic changed visual requirement.'
        atomic_json(self.part / 'shots.json', written)
        self.assertEqual(next_work(self.project)['actions'][0]['kind'], 'inspection', 'A delivered file does not hide a changed visual plan')
        self.assertEqual(manifest.read_bytes(), before)

    def test_unreported_image_cost_needs_an_actual_scope_choice(self):
        self.authorize(); self.ready()
        from test_studio import write_tone
        write_tone(self.part / 'audio/final_mix.wav', 1)
        (self.part / 'images/shot_001.png').unlink()
        self.assertEqual(next_work(self.project)['actions'][0]['kind'], 'image_cost_scope')


class CachedReadinessTests(unittest.TestCase):
    setUp = fixtures.FastFixture.setUp
    authorize = fixtures.FastFixture.authorize

    def cached(self):
        from speech import input_fingerprint, plan_speech
        from test_studio import write_tone
        profile = read_json(self.project / 'audio/narrator.json')
        profile.update(provider='chatterbox', model='nano', voice='synthetic-narrator',
                       providers={'chatterbox': {'endpoint': 'http://127.0.0.1:1/speech', 'reference_audio': 'audio/fixture-reference.wav'}})
        write_tone(self.project / 'audio/fixture-reference.wav', 1)
        atomic_json(self.project / 'audio/narrator.json', profile)
        atomic_text(self.part / 'narration.txt', 'A quiet room.')
        timeline = read_json(self.part / 'timeline.json'); timeline['narration_file'] = 'audio/narration.wav'
        atomic_json(self.part / 'timeline.json', timeline)
        write_tone(self.part / 'audio/narration.wav', 1)
        write_tone(self.part / 'audio/clip.wav', 1)
        turns = plan_speech(self.project, profile, 'A quiet room.', require_runtime=False)
        atomic_json(self.part / 'audio/narration.chunks.json', {
            'speech_input_fingerprint': input_fingerprint(turns), 'audio_sha256': sha256_file(self.part / 'audio/narration.wav'),
            'chunks': [{'file': 'clip.wav', 'sha256': sha256_file(self.part / 'audio/clip.wav')}]})

    def test_verified_clips_skip_provider_setup_and_corrupt_clip_does_not(self):
        from preflight import inspect, speech_cached
        self.cached()
        with patch('preflight.local_info', side_effect=AssertionError('No provider contact for verified cached speech')):
            self.assertTrue(speech_cached(self.project, self.part))
            self.assertTrue(inspect(self.project, self.part.name, live_local=True, reuse_verified=True)['ready'])
        atomic_text(self.part / 'audio/clip.wav', 'Corrupt cached bytes')
        self.assertFalse(speech_cached(self.project, self.part))
        with patch('preflight.local_info', side_effect=ValueError('Actual offline test endpoint')):
            self.assertFalse(inspect(self.project, self.part.name, live_local=True, reuse_verified=True)['ready'])

    def test_role_sample_is_agent_work_before_full_generation_and_reuses_real_existing_bytes(self):
        from preflight import inputs
        self.cached()
        intake = read_json(self.project / 'creative/intake.json'); intake.update(performance='narration', language='en-us')
        atomic_json(self.project / 'creative/intake.json', intake)
        workflow = read_json(self.project / 'production/workflow.json'); workflow['scope']['tools'].append('chatterbox')
        atomic_json(self.project / 'production/workflow.json', workflow)
        self.authorize()
        atomic_json(self.project / 'production/preflight.json', {'ready': True, 'inputs': inputs(self.project, self.part.name)})
        packet = next_work(self.project)
        self.assertEqual(packet['actions'][0]['kind'], 'casting')
        self.assertEqual(packet['actions'][0]['actor'], 'agent')
        atomic_json(self.project / 'audio/voice-plan.json', {'roles': {'NARRATOR': {
            'performance_brief': 'Synthetic restrained narration fixture.',
            'selected': {'provider': 'chatterbox', 'model': 'nano', 'voice': 'synthetic-narrator'},
            'sample': {'file': 'audio/fixture-reference.wav', 'sha256': sha256_file(self.project / 'audio/fixture-reference.wav'),
                       'provider': 'chatterbox', 'model': 'nano', 'voice': 'synthetic-narrator'},
            'listening_status': 'Provisional test fixture, no actual listening claimed.'}}})
        self.assertNotEqual(next_work(self.project)['actions'][0]['kind'], 'casting')
        profile = read_json(self.project / 'audio/narrator.json'); profile['voice'] = 'different-role-voice'
        atomic_json(self.project / 'audio/narrator.json', profile)
        plan = read_json(self.project / 'audio/voice-plan.json')
        plan['roles']['NARRATOR']['selected']['voice'] = 'different-role-voice'
        atomic_json(self.project / 'audio/voice-plan.json', plan)
        self.authorize()
        atomic_json(self.project / 'production/preflight.json', {'ready': True, 'inputs': inputs(self.project, self.part.name)})
        self.assertEqual(next_work(self.project)['actions'][0]['kind'], 'casting', 'An old audition cannot prove a newly selected voice')


if __name__ == '__main__': unittest.main()
