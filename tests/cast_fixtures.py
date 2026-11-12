"""Mechanical cast data for isolated tests, never real character-design inspection."""
from studio_common import ROOT, atomic_json, atomic_text, read_json, sha256_file


def install_profile(project, identity='CHAR-001', style=None, reference=None, ready=False):
    from cast import CHECKS, design_version, record_review, render_profile
    registry = read_json(project / 'continuity/entities.json')
    style = style or next(iter(registry['styles']))
    profile = read_json(ROOT / 'templates/cast-profile.example.json')
    profile.update(name='Synthetic ' + identity, role='SYNTHETIC role: a nervous traveller; narrow silhouette, blue coat.',
                   style_id=style, style_revision=registry['styles'][style]['revision'])
    data = read_json(project / 'world/cast.json', {'schema_version': 1, 'characters': {}})
    data['characters'][identity] = profile
    atomic_json(project / 'world/cast.json', data)
    name = 'world/characters/' + identity + '.md'
    atomic_text(project / name, render_profile(identity, profile))
    record = registry.setdefault('characters', {}).setdefault(identity, {})
    record.update(canonical_file=name, revision='r1', style_id=style,
                  reference_paths=[reference] if reference else [])
    atomic_json(project / 'continuity/entities.json', registry)
    if ready:
        record_review(project, {'character_id': identity, 'design_version': design_version(project, identity),
            'images': [reference], 'image_sha256': {reference: sha256_file(project / reference)},
            'verdict': 'passed', 'reviewer': 'synthetic unit fixture',
            'notes': 'SYNTHETIC mechanical coverage fixture; no actual artistic or human approval.', 'checks': list(CHECKS),
            'coverage': {group: {key: reference for key in profile[group]} for group in ('views', 'expressions', 'poses')}})
    return profile
