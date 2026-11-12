"""Canonical cast profiles, inspected sheet coverage and revision requests."""
import argparse
import copy
import json
import hashlib
import re
from pathlib import Path
import uuid

from studio_common import ROOT, atomic_text, fingerprint, read_json, record_lock, sha256_file, utc_now

TEXT_FIELDS = ('name', 'role', 'age_or_life_stage', 'design_type', 'personality', 'appearance',
               'proportions', 'wardrobe', 'relative_scale', 'expression_system')
CHECKS = ('identity', 'style', 'wardrobe', 'expressions', 'poses', 'readability')


def profiles(project):
    values = read_json(Path(project) / 'world/cast.json', {}).get('characters', {})
    return values if isinstance(values, dict) else {}


def render_profile(identity, profile):
    lines = ['# ' + identity + ' — ' + profile['name'], '',
             'Generated from world/cast.json. Edit the structured profile through the cast workflow.', '',
             'Style: ' + profile['style_id'] + ' / ' + profile['style_revision'],
             'Character revision: ' + profile['revision'], '']
    for field in TEXT_FIELDS:
        lines += ['## ' + field.replace('_', ' ').capitalize(), profile[field], '']
    lines += ['## Identity anchors', *['- ' + item for item in profile['identity_anchors']], '',
              '## Required views', *['- ' + item for item in profile['views']], '']
    for group in ('expressions', 'poses', 'state_variants'):
        lines += ['## ' + group.replace('_', ' ').capitalize()]
        lines += ['- ' + key + ': ' + value for key, value in profile.get(group, {}).items()]
        lines += ['']
    lines += ['## Reference notes', profile.get('reference_notes') or 'Use the registered current identity sheet.']
    return '\n'.join(lines) + '\n'


def profile_problems(project, identity, profile, registry=None):
    registry = registry or read_json(Path(project) / 'continuity/entities.json', {})
    prefix = str(identity) + ': '
    if not isinstance(profile, dict):
        return [prefix + 'author its structured world/cast.json profile']
    errors = [prefix + 'complete ' + field for field in TEXT_FIELDS
              if not isinstance(profile.get(field), str) or not profile[field].strip()]
    if not re.fullmatch(r'r[1-9][0-9]*', str(profile.get('revision', ''))):
        errors.append(prefix + 'use a character revision such as r1')
    style = registry.get('styles', {}).get(profile.get('style_id')) if isinstance(profile.get('style_id'), str) else None
    if not style or style.get('revision') != profile.get('style_revision'):
        errors.append(prefix + 'bind the exact current style_id/style_revision')
    for field in ('identity_anchors', 'views'):
        values = profile.get(field)
        if (not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values)
                or len(set(v for v in values if isinstance(v, str))) != len(values)):
            errors.append(prefix + 'list distinct story-specific ' + field)
    for field in ('expressions', 'poses', 'state_variants'):
        values = profile.get(field, {} if field == 'state_variants' else None)
        if (not isinstance(values, dict) or (field != 'state_variants' and not values)
                or any(not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip() for k, v in (values or {}).items())):
            errors.append(prefix + 'map required ' + field + ' to actual performance/design descriptions')
    return errors


def plan_problems(project, identities=None):
    project = Path(project)
    registry = read_json(project / 'continuity/entities.json', {})
    cast = profiles(project)
    data = read_json(project / 'world/cast.json', {})
    errors = []
    if registry.get('characters') and (data.get('schema_version') != 1 or not isinstance(data.get('characters'), dict)):
        errors.append('Author world/cast.json with schema_version 1 and its complete characters map')
    for identity in identities if identities is not None else registry.get('characters', {}):
        profile = cast.get(identity)
        issues = profile_problems(project, identity, profile, registry)
        errors.extend(issues)
        if issues:
            continue
        record = registry.get('characters', {}).get(identity, {})
        name = 'world/characters/' + identity + '.md'
        if (record.get('canonical_file') != name or record.get('revision') != profile['revision']
                or record.get('style_id') != profile['style_id']):
            errors.append(identity + ': synchronize character registry revision/style_id with its structured profile')
        path = project / name
        if not path.is_file() or path.read_text(encoding='utf-8-sig') != render_profile(identity, profile):
            errors.append(identity + ': regenerate its character document from world/cast.json')
    return errors


