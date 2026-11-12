"""Exact style selection, reference roles and current written-shot request boundaries."""
import shutil
import unittest

import test_workflow as fixtures
from image_jobs import compile_reference, compile_request, import_result, queue_request, start_request
from quality import image_review_context
from studio_common import ROOT, atomic_json, atomic_text, executable, read_json, sha256_file


class ImageReferenceTests(unittest.TestCase):
    setUp = fixtures.FastFixture.setUp
    authorize = fixtures.FastFixture.authorize

    def snapshot(self, name='selected.png', color='blue', source=None):
        from PIL import Image
        target = self.project / 'references/style' / name
        if source:
            shutil.copy2(source, target)
        else:
            Image.new('RGB', (64, 96), color).save(target)
        path = self.project / 'references/style/manifest.json'
        manifest = read_json(path)
        row = {'id': name, 'snapshot_path': target.relative_to(self.project).as_posix(),
               'source_path': 'X:/old/references/' + name, 'sha256': sha256_file(target), 'role': 'visual treatment only'}
        manifest['references'].append(row)
        atomic_json(path, manifest)
        return target

    def character(self, identity='CHAR-001', reference=None, style=None):
        from cast_fixtures import install_profile
        install_profile(self.project, identity, style=style, reference=reference, ready=bool(reference))
        if style is None and len(read_json(self.project / 'continuity/entities.json')['styles']) > 1:
            registry = read_json(self.project / 'continuity/entities.json')
            registry['characters'][identity].pop('style_id')
            atomic_json(self.project / 'continuity/entities.json', registry)

    def written(self, **fields):
        fields.update(story_time=0, entity_states={})
        document = read_json(self.part / 'shots.json')
        document['shots'][0].update(fields)
        atomic_json(self.part / 'shots.json', document)
        timeline = read_json(self.part / 'timeline.json')
        timeline['shots'][0].update(fields)
        atomic_json(self.part / 'timeline.json', timeline)
        return document['shots'][0]

    def test_style_reference_automatically_uses_the_exact_selected_snapshot(self):
        selected = self.snapshot()
        registry = read_json(self.project / 'continuity/entities.json')
        registry['styles']['STYLE-001']['reference_paths'] = []
        atomic_json(self.project / 'continuity/entities.json', registry)
        self.authorize()
        request = compile_reference(self.project, 'STYLE-001', .1)
        self.assertEqual(request['tool_request']['arguments']['referenced_image_paths'], [str(selected)])
        self.assertEqual(request['reference_hashes'][str(selected)], sha256_file(selected))
        self.assertIn('Image 1: STYLE-001', request['tool_request']['arguments']['prompt'])
        self.assertIn('visual treatment only', request['tool_request']['arguments']['prompt'])
        self.assertFalse((self.project / 'production/image-jobs').exists())

    def test_new_character_reference_inherits_the_style_proof_and_selected_treatment(self):
        selected = self.snapshot()
        self.character()
        self.authorize()
        request = compile_reference(self.project, 'CHAR-001', .1)
        self.assertIn(str(selected), request['tool_request']['arguments']['referenced_image_paths'])
        self.assertIn(str(self.project / 'references/style/fixture.png'), request['reference_hashes'])
        prompt = request['tool_request']['arguments']['prompt']
        self.assertIn('nervous traveller', prompt)
        self.assertIn('Do not substitute people or scenery from treatment examples', prompt)

    def test_shared_cast_reference_is_attached_once_with_both_identity_roles(self):
        from PIL import Image
        shared = self.project / 'references/characters/shared.png'
        shared.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', (64, 96), 'blue').save(shared)
        for identity in ('CHAR-001', 'CHAR-002'):
            self.character(identity, 'references/characters/shared.png')
        self.written(character_ids=['CHAR-001', 'CHAR-002'])
        self.authorize()
        request = compile_request(self.project, 'part_001', 'SHOT-001', .1)
        self.assertEqual(len(request['tool_request']['arguments']['referenced_image_paths']), 2)
        binding = next(row for row in request['reference_bindings'] if row['path'] == str(shared))
        self.assertEqual([use['entity_id'] for use in binding['roles']], ['CHAR-001', 'CHAR-002'])
        self.assertIn('Image 2: CHAR-001', request['tool_request']['arguments']['prompt'])

    def test_storybook_stickman_uses_accepted_pixels_instead_of_the_old_line_leg_prompt(self):
        self.snapshot(source=ROOT / 'references/style/visual-preferences/images/storybook-stickman.png')
        self.authorize()
        prompt = compile_reference(self.project, 'STYLE-001', .1)['tool_request']['arguments']['prompt']
        self.assertIn('clothed legs', prompt)
        self.assertIn('thin black line arms', prompt)
        self.assertNotIn('thin black LINE arms and legs', prompt)

    def test_changed_selected_snapshot_is_rejected_before_a_request_is_queued(self):
        selected = self.snapshot()
        selected.write_bytes((self.project / 'references/style/fixture.png').read_bytes())
        self.authorize()
        with self.assertRaisesRegex(ValueError, 'exact recorded path/hash'):
            compile_reference(self.project, 'STYLE-001', .1)
        self.assertFalse((self.project / 'production/image-jobs').exists())

    def test_historical_source_alias_resolves_to_its_own_snapshot_not_todays_gallery(self):
        selected = self.snapshot()
        manifest_path = self.project / 'references/style/manifest.json'
        manifest = read_json(manifest_path)
        alias = 'references/style/visual-preferences/images/storybook-stickman.png'
        manifest['references'][0]['source_path'] = 'X:/prior-checkout/' + alias
        atomic_json(manifest_path, manifest)
        registry = read_json(self.project / 'continuity/entities.json')
        registry['styles']['STYLE-001']['inspiration_paths'] = [alias]
        atomic_json(self.project / 'continuity/entities.json', registry)
        self.authorize()
        request = compile_reference(self.project, 'STYLE-001', .1)
        self.assertIn(str(selected), request['reference_hashes'])
        self.assertNotIn(str(ROOT / alias), request['reference_hashes'])
        self.assertNotEqual(sha256_file(selected), sha256_file(ROOT / alias))

    def test_multiple_historical_snapshots_require_explicit_selection(self):
        selected = self.snapshot()
        unused = self.snapshot('other.png', 'green')
        self.authorize()
        with self.assertRaisesRegex(ValueError, 'historical snapshots are ambiguous'):
            compile_reference(self.project, 'STYLE-001', .1)
        registry = read_json(self.project / 'continuity/entities.json')
        registry['styles']['STYLE-001']['inspiration_paths'] = ['references/style/selected.png']
        atomic_json(self.project / 'continuity/entities.json', registry)
        request = compile_reference(self.project, 'STYLE-001', .1)
        self.assertIn(str(selected), request['reference_hashes'])
        self.assertNotIn(str(unused), request['reference_hashes'])

    def test_multiple_styles_bind_the_character_to_one_exact_style(self):
        registry = read_json(self.project / 'continuity/entities.json')
        atomic_text(self.project / 'world/style-two.md', 'SYNTHETIC second medium, angular forms.\n')
        registry['styles']['STYLE-002'] = dict(registry['styles']['STYLE-001'], canonical_file='world/style-two.md')
        atomic_json(self.project / 'continuity/entities.json', registry)
        self.character()
        self.authorize()
        with self.assertRaisesRegex(ValueError, 'style_id'):
            compile_reference(self.project, 'CHAR-001', .1)
        self.character(style='STYLE-002')
        request = compile_reference(self.project, 'CHAR-001', .1)
        self.assertIn('world/style-two.md', request['canonical_inputs'])
        self.assertNotIn('world/visual-bible.md', request['canonical_inputs'])

    def test_changed_shot_frame_or_scoped_entity_prevents_starting_an_old_prompt(self):
        self.authorize()
        request = compile_request(self.project, 'part_001', 'SHOT-001', .1)
        path, _ = queue_request(self.project, request)
        for name, mutate in [
            ('parts/part_001/shots.json', lambda value: value['shots'][0].update(visual_description='Changed synthetic action.')),
            ('parts/part_001/timeline.json', lambda value: value.update(width=128)),
            ('continuity/entities.json', lambda value: value['styles']['STYLE-001'].update(reference_note='Changed contribution.'))]:
            target = self.project / name
            before = target.read_bytes()
            value = read_json(target); mutate(value); atomic_json(target, value)
            try:
                with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'prompt context changed'):
                    start_request(self.project, path)
                self.assertEqual(read_json(path)['status'], 'pending')
            finally:
                target.write_bytes(before)

    def test_unrelated_entity_edit_does_not_invalidate_the_selected_shot(self):
        self.authorize()
        request = compile_request(self.project, 'part_001', 'SHOT-001', .1)
        path, _ = queue_request(self.project, request)
        registry = read_json(self.project / 'continuity/entities.json')
        atomic_text(self.project / 'world/props/PROP-099.md', 'Unseen synthetic background prop.\n')
        registry['props']['PROP-099'] = {'canonical_file': 'world/props/PROP-099.md', 'revision': 'r1', 'reference_paths': []}
        atomic_json(self.project / 'continuity/entities.json', registry)
        self.assertEqual(start_request(self.project, path)['status'], 'requesting')

    def test_stale_result_cannot_replace_current_shot_but_source_bytes_are_preserved(self):
        self.authorize()
        path, _ = queue_request(self.project, compile_request(self.project, 'part_001', 'SHOT-001', .1))
        source = self.project / 'references/style/fixture.png'
        original = source.read_bytes()
        before = (self.part / 'timeline.json').read_bytes()
        written = read_json(self.part / 'shots.json')
        written['shots'][0]['camera_direction'] = 'New synthetic angle facing south.'
        atomic_json(self.part / 'shots.json', written)
        with self.assertRaisesRegex(ValueError, 'prompt context changed'):
            import_result(self.project, path, source, 'synthetic provider')
        self.assertEqual((self.part / 'timeline.json').read_bytes(), before)
        self.assertEqual(source.read_bytes(), original)

    def test_additional_selected_style_bytes_are_bound_to_visual_review(self):
        selected = self.snapshot()
        before = image_review_context(self.project, 'part_001', self.shot)
        from PIL import Image
        Image.new('RGB', (64, 96), 'green').save(selected)
        manifest = read_json(self.project / 'references/style/manifest.json')
        manifest['references'][0]['sha256'] = sha256_file(selected)
        atomic_json(self.project / 'references/style/manifest.json', manifest)
        self.assertNotEqual(image_review_context(self.project, 'part_001', self.shot), before)

    def test_visual_review_hashes_survive_copying_the_project(self):
        self.snapshot()
        before = image_review_context(self.project, 'part_001', self.shot)
        portable = self.base / 'portable'
        shutil.copytree(self.project, portable)
        self.assertEqual(image_review_context(portable, 'part_001', self.shot), before)

    @unittest.skipUnless(executable('ffmpeg'), 'Actual FFmpeg required')
    def test_export_includes_extra_selected_reference_and_provenance(self):
        from delivery import export_part, record_playback
        from quality import record_image_review
        from studio import run_project
        from workflow import record_preview
        selected = self.snapshot()
        self.authorize()
        run_project(self.project, stages=('mix', 'render', 'qa'))
        record_image_review(self.project, 'part_001', 'SHOT-001', 'passed', 'SYNTHETIC technical fixture only.', 'unit fixture')
        record_preview(self.project, 'part_001', 'SYNTHETIC preview receipt; no actual story decision.', 'unit fixture')
        run_project(self.project, profile='final', stages=('mix', 'render', 'qa'))
        record_playback(self.project, 'part_001', 'unit fixture', 'SYNTHETIC mechanical export; no artistic or listening claim.', True)
        exported = export_part(self.project, 'part_001', 'fixture')
        manifest = read_json(exported / 'manifest.json')['files']
        name = selected.relative_to(self.project).as_posix()
        self.assertIn(name, manifest)
        self.assertEqual(sha256_file(exported / name), sha256_file(selected))
        self.assertIn('references/style/manifest.json', manifest)


class CatalogFidelityTests(unittest.TestCase):
    def test_observed_traits_are_bound_to_all_eight_exact_current_images(self):
        base = ROOT / 'references/style/visual-preferences'
        catalog = read_json(base / 'style-catalog.json')['styles']
        traits = {row['id']: row for row in read_json(base / 'fidelity.json')['styles']}
        self.assertEqual(len(catalog), 8)
        self.assertEqual(set(traits), {row['id'] for row in catalog})
        for row in catalog:
            self.assertEqual(sha256_file(base / row['file']), traits[row['id']]['sha256'])
            self.assertEqual(row['sha256'], traits[row['id']]['sha256'])
            self.assertTrue(traits[row['id']]['traits'])


if __name__ == '__main__':
    unittest.main()
