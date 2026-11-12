"""Complete cast profiles, genuine record bindings, revision history and safe UI requests."""
import copy
import json
from pathlib import Path
import shutil
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import uuid
from unittest.mock import patch

import test_workflow as fixtures
from cast_fixtures import install_profile
from cast import CHECKS, design_version, plan_problems, record_review, request_change, revise, sheet_problems
from production_plan import apply, snapshot
from production_next import next_work
from studio_common import ROOT, atomic_json, atomic_text, read_json, sha256_file
from visual_continuity import binding_problems


class CastTests(unittest.TestCase):
    setUp = fixtures.FastFixture.setUp
    authorize = fixtures.FastFixture.authorize

    def cast(self):
        profile = install_profile(self.project)
        shot = read_json(self.part / 'shots.json')
        shot['shots'][0].update(character_ids=['CHAR-001'], story_time=0, entity_states={})
        atomic_json(self.part / 'shots.json', shot)
        timeline = read_json(self.part / 'timeline.json')
        timeline['shots'][0].update(character_ids=['CHAR-001'], story_time=0, entity_states={})
        atomic_json(self.part / 'timeline.json', timeline)
        return profile

    def sheet(self):
        from PIL import Image
        path = self.project / 'references/characters/actual-sheet.png'
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (128, 192), 'blue').save(path)
        return path.relative_to(self.project).as_posix()

    def review(self, path):
        profile = read_json(self.project / 'world/cast.json')['characters']['CHAR-001']
        return {'character_id': 'CHAR-001', 'design_version': design_version(self.project, 'CHAR-001'), 'images': [path],
                'image_sha256': {path: sha256_file(self.project / path)}, 'verdict': 'passed',
                'reviewer': 'synthetic test fixture', 'notes': 'Synthetic shape/coverage checks only; no actual artistic inspection claim.',
                'checks': list(CHECKS), 'coverage': {group: {name: path for name in profile[group]} for group in ('views', 'expressions', 'poses')}}

    def test_prepare_authors_single_authority_and_generates_matching_documents(self):
        profile = read_json(ROOT / 'templates/cast-profile.example.json')
        bundle = snapshot(self.project)
        bundle['artifacts'] = {'world/cast.json': {'schema_version': 1, 'characters': {'CHAR-001': profile}}}
        apply(self.project, bundle)
        self.assertEqual(plan_problems(self.project), [])
        self.assertIn('restrained grief', (self.project / 'world/characters/CHAR-001.md').read_text(encoding='utf-8'))
        self.assertEqual(read_json(self.project / 'continuity/entities.json')['characters']['CHAR-001']['style_id'], 'STYLE-001')

    def test_missing_character_bindings_cannot_silently_bypass_reference_checks(self):
        self.cast()
        document = read_json(self.part / 'shots.json')
        document['shots'][0].pop('character_ids')
        document['shots'][0]['visual_description'] = 'A scene containing CHAR-001.'
        atomic_json(self.part / 'shots.json', document)
        self.assertIn('character_ids', ' '.join(binding_problems(self.project)))
        self.assertIn('structured', ' '.join(binding_problems(self.project)))

    def test_known_state_fields_and_story_time_cannot_be_omitted(self):
        self.cast()
        registry = read_json(self.project / 'continuity/entities.json')
        registry['characters']['CHAR-001']['initial_state'] = {'coat': 'blue'}
        atomic_json(self.project / 'continuity/entities.json', registry)
        self.assertIn('all known state fields', ' '.join(binding_problems(self.project)))
        document = read_json(self.part / 'shots.json'); document['shots'][0].pop('story_time')
        atomic_json(self.part / 'shots.json', document)
        self.assertIn('story_time', ' '.join(binding_problems(self.project)))

    def test_generic_or_stale_profiles_do_not_pass_and_no_cast_sheet_is_auto_approved(self):
        self.cast()
        self.assertTrue(sheet_problems(self.project, 'CHAR-001'))
        data = read_json(self.project / 'world/cast.json')
        data['characters']['CHAR-001']['style_revision'] = 'r9'
        atomic_json(self.project / 'world/cast.json', data)
        self.assertIn('current style', ' '.join(plan_problems(self.project)))
        self.assertFalse((self.project / 'production/cast-reviews.json').exists())

    def test_review_requires_actual_expression_pose_view_coverage_and_inspected_bytes(self):
        self.cast(); path = self.sheet()
        original = self.review(path)
        for field in ('views', 'expressions', 'poses'):
            review = copy.deepcopy(original); review['coverage'][field] = {}
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'coverage'):
                record_review(self.project, review)
        review = copy.deepcopy(original); review['image_sha256'][path] = 'different'
        with self.assertRaisesRegex(ValueError, 'exact inspected'):
            record_review(self.project, review)
        record_review(self.project, original)
        self.assertEqual(sheet_problems(self.project, 'CHAR-001'), [])
        self.assertTrue(all(item['status'] == 'draft' for item in read_json(self.project / 'approvals.json')['gates'].values()))

    def test_changed_sheet_bytes_stale_the_review_and_gallery_cannot_be_cast_identity(self):
        self.cast(); path = self.sheet()
        record_review(self.project, self.review(path))
        from PIL import Image
        Image.new('RGB', (128, 192), 'purple').save(self.project / path)
        self.assertTrue(sheet_problems(self.project, 'CHAR-001'))
        target = self.project / 'references/characters/gallery.png'
        shutil.copy2(ROOT / 'references/style/visual-preferences/images/storybook-stickman.png', target)
        with self.assertRaisesRegex(ValueError, 'not a story-specific cast'):
            record_review(self.project, self.review('references/characters/gallery.png'))

    def test_next_schedules_cast_preparation_as_agent_work_without_signoff(self):
        self.cast(); self.authorize()
        packet = next_work(self.project)
        self.assertEqual(packet['actions'][0]['actor'], 'agent')
        self.assertIn(packet['actions'][0]['kind'], ('preflight', 'reference'))
        registry = read_json(self.project / 'continuity/entities.json'); registry['characters']['CHAR-001']['style_id'] = 'STYLE-999'
        atomic_json(self.project / 'continuity/entities.json', registry)
        self.assertEqual(next_work(self.project)['actions'][0]['kind'], 'cast_plan')

    def test_change_request_is_idempotent_and_stale_design_submission_writes_nothing(self):
        self.cast(); version = design_version(self.project, 'CHAR-001')
        identity = str(uuid.uuid4())
        first = request_change(self.project, 'CHAR-001', 'Give the coat silver buttons.', version, 'SYNTHETIC unit request', identity)
        self.assertEqual(first, request_change(self.project, 'CHAR-001', 'Give the coat silver buttons.', version, 'SYNTHETIC unit request', identity))
        self.assertEqual(len(read_json(self.project / 'production/cast-change-requests.json')['requests']), 1)
        with self.assertRaisesRegex(ValueError, 'design changed'):
            request_change(self.project, 'CHAR-001', 'Other change.', 'stale', 'SYNTHETIC request')

    def test_revision_preserves_images_and_documents_and_identifies_affected_shots(self):
        profile = self.cast(); path = self.sheet()
        record_review(self.project, self.review(path))
        old_document = (self.project / 'world/characters/CHAR-001.md').read_bytes()
        old_image = (self.project / path).read_bytes()
        request = request_change(self.project, 'CHAR-001', 'Change the coat to silver.', design_version(self.project, 'CHAR-001'), 'SYNTHETIC unit request')
        profile['wardrobe'] = 'Silver coat; preserve all other synthetic details.'
        result = revise(self.project, 'CHAR-001', profile, request['id'])
        self.assertEqual(result['revision'], 'r2')
        self.assertEqual(result['affected_shots'], ['part_001/SHOT-001'])
        record = read_json(self.project / 'continuity/entities.json')['characters']['CHAR-001']
        self.assertEqual(record['reference_paths'], [])
        self.assertIn(path, record['previous_reference_paths'])
        self.assertEqual((self.project / path).read_bytes(), old_image)
        self.assertEqual((self.project / 'production/cast-revisions' / request['id'] / 'before/world/characters/CHAR-001.md').read_bytes(), old_document)
        self.assertTrue(sheet_problems(self.project, 'CHAR-001'))

    def test_inspected_character_cannot_be_silently_changed_through_batch_prepare(self):
        self.cast(); path = self.sheet(); record_review(self.project, self.review(path))
        data = read_json(self.project / 'world/cast.json'); data['characters']['CHAR-001']['appearance'] = 'Different face.'
        bundle = snapshot(self.project); bundle['artifacts'] = {'world/cast.json': data}
        with self.assertRaisesRegex(ValueError, 'cast revise'):
            apply(self.project, bundle)

    def test_wrong_branch_change_request_does_not_touch_the_project(self):
        self.cast()
        with patch('story_git.require_story_branch', side_effect=ValueError('wrong branch')), self.assertRaisesRegex(ValueError, 'wrong branch'):
            request_change(self.project, 'CHAR-001', 'Change hair.', 'any', 'SYNTHETIC unit request')
        self.assertFalse((self.project / 'production/cast-change-requests.json').exists())

    def test_a_real_legacy_character_request_can_create_its_complete_current_profile(self):
        registry = read_json(self.project / 'continuity/entities.json')
        registry['characters']['CHAR-001'] = {'canonical_file': 'world/characters/CHAR-001.md', 'revision': 'r1', 'reference_paths': []}
        atomic_json(self.project / 'continuity/entities.json', registry)
        old = '# Legacy character, original requested identity.\n'
        atomic_text(self.project / 'world/characters/CHAR-001.md', old)
        request = request_change(self.project, 'CHAR-001', 'SYNTHETIC change to the older character.', design_version(self.project, 'CHAR-001'), 'SYNTHETIC unit request')
        profile = read_json(ROOT / 'templates/cast-profile.example.json')
        result = revise(self.project, 'CHAR-001', profile, request['id'])
        self.assertEqual(result['revision'], 'r2')
        self.assertEqual(plan_problems(self.project), [])
        self.assertEqual((self.project / 'production/cast-revisions' / request['id'] / 'before/world/characters/CHAR-001.md').read_text(), old)

    def test_revision_requires_real_pending_request_and_preserves_a_concurrent_edit(self):
        profile = self.cast()
        with self.assertRaisesRegex(ValueError, 'actual pending'):
            revise(self.project, 'CHAR-001', profile, str(uuid.uuid4()))
        from cast import _capture, _publish
        expected = _capture(self.project, ['world/cast.json'])
        atomic_text(self.project / 'world/cast.json', '{"schema_version":1,"characters":{},"concurrent":true}\n')
        with self.assertRaisesRegex(ValueError, 'Concurrent cast edit'):
            _publish(self.project, {'world/cast.json': {'schema_version': 1, 'characters': {}}}, str(uuid.uuid4()), expected)
        self.assertTrue(read_json(self.project / 'world/cast.json')['concurrent'])

    def test_cast_transactions_cannot_overwrite_story_sources_or_escape_revision_history(self):
        from cast import _publish
        for name in ('creative/original.md', '../outside.txt', 'production/delegation.json'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'cannot edit'):
                _publish(self.project, {name: 'invalid'}, str(uuid.uuid4()))
        with self.assertRaisesRegex(ValueError, 'UUID'):
            _publish(self.project, {'world/cast.json': {}}, '../../outside')

    def test_event_driven_variants_also_need_actual_coverage(self):
        profile = self.cast()
        data = read_json(self.project / 'world/cast.json')
        profile['state_variants'] = {'EVENT-001': 'Coat wet after the river crossing.'}
        data['characters']['CHAR-001'] = profile
        atomic_json(self.project / 'world/cast.json', data)
        from cast import render_profile
        atomic_text(self.project / 'world/characters/CHAR-001.md', render_profile('CHAR-001', profile))
        path = self.sheet(); review = self.review(path)
        with self.assertRaisesRegex(ValueError, 'state_variants'):
            record_review(self.project, review)
        review['coverage']['state_variants'] = {'EVENT-001': path}
        record_review(self.project, review)
        self.assertEqual(sheet_problems(self.project, 'CHAR-001'), [])

    def test_unknown_provider_outcome_precedes_a_new_design_revision(self):
        self.cast(); self.authorize()
        request_change(self.project, 'CHAR-001', 'SYNTHETIC change.', design_version(self.project, 'CHAR-001'), 'SYNTHETIC unit request')
        atomic_json(self.project / 'production/image-jobs/pending.json', {'status': 'requesting'})
        self.assertEqual(next_work(self.project)['actions'][0]['kind'], 'reconcile_provider')

    def test_focused_sheet_requests_are_distinct_and_do_not_invent_unused_variants(self):
        from image_jobs import compile_reference
        from studio_common import fingerprint
        self.cast(); self.authorize()
        identity = compile_reference(self.project, 'CHAR-001', .1, sheet='identity')
        expressions = compile_reference(self.project, 'CHAR-001', .1, sheet='expressions')
        self.assertIn('FOCUSED IDENTITY SHEET ONLY', identity['tool_request']['arguments']['prompt'])
        self.assertIn('FOCUSED EXPRESSIONS SHEET ONLY', expressions['tool_request']['arguments']['prompt'])
        self.assertNotEqual(fingerprint(identity), fingerprint(expressions))
        with self.assertRaisesRegex(ValueError, 'No event-driven'):
            compile_reference(self.project, 'CHAR-001', .1, sheet='variants')

    def test_a_passed_label_or_copied_receipt_without_coverage_is_not_sufficient(self):
        self.cast(); path = self.sheet(); record_review(self.project, self.review(path))
        data = read_json(self.project / 'production/cast-reviews.json')
        data['reviews']['CHAR-001']['coverage']['poses'] = {}
        atomic_json(self.project / 'production/cast-reviews.json', data)
        self.assertIn('poses coverage', ' '.join(sheet_problems(self.project, 'CHAR-001')))
        from cast_fixtures import install_profile
        install_profile(self.project, 'CHAR-002')
        self.assertNotEqual(design_version(self.project, 'CHAR-001'), design_version(self.project, 'CHAR-002'))

    def test_directly_registering_a_gallery_image_does_not_bypass_identity_rules(self):
        self.cast()
        path = self.project / 'references/characters/fake-sheet.png'
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'references/style/visual-preferences/images/storybook-stickman.png', path)
        registry = read_json(self.project / 'continuity/entities.json')
        registry['characters']['CHAR-001']['reference_paths'] = ['references/characters/fake-sheet.png']
        atomic_json(self.project / 'continuity/entities.json', registry)
        self.assertIn('not a character identity sheet', ' '.join(sheet_problems(self.project, 'CHAR-001')))