def design_version(project, identity):
    """Stable request base: new sheet files alone do not change the authored design."""
    project = Path(project)
    registry = read_json(project / 'continuity/entities.json', {})
    record = registry.get('characters', {}).get(identity)
    if record is None:
        raise ValueError('Unknown character ' + identity)
    raw_profile = profiles(project).get(identity)
    profile = raw_profile if isinstance(raw_profile, dict) else None
    style_id = (profile or {}).get('style_id') or record.get('style_id')
    if style_id is None and len(registry.get('styles', {})) == 1:
        style_id = next(iter(registry['styles']))
    style = registry.get('styles', {}).get(style_id, {})
    from project_records import artifact_path
    source = artifact_path(project, record['canonical_file'])
    style_source = artifact_path(project, style['canonical_file']) if style.get('canonical_file') else None
    return fingerprint({'character_id': identity, 'profile': raw_profile, 'legacy_document': sha256_file(source) if profile is None and source.is_file() else None,
                        'style': style, 'style_document': sha256_file(style_source) if style_source and style_source.is_file() else None})


def sheet_inputs(project, identity, images=None):
    project = Path(project)
    registry = read_json(project / 'continuity/entities.json', {})
    names = images if images is not None else registry.get('characters', {}).get(identity, {}).get('reference_paths', [])
    from project_records import artifact_path
    return {'design_version': design_version(project, identity),
            'images': {name: sha256_file(artifact_path(project, name)) for name in names}}


def sheet_problems(project, identity):
    errors = plan_problems(project, [identity])
    if errors:
        return errors
    record = read_json(Path(project) / 'continuity/entities.json')['characters'][identity]
    if not record.get('reference_paths'):
        return [identity + ': create and inspect the requested cast sheet']
    try:
        current = sheet_inputs(project, identity)
    except OSError:
        return [identity + ': a registered cast sheet is missing']
    gallery = {r['sha256'] for r in read_json(ROOT / 'references/style/visual-preferences/style-catalog.json')['styles']}
    if any(digest in gallery for digest in current['images'].values()):
        return [identity + ': a gallery treatment example is not a character identity sheet']
    review = read_json(Path(project) / 'production/cast-reviews.json', {}).get('reviews', {}).get(identity, {})
    if (review.get('verdict') != 'passed' or review.get('inputs') != current or review.get('character_id') != identity
            or not str(review.get('reviewer', '')).strip() or not str(review.get('notes', '')).strip()
            or not set(CHECKS) <= set(review.get('checks', []))):
        return [identity + ': inspect the current sheet for identity, style, required views, expressions and poses']
    profile = profiles(project)[identity]
    for group in ('views', 'expressions', 'poses', 'state_variants'):
        coverage = review.get('coverage', {}).get(group, {})
        if not isinstance(coverage, dict) or any(coverage.get(name) not in current['images'] for name in profile.get(group, [])):
            return [identity + ': current inspection is missing required ' + group + ' coverage']
    return []


def visible_cast(project, parts=None):
    ids = []
    for part in sorted((Path(project) / 'parts').glob('part_*')):
        if parts is not None and part.name not in parts:
            continue
        for shot in read_json(part / 'shots.json', {}).get('shots', []):
            ids.extend(shot.get('character_ids', []))
    return list(dict.fromkeys(ids))


def ready_problems(project, parts=None):
    return [problem for identity in visible_cast(project, parts) for problem in sheet_problems(project, identity)]


def pending_requests(project):
    result = []
    for item in read_json(Path(project) / 'production/cast-change-requests.json', {}).get('requests', []):
        if item.get('status') == 'requested':
            value = dict(item)
            try:
                value['base_current'] = item['base_version'] == design_version(project, item['character_id'])
            except (KeyError, OSError, ValueError):
                value['base_current'] = False
            result.append(value)
    return result


