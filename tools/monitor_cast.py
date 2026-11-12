"""Read-only cast progress and registered image routes for the local monitor."""
from pathlib import Path
from urllib.parse import urlencode

from cast import TEXT_FIELDS, design_version, plan_problems, sheet_problems
from progress_snapshot import public_text
from studio_common import hash_session


@hash_session()
def cast_view(reader, info):
    project = Path(info['path'])
    registry = reader.json(project / 'continuity/entities.json')
    profiles = reader.json(project / 'world/cast.json').get('characters', {})
    reviews = reader.json(project / 'production/cast-reviews.json').get('reviews', {})
    requests = reader.json(project / 'production/cast-change-requests.json').get('requests', [])
    jobs = [reader.json(path) for path in (project / 'production/image-jobs').glob('*.json')]
    characters, events = [], []
    for identity, entity in registry.get('characters', {}).items():
        raw_profile = profiles.get(identity)
        profile = raw_profile if isinstance(raw_profile, dict) else None
        display_profile = profile if (isinstance(profile, dict) and all(isinstance(profile.get(field), str) for field in (*TEXT_FIELDS, 'revision', 'style_id', 'style_revision'))
                                       and all(isinstance(profile.get(field), list) for field in ('identity_anchors', 'views'))
                                       and all(isinstance(value, str) for field in ('identity_anchors', 'views') for value in profile[field])
                                       and all(isinstance(profile.get(field), dict) for field in ('expressions', 'poses'))
                                       and isinstance(profile.get('state_variants', {}), dict)
                                       and all(isinstance(key, str) and isinstance(value, str) for field in ('expressions', 'poses', 'state_variants')
                                               for key, value in profile.get(field, {}).items())) else None
        source = project / entity.get('canonical_file', '')
        text = source.read_text(encoding='utf-8-sig') if source.is_file() else ''
        name = (profile or {}).get('name') or (text.splitlines()[0].split('—', 1)[-1].strip() if text else identity)
        issues = plan_problems(project, [identity])
        review_current = False
        state = 'profile_missing' if display_profile is None else 'stale' if issues else 'sheet_missing' if not entity.get('reference_paths') else 'awaiting_review'
        review = reviews.get(identity, {})
        if not issues and entity.get('reference_paths'):
            problems = sheet_problems(project, identity)
            missing = any(not (project / name).is_file() for name in entity['reference_paths'])
            state = 'ready' if not problems else 'sheet_missing' if missing else 'failed' if review.get('verdict') == 'failed' else 'stale' if review else 'awaiting_review'
            review_current = not problems
            issues += problems
        related = [item for item in requests if item.get('character_id') == identity]
        try:
            version = design_version(project, identity)
        except (OSError, ValueError, KeyError):
            version = None
        pending = [item for item in related if item.get('status') == 'requested']
        if pending:
            state = 'changes_requested'
        active = [job for job in jobs if job.get('kind') == 'reference' and job.get('entity_id') == identity
                  and (job.get('cast_design_version') == version or (not job.get('cast_design_version') and
                       job.get('canonical_inputs', {}).get(entity.get('canonical_file')) == reader.digest(project / entity.get('canonical_file', ''))))]
        unknown = [job for job in active if job.get('status') == 'needs_attention' and job.get('outcome_known') is not True]
        if unknown:
            state = 'unknown_result'
        elif any(job.get('status') == 'requesting' for job in active):
            state = 'provider_wait'
        elif state != 'ready' and active and max(active, key=lambda job: job.get('created_at', '')).get('status') in ('failed', 'needs_attention'):
            state = 'failed'
        images = []
        for previous, paths in ((False, entity.get('reference_paths', [])), (True, entity.get('previous_reference_paths', []))):
            for path in paths:
                source = (project / path).resolve()
                digest = reader.digest(source) if source.is_relative_to(project.resolve()) else None
                if not digest:
                    continue
                images.append({'path': path, 'sha256': digest, 'previous': previous,
                               'url': '/api/cast-image?' + urlencode({'project': info['id'], 'character': identity, 'v': digest})})
        linked = [part.name + '/' + shot['id'] for part in (project / 'parts').glob('part_*')
                  for shot in reader.json(part / 'shots.json').get('shots', []) if identity in shot.get('character_ids', [])]
        characters.append({'id': identity, 'name': public_text(name, 100), 'revision': (profile or {}).get('revision') or entity.get('revision'),
                           'style_id': (profile or {}).get('style_id') or entity.get('style_id'),
                           'style_revision': (profile or {}).get('style_revision'), 'state': state, 'issues': issues,
                           'profile': display_profile, 'legacy_document': text if not display_profile else None, 'design_version': version,
                           'images': images, 'review': review or None, 'review_current': review_current, 'changes': related, 'linked_shots': linked})
        for item in related:
            for key, kind in (('at', 'cast_change'), ('applied_at', 'cast_revision')):
                if item.get(key):
                    events.append({'id': 'cast:' + item['id'] + ':' + kind, 'at': item[key], 'kind': kind,
                                   'job': 'cast:' + identity, 'label': 'Character revision', 'message': identity + ': ' + public_text(item.get('request')),
                                   'detail': public_text(item.get('request'), 4000), 'part': None, 'source': 'production/cast-change-requests.json'})
        if review.get('at'):
            events.append({'id': 'cast-review:' + identity + ':' + review['at'], 'at': review['at'],
                           'kind': 'complete' if review.get('verdict') == 'passed' else 'failed', 'job': 'cast:' + identity,
                           'label': 'Cast-sheet inspection', 'message': identity + ': ' + public_text(review.get('notes')),
                           'part': None, 'source': 'production/cast-reviews.json'})
    return {'characters': characters, 'total': len(characters), 'ready': sum(c['state'] == 'ready' for c in characters),
            'pending_changes': sum(r.get('status') == 'requested' for r in requests), 'events': events,
            'scope': 'Actual registered cast, requested sheet coverage and byte-bound visual inspections. No automatic artistic approval.'}


def cast_image(reader, project, identity, digest):
    project = Path(project).resolve()
    entity = reader.json(project / 'continuity/entities.json').get('characters', {}).get(identity, {})
    for name in [*entity.get('reference_paths', []), *entity.get('previous_reference_paths', [])]:
        path = (project / name).resolve()
        if (path.is_relative_to(project) and path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')
                and path.is_file() and reader.digest(path) == digest):
            return path
    raise ValueError('This character reference is missing or a newer revision is available')