class CastHttpTests(unittest.TestCase):
    cast = CastTests.cast
    sheet = CastTests.sheet
    review = CastTests.review

    def setUp(self):
        fixtures.FastFixture.setUp(self)
        target = self.base / 'stories/fixture'
        shutil.copytree(self.project, target)
        self.project, self.part = target, target / 'parts/part_001'
        self.cast()
        from monitor import make_server
        from progress_snapshot import Monitor
        self.monitor = Monitor([self.base], discover=False)
        self.info = self.monitor.projects()[0]
        self.server = make_server(self.monitor, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)

    def get(self):
        with urlopen(self.url + '/api/status?project=' + self.info['id'], timeout=5) as response:
            return json.load(response)

    def post(self, body, origin=None, token=None):
        request = Request(self.url + '/api/cast-change', data=json.dumps(body).encode(), method='POST',
                          headers={'Content-Type': 'application/json', 'Origin': origin or self.url,
                                   'X-Studio-Cast-Token': token or ''})
        return urlopen(request, timeout=5)

    def body(self):
        return {'project': self.info['id'], 'character_id': 'CHAR-001', 'request': 'SYNTHETIC test request: adjust the coat.',
                'base_version': design_version(self.project, 'CHAR-001'), 'id': str(uuid.uuid4())}

    def test_live_cast_snapshot_is_read_only_and_does_not_claim_missing_sheets_exist(self):
        before = {str(p): p.read_bytes() for p in self.project.rglob('*') if p.is_file()}
        data = self.get()
        self.assertEqual(data['cast']['total'], 1)
        self.assertEqual(data['cast']['ready'], 0)
        self.assertEqual(data['cast']['characters'][0]['state'], 'sheet_missing')
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.project.rglob('*') if p.is_file()})

    def test_explicit_same_origin_request_is_persisted_once_without_editing_canonical_data(self):
        token = self.get()['cast_control']['token']
        before = (self.project / 'world/cast.json').read_bytes()
        body = self.body()
        for _ in range(2):
            with self.post(body, token=token) as response:
                self.assertEqual(response.status, 201)
        self.assertEqual(len(read_json(self.project / 'production/cast-change-requests.json')['requests']), 1)
        self.assertEqual((self.project / 'world/cast.json').read_bytes(), before)
        self.assertEqual(self.get()['cast']['pending_changes'], 1)

    def test_cross_origin_missing_token_and_stale_design_requests_are_rejected(self):
        token = self.get()['cast_control']['token']
        for origin, nonce, expected in (('https://outside.example', token, 403), (self.url, '', 403)):
            with self.subTest(origin=origin), self.assertRaises(HTTPError) as error:
                self.post(self.body(), origin=origin, token=nonce)
            self.assertEqual(error.exception.code, expected)
        body = self.body(); body['base_version'] = 'old version'
        with self.assertRaises(HTTPError) as error:
            self.post(body, token=token)
        self.assertEqual(error.exception.code, 409)
        self.assertFalse((self.project / 'production/cast-change-requests.json').exists())

    def test_only_registered_current_or_preserved_reference_images_can_be_served(self):
        path = self.sheet(); record_review(self.project, self.review(path))
        image = self.get()['cast']['characters'][0]['images'][0]
        with urlopen(self.url + image['url'], timeout=5) as response:
            self.assertTrue(response.headers['Content-Type'].startswith('image/'))
            self.assertEqual(response.read(), (self.project / path).read_bytes())
        with self.assertRaises(HTTPError):
            urlopen(self.url + '/api/cast-image?project=' + self.info['id'] + '&character=../../world&v=anything', timeout=5)

    def test_incompatible_profile_shapes_remain_visible_as_needing_a_profile(self):
        data = read_json(self.project / 'world/cast.json')
        data['characters']['CHAR-001']['expressions'] = {'neutral': {'unsupported_nested_shape': True}}
        atomic_json(self.project / 'world/cast.json', data)
        character = self.get()['cast']['characters'][0]
        self.assertIsNone(character['profile'])
        self.assertEqual(character['state'], 'profile_missing')
        self.assertTrue(character['issues'])