def request_change(project, identity, text, base_version, source, request_id=None):
    from story_git import require_story_branch
    project = Path(project).resolve()
    require_story_branch(project)
    if not isinstance(identity, str) or not re.fullmatch(r'CHAR-[0-9]{3}', identity):
        raise ValueError('Choose a registered CHAR-### character')
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 4000 or not isinstance(source, str) or not source.strip():
        raise ValueError('Provide the actual character-change request and its source')
    request_id = request_id or str(uuid.uuid4())
    try:
        uuid.UUID(request_id)
    except (ValueError, AttributeError):
        raise ValueError('Use a UUID request ID')
    with record_lock(project / 'production/cast.lock'):
        from project_records import artifact_path
        path = artifact_path(project, 'production/cast-change-requests.json')
        data = read_json(path, {'schema_version': 1, 'requests': []})
        existing = next((r for r in data['requests'] if r['id'] == request_id), None)
        if existing:
            if existing['character_id'] != identity or existing['request'] != text.strip() or existing['base_version'] != base_version:
                raise ValueError('This request ID already belongs to a different change')
            return existing
        if base_version != design_version(project, identity):
            raise ValueError('The character design changed; refresh and review the current revision before submitting')
        item = {'id': request_id, 'character_id': identity, 'request': text.strip(), 'source': source.strip(),
                'base_version': base_version, 'at': utc_now(), 'status': 'requested'}
        data['requests'].append(item)
        from studio_common import atomic_json
        atomic_json(path, data)
    return item


def _capture(project, names):
    return {name: (Path(project) / name).read_bytes() if (Path(project) / name).is_file() else None for name in names}


