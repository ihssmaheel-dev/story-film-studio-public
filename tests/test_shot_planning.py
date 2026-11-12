"""Story-driven count records, real timing context and legacy/cache compatibility."""
import unittest
from unittest.mock import patch

import test_workflow as fixtures
from production_next import next_work
from production_plan import apply, snapshot
from shot_planning import problems, summary
from studio_common import atomic_json, atomic_text, read_json, sha256_file
from workflow import written_problems


class ShotPlanningTests(unittest.TestCase):
    setUp = fixtures.FastFixture.setUp
    authorize = fixtures.FastFixture.authorize

    def plan(self, count=1):
        document = read_json(self.part / 'shots.json')
        document['shots'] = [dict(self.shot, id=f'SHOT-{n:03d}') for n in range(1, count + 1)]
        document['image_planning'] = {
            'schema_version': 1, 'story_file': 'creative/original.md',
            'story_sha256': sha256_file(self.project / 'creative/original.md'),
            'rationale': 'Synthetic structural fixture; no artistic assessment is asserted.',
            'shots': [{'shot_id': shot['id'], 'purpose': 'Synthetic narrative purpose.',
                       'entry_reason': 'Synthetic change of visible story state.'} for shot in document['shots']]}
        return document

    def test_count_is_not_a_runtime_quota_or_budget_target(self):
        for count in (1, 6, 15):
            with self.subTest(count=count):
                document = self.plan(count)
                atomic_json(self.part / 'shots.json', document)
                timeline = read_json(self.part / 'timeline.json')
                timeline['duration'] = 60
                atomic_json(self.part / 'timeline.json', timeline)
                self.assertEqual(problems(self.project, self.part), [])
                self.assertEqual(summary(self.project, self.part)['written_shot_count'], count)
        # This validator never authorizes the calls or expands the provider cap.
        self.assertFalse((self.project / 'production/delegation.json').exists())

    def test_every_shot_needs_a_purpose_and_reason_in_order(self):
        for change in ('missing', 'duplicate', 'reversed', 'purpose', 'entry_reason', 'rationale', 'shape'):
            document = self.plan(2)
            plan = document['image_planning']
            if change == 'missing': plan['shots'].pop()
            if change == 'duplicate': plan['shots'][1]['shot_id'] = 'SHOT-001'
            if change == 'reversed': plan['shots'].reverse()
            if change in ('purpose', 'entry_reason'): plan['shots'][0][change] = ' '
            if change == 'rationale': plan['rationale'] = ''
            if change == 'shape': document['image_planning'] = None
            with self.subTest(change=change):
                self.assertTrue(problems(self.project, self.part, document))

    def test_current_final_story_is_required_and_later_revision_stales_the_plan(self):
        document = self.plan()
        revised = self.project / 'creative/story-revised.md'
        atomic_text(revised, 'A quiet room, revised.\n')
        self.assertTrue(problems(self.project, self.part, document))
        document['image_planning'].update(story_file='creative/story-revised.md', story_sha256=sha256_file(revised))
        self.assertEqual(problems(self.project, self.part, document), [])
        atomic_text(revised, 'Another revision.\n')
        self.assertIn('different final-story', ' '.join(problems(self.project, self.part, document)))

    def test_legacy_plan_stays_usable_and_empty_scaffold_is_not_reported_complete(self):
        self.assertEqual(problems(self.project, self.part), [])
        self.assertEqual(written_problems(self.project, ['part_001']), [])
        self.assertEqual(summary(self.project, self.part)['status'], 'unrecorded')
        document = self.plan()
        document['shots'] = []
        atomic_json(self.part / 'shots.json', document)
        self.assertEqual(summary(self.project, self.part)['status'], 'draft')

    def test_preparation_rejects_incomplete_reasoning_before_writing_anything(self):
        document = self.plan()
        document['image_planning']['shots'] = []
        bundle = snapshot(self.project)
        bundle['artifacts'] = {'world/visual-bible.md': '# Proposed synthetic change\n',
                               'parts/part_001/shots.json': document}
        before = {name: (self.project / name).read_bytes() for name in bundle['artifacts']}
        with self.assertRaisesRegex(ValueError, 'every written shot'):
            apply(self.project, bundle)
        self.assertEqual(before, {name: (self.project / name).read_bytes() for name in before})

    def test_rationale_only_edit_preserves_derived_tracks_and_media(self):
        document = self.plan()
        document['timing_mode'] = 'speech_turns'
        atomic_json(self.part / 'shots.json', document)
        atomic_text(self.part / 'preview.mp4', 'Synthetic cache bytes, not a film.')
        before = (self.part / 'timeline.json').read_bytes()
        media = (self.part / 'preview.mp4').read_bytes()
        bundle = snapshot(self.project)
        document['image_planning']['rationale'] = 'Changed explanation; same synthetic shot plan.'
        bundle['artifacts'] = {'parts/part_001/shots.json': document}
        result = apply(self.project, bundle)
        self.assertNotIn('parts/part_001/timeline.json', result['files'])
        self.assertEqual((self.part / 'timeline.json').read_bytes(), before)
        self.assertEqual((self.part / 'preview.mp4').read_bytes(), media)

    def test_substantive_shot_edit_still_marks_derived_tracks_pending(self):
        document = self.plan()
        document['timing_mode'] = 'speech_turns'
        atomic_json(self.part / 'shots.json', document)
        bundle = snapshot(self.project)
        document['shots'][0]['visual_description'] = 'A necessary different synthetic story state.'
        bundle['artifacts'] = {'parts/part_001/shots.json': document}
        apply(self.project, bundle)
        self.assertEqual(read_json(self.part / 'timeline.json')['shots'], [])

    def test_next_returns_planning_as_agent_work_with_no_tool_call_or_question(self):
        document = self.plan()
        document['image_planning']['rationale'] = ''
        atomic_json(self.part / 'shots.json', document)
        self.authorize()
        with patch('studio.run_project') as run, patch('image_jobs.queue_request') as queue:
            packet = next_work(self.project)
        self.assertEqual(packet['actions'][0]['kind'], 'shot_plan')
        self.assertEqual(packet['actions'][0]['actor'], 'agent')
        self.assertIn('instructions/shot-planning.md', packet['actions'][0]['context'])
        self.assertEqual(packet['image_plan']['status'], 'needs_update')
        run.assert_not_called()
        queue.assert_not_called()

    def test_measured_holds_are_current_read_only_and_separate_from_image_calls(self):
        atomic_json(self.part / 'shots.json', self.plan())
        timeline = read_json(self.part / 'timeline.json')
        timeline['timing_source'] = {'shots_sha256': sha256_file(self.part / 'shots.json')}
        timeline['shots'][0].update(start=0, end=12.25)
        atomic_json(self.part / 'timeline.json', timeline)
        self.authorize()
        before = {str(p): p.read_bytes() for p in self.project.rglob('*') if p.is_file()}
        context = next_work(self.project)['image_plan']
        self.assertEqual(context['timing_basis'], 'measured_speech')
        self.assertEqual(context['holds'], [{'shot_id': 'SHOT-001', 'seconds': 12.25}])
        self.assertEqual(context['distinct_timeline_image_files'], 1)
        self.assertEqual(context['missing_timeline_image_files'], 0)
        self.assertEqual(context['registered_reference_files'], 1)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.project.rglob('*') if p.is_file()})

    def test_stale_timing_and_manual_timing_are_never_mislabeled_as_measured(self):
        document = self.plan()
        atomic_json(self.part / 'shots.json', document)
        timeline = read_json(self.part / 'timeline.json')
        timeline['timing_source'] = {'shots_sha256': 'old plan hash'}
        atomic_json(self.part / 'timeline.json', timeline)
        self.assertEqual(summary(self.project, self.part)['holds'], [])
        self.assertEqual(summary(self.project, self.part)['timing_basis'], 'pending_current_timing')
        document['timing_mode'] = 'manual'
        atomic_json(self.part / 'shots.json', document)
        context = summary(self.project, self.part)
        self.assertEqual(context['timing_basis'], 'authored_manual')
        self.assertEqual(context['holds'][0]['seconds'], 1)
        timeline['shots'][0]['end'] = True
        atomic_json(self.part / 'timeline.json', timeline)
        self.assertEqual(summary(self.project, self.part)['holds'], [])


if __name__ == '__main__':
    unittest.main()