def _publish(project, changes, revision, expected=None):
    """Preserve exact previous bytes and roll back only our own writes on a failed transaction."""
    project = Path(project).resolve()
    try:
        uuid.UUID(revision)
    except (ValueError, AttributeError):
        raise ValueError('Use an immutable UUID cast-revision ID')
    allowed = {'world/cast.json', 'continuity/entities.json', 'production/cast-reviews.json', 'production/cast-change-requests.json'}
    for name in changes:
        if name not in allowed and not re.fullmatch(r'world/characters/CHAR-[0-9]{3}\.md', name):
            raise ValueError('Cast transactions cannot edit source/configuration or arbitrary project files')
        if not (project / name).resolve().is_relative_to(project):
            raise ValueError('Cast transaction path escapes the story project')
    if expected is not None and _capture(project, expected) != expected:
        raise ValueError('Concurrent cast edit; reread the current design before publishing')
    before = _capture(project, changes)
    after = {name: (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n' if isinstance(value, dict) else value).encode('utf-8')
             for name, value in changes.items()}
    archive = (project / 'production/cast-revisions' / revision).resolve()
    if not archive.is_relative_to(project):
        raise ValueError('Cast revision history escapes the story project')
    for name, raw in before.items():
        if raw is not None:
            target = archive / 'before' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    written = []
    try:
        for name, raw in after.items():
            path = project / name
            if (path.read_bytes() if path.is_file() else None) != before[name]:
                raise ValueError('Concurrent cast edit; reconcile ' + name)
            atomic_text(path, raw.decode('utf-8'))
            written.append(name)
        from studio_common import atomic_json
        atomic_json(archive / 'receipt.json', {'at': utc_now(), 'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in after.items()}})
    except BaseException:
        for name in reversed(written):
            path = project / name
            if path.is_file() and path.read_bytes() == after[name]:
                if before[name] is None:
                    path.unlink()
                else:
                    path.write_bytes(before[name])
        raise


def record_review(project, review):
    from story_git import require_story_branch
    from production_session import session_lock
    from project_records import artifact_path
    from PIL import Image
    project = Path(project).resolve()
    require_story_branch(project)
    identity = review.get('character_id')
    errors = plan_problems(project, [identity])
    if errors:
        raise ValueError('; '.join(errors))
    if review.get('verdict') not in ('passed', 'failed') or not str(review.get('reviewer', '')).strip() or not str(review.get('notes', '')).strip():
        raise ValueError('Record the actual visual verdict, reviewer and inspection notes')
    profile = profiles(project)[identity]
    with session_lock(project), record_lock(project / 'production/cast.lock'):
        expected = _capture(project, ('world/cast.json', 'continuity/entities.json', 'production/cast-reviews.json'))
        errors = plan_problems(project, [identity])
        if errors:
            raise ValueError('; '.join(errors))
        profile = profiles(project)[identity]
        if review.get('design_version') != design_version(project, identity):
            raise ValueError('The cast design changed after inspection; inspect its current revision')
        images = review.get('images')
        if not isinstance(images, list) or not images or any(not isinstance(name, str) for name in images):
            raise ValueError('List the actual inspected sheet images')
        gallery = {r['sha256'] for r in read_json(ROOT / 'references/style/visual-preferences/style-catalog.json')['styles']}
        for name in images:
            path = artifact_path(project, name)
            if not path.is_relative_to(project) or not path.is_file() or path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
                raise ValueError('Snapshot actual cast-sheet images inside this project')
            with Image.open(path) as picture:
                picture.verify()
            if sha256_file(path) in gallery:
                raise ValueError('A gallery treatment example is not a story-specific cast identity sheet')
            if review.get('image_sha256', {}).get(name) != sha256_file(path):
                raise ValueError('Record the exact inspected image_sha256 for every sheet; changed pixels need renewed inspection')
        coverage = review.get('coverage', {})
        if review['verdict'] == 'passed':
            if not set(CHECKS) <= set(review.get('checks', [])):
                raise ValueError('Inspect every required cast-sheet check')
            for group, required in (('views', profile['views']), ('expressions', profile['expressions']), ('poses', profile['poses']),
                                    ('state_variants', profile.get('state_variants', {}))):
                actual = coverage.get(group, {})
                if not isinstance(actual, dict) or any(name not in actual or actual[name] not in images for name in required):
                    raise ValueError('Record actual image coverage for every required ' + group)
        registry = read_json(project / 'continuity/entities.json')
        registry['characters'][identity]['reference_paths'] = list(dict.fromkeys(images))
        inputs = sheet_inputs(project, identity, images)
        data = read_json(project / 'production/cast-reviews.json', {'schema_version': 1, 'reviews': {}, 'history': []})
        if identity in data['reviews']:
            data['history'].append(data['reviews'][identity])
        item = {key: review[key] for key in ('character_id', 'verdict', 'reviewer', 'notes')}
        item.update(at=utc_now(), inputs=inputs, coverage=coverage, checks=review.get('checks', []))
        data['reviews'][identity] = item
        if review['design_version'] != design_version(project, identity):
            raise ValueError('The cast design changed during inspection recording')
        _publish(project, {'continuity/entities.json': registry, 'production/cast-reviews.json': data}, str(uuid.uuid4()), expected)
    return item


def revise(project, identity, proposed, request_id):
    from story_git import require_story_branch
    from production_session import session_lock
    project = Path(project).resolve()
    require_story_branch(project)
    if not isinstance(proposed, dict):
        raise ValueError('Provide the complete revised character profile as a JSON object')
    with session_lock(project), record_lock(project / 'production/cast.lock'):
        expected = _capture(project, ('world/cast.json', 'continuity/entities.json', 'production/cast-change-requests.json',
                                      'world/characters/' + identity + '.md'))
        requests = read_json(project / 'production/cast-change-requests.json', {})
        item = next((r for r in requests.get('requests', []) if r['id'] == request_id and r['character_id'] == identity), None)
        if item is None or item.get('status') != 'requested':
            raise ValueError('Use the actual pending character-change request')
        if item['base_version'] != design_version(project, identity):
            raise ValueError('The request targets an earlier design; reconcile its actual intent before revising')
        data = read_json(project / 'world/cast.json', {'schema_version': 1, 'characters': {}})
        old = data['characters'].get(identity)
        registry = read_json(project / 'continuity/entities.json')
        prior_revision = (old or {}).get('revision') or registry['characters'][identity].get('revision', 'r0')
        if not re.fullmatch(r'r[0-9]+', str(prior_revision)):
            raise ValueError('Reconcile the actual previous character revision before changing it')
        profile = copy.deepcopy(proposed)
        profile['revision'] = 'r' + str(int(prior_revision[1:]) + 1)
        errors = profile_problems(project, identity, profile, registry)
        if errors:
            raise ValueError('; '.join(errors))
        record = registry['characters'][identity]
        immediate = record.get('reference_paths') or record.get('revision_reference_paths', [])
        previous = list(dict.fromkeys([*record.get('previous_reference_paths', []), *record.get('reference_paths', [])]))
        record.update(canonical_file='world/characters/' + identity + '.md', revision=profile['revision'], style_id=profile['style_id'],
                      reference_paths=[], previous_reference_paths=previous, revision_reference_paths=immediate)
        data['characters'][identity] = profile
        affected = [part.name + '/' + shot['id'] for part in (project / 'parts').glob('part_*')
                    for shot in read_json(part / 'shots.json', {}).get('shots', []) if identity in shot.get('character_ids', [])]
        item.update(status='applied', applied_at=utc_now(), revision=profile['revision'], affected_shots=affected)
        if item['base_version'] != design_version(project, identity):
            raise ValueError('The base design changed during revision; preserve and reconcile that edit')
        _publish(project, {'world/cast.json': data, record['canonical_file']: render_profile(identity, profile),
                           'continuity/entities.json': registry, 'production/cast-change-requests.json': requests}, request_id, expected)
    return {'character_id': identity, 'revision': profile['revision'], 'affected_shots': affected,
            'next': 'Create and inspect the revised sheet, then inspect/rebuild affected shots and presentation. Previous files are preserved.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('status')
    template = sub.add_parser('review-template')
    template.add_argument('--character', required=True)
    template.add_argument('--images', nargs='+', required=True)
    review = sub.add_parser('review')
    review.add_argument('--file', required=True, type=Path)
    request = sub.add_parser('request')
    request.add_argument('--character', required=True)
    request.add_argument('--change', required=True)
    request.add_argument('--source', required=True)
    request.add_argument('--base-version', required=True)
    revision = sub.add_parser('revise')
    revision.add_argument('--character', required=True)
    revision.add_argument('--file', required=True, type=Path)
    revision.add_argument('--request', required=True)
    args = parser.parse_args()
    try:
        if args.action == 'review-template':
            profile = profiles(args.project).get(args.character)
            errors = plan_problems(args.project, [args.character])
            if errors:
                raise ValueError('; '.join(errors))
            from project_records import artifact_path
            result = {'character_id': args.character, 'design_version': design_version(args.project, args.character),
                      'images': args.images, 'image_sha256': {name: sha256_file(artifact_path(args.project, name)) for name in args.images},
                      'verdict': 'pending', 'reviewer': '', 'notes': '', 'checks': [],
                      'coverage': {group: {key: None for key in profile.get(group, [])} for group in ('views', 'expressions', 'poses', 'state_variants')}}
        elif args.action == 'review':
            result = record_review(args.project, read_json(args.file))
        elif args.action == 'request':
            result = request_change(args.project, args.character, args.change, args.base_version, args.source)
        elif args.action == 'revise':
            result = revise(args.project, args.character, read_json(args.file), args.request)
        else:
            result = {'profiles': profiles(args.project), 'problems': plan_problems(args.project),
                      'pending_requests': pending_requests(args.project),
                      'design_versions': {identity: design_version(args.project, identity) for identity in read_json(args.project / 'continuity/entities.json').get('characters', {})}}
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
