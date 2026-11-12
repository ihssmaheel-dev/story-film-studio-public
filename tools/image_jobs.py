#!/usr/bin/env python3
"""Approval-aware image request bridge; import actual provider results with provenance."""
import argparse
from pathlib import Path
import shutil
import math
import json

from camera_motion import normalize_motion
from image_references import collect as collect_references, require_current as require_current_prompt
from cast import design_version as cast_design_version

from project_records import artifact_path, validate_continuity
from studio_common import atomic_json, fingerprint, hash_session, read_json, record_lock, require_authorized_work, sha256_file, utc_now
from workflow import image_scope, require_stage


def builtin_scope(project):
    from workflow import policy
    value = policy(project)
    return value['scope'].get('builtin_images') if value['mode'] == 'fast' else None


def validate_estimate(project, estimate):
    if estimate is None and builtin_scope(project):
        return
    if isinstance(estimate, bool) or not isinstance(estimate, (int, float)) or not math.isfinite(estimate) or estimate < 0:
        raise ValueError('Provide a real price estimate, or explicitly authorize capped built-in calls with unreported cost')


def reserved_calls(project):
    return sum(record.get('reserved_calls', max(1, record.get('attempts', 0)))
               for path in (Path(project) / 'production/image-jobs').glob('*.json')
               if (record := read_json(path)).get('requested_provider', record.get('provider')) == 'codex-imagegen'
               or record.get('tool_request', {}).get('tool') == 'image_gen.imagegen')


def unresolved_outcome(record):
    return record.get('status') == 'requesting' or (
        record.get('status') == 'needs_attention' and record.get('outcome_known') is not True)


@hash_session()
def compile_request(project, part_id, shot_id, estimated_cost, currency='USD'):
    project = Path(project).resolve()
    require_stage(project, 'images', [part_id], tool='codex-imagegen')
    problems = validate_continuity(project, [part_id])
    if problems:
        raise ValueError('; '.join(problems))
    part = artifact_path(project, 'parts/' + part_id)
    shots = read_json(part / 'shots.json')['shots']
    found = [shot for shot in shots if shot.get('id') == shot_id]
    if len(found) != 1:
        raise ValueError('Shot must appear exactly once in the G4-approved written shots.json')
    shot = found[0]
    if not shot.get('visual_description') or not shot.get('camera_direction'):
        raise ValueError('Written visual description and camera geography are required')
    budget, _ = image_scope(project, 'final', 'codex-imagegen', currency, [part_id])
    validate_estimate(project, estimated_cost)
    if budget.get('currency') != currency:
        raise ValueError('An actual nonnegative price estimate and approved matching currency are required')
    if estimated_cost is not None and estimated_cost > budget.get('limit', 0):
        raise ValueError('Request exceeds the G6-approved remaining budget')
    registry = read_json(project / 'continuity/entities.json')
    all_entities = {identity: record for group in ('styles', 'characters', 'locations', 'props')
                    for identity, record in registry.get(group, {}).items()}
    visible = [shot.get('style_id'), shot.get('location_id')] + shot.get('character_ids', []) + shot.get('prop_ids', [])
    references, prompt_context = collect_references(project, {'kind': 'final', 'part_id': part_id, 'shot_id': shot_id})
    facts, inputs = [], {}
    for identity in filter(None, visible):
        if identity not in all_entities:
            raise ValueError(f'Unknown canonical entity {identity}')
        record = all_entities[identity]
        if identity == shot.get('style_id') and record.get('revision') != shot.get('style_revision'):
            raise ValueError('Shot style conflicts with the canonical registry')
        canonical = artifact_path(project, record['canonical_file'])
        facts.append(f'[{identity} revision {record.get("revision", "unreported")}]\n' + canonical.read_text(encoding='utf-8'))
        inputs[canonical.relative_to(project).as_posix()] = sha256_file(canonical)
    if not references.bindings:
        raise ValueError('Final shot generation requires actual canonical reference paths')
    prompt = '\n\n'.join([
        f'Create one cinematic still for {part_id}/{shot_id}. Preserve all canonical facts and reference identity.',
        references.contract(),
        f'Written visual: {shot["visual_description"]}',
        f'Camera direction: {shot["camera_direction"]}',
        f'Performance context only (do not draw subtitles or dialogue): {shot.get("narration", "")}',
        'Current scene states: ' + json.dumps(shot.get('entity_states', {}), ensure_ascii=False, sort_keys=True),
        *facts,
        'Portray each character through the recorded role, personality, posture and current emotional state. '
        'Preserve their distinctive face, silhouette, proportions, costume and story-time state across shots and parts. '
        'Do not replace the canonical cast with generic attractive hero or villain designs.',
        'The registry governs identity, geometry, props and style. Do not mirror locations or introduce unplanned changes.',
        'Render only this shot’s present action and visible information; do not illustrate later narration or reveal concealed story facts. '
        'Add readable in-world text only when the written visual explicitly requires it. No invented captions, panels, logos or interface.',
    ])
    timeline = read_json(part / 'timeline.json')
    prompt += f'\nDeliver a {timeline["width"]}:{timeline["height"]} composition with narrative details safe in the final frame.'
    motion = normalize_motion(shot.get('motion'))
    if motion['type'] != 'static':
        largest_zoom = max(motion['start']['zoom'], motion['end']['zoom'])
        divisor = math.gcd(timeline['width'], timeline['height'])
        multiple = math.ceil(divisor * largest_zoom / 2) * 2
        suggested_width = timeline['width'] // divisor * multiple
        suggested_height = timeline['height'] // divisor * multiple
        prompt += (f'\nThis is ONE still image, later framed with a {motion["type"]} camera move. '
                   f'Story purpose: {motion["reason"]}. Compose the full scene for the approved aspect ratio; '
                   f'provide enough detail for up to {largest_zoom:.3f}x enlargement '
                   f'(prefer at least {suggested_width}x{suggested_height} pixels if supported). '
                   f'Camera start: {motion["start"]}; end: {motion["end"]}. '
                   f'Keep these protected boxes accurate in normalized full-frame coordinates: {motion["protected_regions"]}. '
                   'Leave breathing room for the approved crop and subtitles. Do not draw a zoom sequence, '
                   'panels, crop marks, labels, borders or motion blur. Preserve identity and reveal timing.')
    return {'schema_version': 1, 'kind': 'final', 'part_id': part_id, 'shot_id': shot_id, 'provider': 'codex-imagegen',
            'tool_request': {'tool': 'image_gen.imagegen', 'arguments': {
                'prompt': prompt, 'referenced_image_paths': list(references.hashes()), 'transparent_background': False}},
            'canonical_inputs': inputs, 'reference_hashes': references.hashes(),
            'reference_bindings': references.bindings, 'prompt_context_sha256': prompt_context,
            'estimated_cost': estimated_cost, 'currency': currency,
            'output': next(item['image'] for item in timeline['shots'] if item['id'] == shot_id)}


@hash_session()
def queue_request(project, request):
    project = Path(project).resolve()
    with record_lock(project / 'production/provider-budget.lock'):
        return _queue_locked(project, request)


def _queue_locked(project, request):
    project = Path(project).resolve()
    budget, shared_budget = image_scope(project, request.get('kind', 'final'), request.get('provider'), request['currency'],
                                        [request['part_id']] if request.get('part_id') else None)
    validate_estimate(project, request['estimated_cost'])
    identity = fingerprint(request)
    path = project / 'production/image-jobs' / (identity + '.json')
    if path.is_file():
        existing = read_json(path)
        if existing.get('status') in ('needs_attention', 'requesting'):
            raise ValueError('Existing request has an unknown outcome or exhausted attempts; resolve it before another call')
        if existing.get('status') != 'failed':
            require_current_prompt(project, request)
            return path, existing
    else:
        existing = None
    if any(unresolved_outcome(read_json(other))
           for other in (project / 'production/image-jobs').glob('*.json') if other != path):
        raise ValueError('Reconcile the outstanding image outcome before queueing another call')
    cap = builtin_scope(project)
    if cap and reserved_calls(project) + 1 > cap['max_calls']:
        raise ValueError('The authorized built-in image call cap is exhausted; no call was queued')
    if request['currency'] != budget.get('currency') or not math.isfinite(budget.get('limit', 0)):
        raise ValueError('Request currency and finite approved budget must match')
    require_stage(project, 'reference' if request.get('kind') == 'reference' else 'images',
                  [request['part_id']] if request.get('part_id') else None)
    from provider_budget import spent_or_reserved
    used = spent_or_reserved(project, request['currency'], shared_budget, request.get('kind', 'final'))
    if request['estimated_cost'] is not None and used + request['estimated_cost'] > budget.get('limit', 0) + 1e-9:
        raise ValueError('Combined known/reserved requests exceed the approved budget; no request was queued')
    require_current_prompt(project, request)
    record = dict(request, request_id=identity, status='pending', attempts=0, created_at=utc_now(),
                  provider_job_id=None, actual_cost=None, reserved_calls=1,
                  cost_mode='unreported_builtin' if request['estimated_cost'] is None else 'monetary',
                  requested_provider=request['provider'])
    if existing:
        record.update(attempts=existing['attempts'], reserved_calls=existing.get('reserved_calls', 1) + 1,
                      history=[*existing.get('history', []), {key: value for key, value in existing.items() if key != 'history'}])
    atomic_json(path, record)
    return path, record


def compile_reference(project, entity_id, estimated_cost, currency='USD', sheet='complete'):
    project = Path(project).resolve()
    require_stage(project, 'reference', tool='codex-imagegen')
    require_authorized_work(project, 'reference', 'codex-imagegen')
    validate_estimate(project, estimated_cost)
    dependencies = read_json(project / 'continuity/dependencies.json')
    if dependencies.get('review_status') != 'complete':
        raise ValueError('Complete the full-story inventory/dependency matrix before generating references')
    authorization, _ = image_scope(project, 'reference', 'codex-imagegen', currency)
    if authorization.get('currency') != currency:
        raise ValueError('Currency differs from the approved reference-work scope')
    registry = read_json(project / 'continuity/entities.json')
    entities = {identity: (group, record) for group in ('styles', 'characters', 'locations', 'props')
                for identity, record in registry.get(group, {}).items()}
    if entity_id not in entities:
        raise ValueError('Register the entity and its written specification before requesting a reference')
    group, entity = entities[entity_id]
    if sheet not in ('complete', 'identity', 'expressions', 'poses', 'variants') or (group != 'characters' and sheet != 'complete'):
        raise ValueError('Choose a valid character sheet focus, or complete for a world/style reference')
    if group == 'characters':
        from cast import plan_problems, profiles
        errors = plan_problems(project, [entity_id])
        if errors:
            raise ValueError('; '.join(errors))
        if sheet == 'variants' and not profiles(project)[entity_id].get('state_variants'):
            raise ValueError('No event-driven character variants are requested in this profile')
    refs, prompt_context = collect_references(project, {'kind': 'reference', 'entity_id': entity_id})
    inputs, facts = {}, []
    for identity, item in refs.scoped.items():
        path = artifact_path(project, item['record']['canonical_file'])
        name = path.relative_to(project).as_posix()
        if name not in inputs:
            facts.append('[' + identity + ' revision ' + str(item['record'].get('revision', 'unreported')) + ']\n' + path.read_text(encoding='utf-8'))
            inputs[name] = sha256_file(path)
    prompt = ('Create the requested canonical ' + group + ' reference for ' + entity_id + '.\n' +
              refs.contract() + '\n\n' + '\n\n'.join(facts) +
              '\nShow only useful views requested by the written canonical brief. Keep scale, orientation, materials '
              'and identity coherent between views. Use a clear uncluttered presentation, without decorative frames, '
              'watermarks or unrequested labels. Do not substitute people or scenery from treatment examples. '
              'The result needs actual visual inspection against these references and the written acceptance criteria.')
    if group == 'characters':
        prompt += ('\nBase this design on the written story role, history and performance needs. '
                   'Make the recorded age/design type, silhouette, face, costume, posture and expression system coherent and distinctive. '
                   'Show only the requested useful views and representative in-character expressions/poses. '
                   'Keep identity consistent between views; do not invent appearance changes or import the style-example cast.')
        prompt += ('\nCAST SHEET PRESENTATION: build a clean reference board for this character, not a poster or a story scene. '
                   'Use a restrained neutral background, consistent scale and illumination, clear margins and generous separation between requested views. '
                   'Include readable full-body identity views, close facial expression studies and distinct story-action poses exactly as requested. '
                   'Repeat the SAME face, silhouette, proportions, hair, costume colors/materials and accessories in every study. '
                   'Keep clothes, hands and feet fully in frame where needed. Group expressions and poses clearly; do not overlap figures or squeeze them into tiny thumbnails. '
                   'Use only the stable character ID and requested short labels. Keep costume/injury/age variants separately identified by their written events. '
                   'Do not add unrelated characters, invented wardrobe alternatives, decorative scenery or unnecessary turnaround angles.')
        if sheet != 'complete':
            profile = profiles(project)[entity_id]
            fields = {'identity': 'views', 'expressions': 'expressions', 'poses': 'poses', 'variants': 'state_variants'}
            prompt += ('\nTHIS REQUEST IS A FOCUSED ' + sheet.upper() + ' SHEET ONLY. Render only these requested studies: ' +
                       json.dumps(profile[fields[sheet]], ensure_ascii=False) + '. Other view/expression/pose definitions above are identity context, '
                       'not additional panels for this image. Keep the selected studies large, clearly separated and readable.')
    elif group == 'locations':
        prompt += '\nKeep architectural geometry, entrances, landmarks and local camera axes consistent; do not mirror the layout.'
    elif group == 'props':
        prompt += '\nPreserve functional geometry, scale, attachment points and the actual requested story-time state.'
    arguments = {'prompt': prompt, 'transparent_background': False}
    if refs.bindings:
        arguments['referenced_image_paths'] = list(refs.hashes())
    return {'schema_version': 1, 'kind': 'reference', 'entity_id': entity_id, 'reference_group': group,
            'sheet_kind': sheet,
            'provider': 'codex-imagegen', 'tool_request': {'tool': 'image_gen.imagegen', 'arguments': arguments},
            'canonical_inputs': inputs, 'reference_hashes': refs.hashes(),
            'reference_bindings': refs.bindings, 'prompt_context_sha256': prompt_context,
            'cast_design_version': cast_design_version(project, entity_id) if group == 'characters' else None,
            'estimated_cost': estimated_cost, 'currency': currency}


def start_request(project, request_path):
    """Mark the real tool-call boundary; an interrupted outcome cannot auto-retry."""
    project, request_path = Path(project).resolve(), Path(request_path).resolve()
    if not request_path.is_relative_to(project / 'production/image-jobs'):
        raise ValueError('Request must belong to this project image queue')
    with record_lock(project / 'production/provider-budget.lock'):
        record = read_json(request_path)
        image_scope(project, record.get('kind', 'final'), 'codex-imagegen', record['currency'],
                    [record['part_id']] if record.get('part_id') else None)
        if record.get('status') != 'pending':
            raise ValueError('Only a pending request can start; reconcile unknown results before another call')
        if any(unresolved_outcome(read_json(path))
               for path in (project / 'production/image-jobs').glob('*.json') if path != request_path):
            raise ValueError('Reconcile the outstanding image outcome before another call')
        require_stage(project, 'reference' if record.get('kind') == 'reference' else 'images',
                      [record['part_id']] if record.get('part_id') else None, tool='codex-imagegen')
        require_current_prompt(project, record)
        for relative, digest in record['canonical_inputs'].items():
            if sha256_file(artifact_path(project, relative)) != digest:
                raise ValueError('Canonical image inputs changed; compile a current request')
        for source, digest in record['reference_hashes'].items():
            if sha256_file(source) != digest:
                raise ValueError('Image reference changed; compile a current request')
        record.update(status='requesting', started_at=utc_now())
        atomic_json(request_path, record)
        from progress_records import observe
        stage = 'cast' if record.get('reference_group') == 'characters' else 'images'
        observe(project, 'requested', stage, 'Cast-sheet generation submitted' if stage == 'cast' else 'Image generation started', part=record.get('part_id'))
        return record


@hash_session()
def import_result(project, request_path, image, provider, model=None, provider_job_id=None, actual_cost=None):
    from PIL import Image
    project = Path(project).resolve()
    request_path = Path(request_path).resolve()
    if not request_path.is_relative_to(project / 'production/image-jobs'):
        raise ValueError('Request must belong to this project image queue')
    record = read_json(request_path)
    if record.get('kind') == 'reference':
        require_authorized_work(project, 'reference', 'codex-imagegen')
    else:
        require_stage(project, 'images', [record['part_id']], tool='codex-imagegen')
    require_current_prompt(project, record)
    if actual_cost is not None and (not math.isfinite(actual_cost) or actual_cost < 0):
        raise ValueError('Actual cost must be known nonnegative or explicitly unreported')
    for relative, digest in record['canonical_inputs'].items():
        if sha256_file(artifact_path(project, relative)) != digest:
            raise ValueError('Canonical input changed; this request is stale')
    for path, digest in record['reference_hashes'].items():
        if sha256_file(path) != digest:
            raise ValueError('Reference changed; this request is stale')
    image = Path(image).resolve()
    with Image.open(image) as picture:
        picture.verify()
    if record.get('image_sha256') and record['image_sha256'] != sha256_file(image):
        raise ValueError('A different result already exists; create a new explicit revision/request')
    output = (project / 'references' / record['reference_group'] / record['request_id'] / image.name
              if record.get('kind') == 'reference' else
              project / 'parts' / record['part_id'] / 'images/revisions' / record['request_id'] / image.name)
    if output.exists() and sha256_file(output) != sha256_file(image):
        raise ValueError('A different result already exists; create a new explicit revision/request')
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.resolve() != image:
        shutil.copy2(image, output)
    record.update(status='generated', image=output.relative_to(project).as_posix(), image_sha256=sha256_file(output),
                  provider=provider, model=model, provider_job_id=provider_job_id,
                  actual_cost=actual_cost, imported_at=utc_now(), qa_status='visual_review_pending')
    atomic_json(request_path, record)
    from progress_records import observe
    stage = 'cast' if record.get('reference_group') == 'characters' else 'images'
    observe(project, 'received', stage, 'Cast sheet imported; coverage inspection pending' if stage == 'cast' else 'Image result imported; visual review pending', part=record.get('part_id'))
    if record.get('kind') != 'reference':
        timeline_path = project / 'parts' / record['part_id'] / 'timeline.json'
        timeline = read_json(timeline_path)
        for shot in timeline['shots']:
            if shot['id'] == record['shot_id']:
                shot['image'] = output.relative_to(timeline_path.parent).as_posix()
        atomic_json(timeline_path, timeline)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    sub = parser.add_subparsers(dest='action', required=True)
    queue = sub.add_parser('queue')
    queue.add_argument('--part', required=True)
    queue.add_argument('--shot', required=True)
    queue.add_argument('--estimated-cost', type=float)
    queue.add_argument('--currency', default='USD')
    reference = sub.add_parser('reference')
    reference.add_argument('--entity', required=True)
    reference.add_argument('--estimated-cost', type=float)
    reference.add_argument('--currency', default='USD')
    reference.add_argument('--sheet', choices=('complete', 'identity', 'expressions', 'poses', 'variants'), default='complete')
    ingest = sub.add_parser('import')
    ingest.add_argument('--request', required=True, type=Path)
    ingest.add_argument('--image', required=True, type=Path)
    ingest.add_argument('--provider', required=True)
    ingest.add_argument('--model')
    ingest.add_argument('--provider-job-id')
    ingest.add_argument('--actual-cost', type=float)
    fail = sub.add_parser('failed')
    fail.add_argument('--request', required=True, type=Path)
    fail.add_argument('--reason', required=True)
    fail.add_argument('--outcome-known', action='store_true')
    start = sub.add_parser('start')
    start.add_argument('--request', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.action in ('queue', 'reference'):
            request = (compile_reference(args.project, args.entity, args.estimated_cost, args.currency, args.sheet)
                       if args.action == 'reference' else compile_request(args.project, args.part, args.shot,
                                                                         args.estimated_cost, args.currency))
            path, record = queue_request(args.project, request)
            print(path)
            print('Execute tool_request with the available approved image tool; inspect references first. No call has been made by this command.')
        elif args.action == 'start':
            print(start_request(args.project, args.request)['tool_request'])
        elif args.action == 'import':
            print(import_result(args.project, args.request, args.image, args.provider, args.model,
                                args.provider_job_id, args.actual_cost)['image'])
        else:
            path = args.request.resolve()
            if not path.is_relative_to(args.project.resolve() / 'production/image-jobs'):
                raise ValueError('Request is outside this project')
            record = read_json(path)
            record['attempts'] += 1
            record['outcome_known'] = args.outcome_known
            record.update(status='needs_attention' if not args.outcome_known or record['attempts'] >= 3 else 'failed',
                          failure_reason=args.reason, outcome_known=args.outcome_known)
            atomic_json(path, record)
            print('Unknown outcomes must be checked before retrying to avoid duplicate jobs or charges.')
    except (ValueError, OSError, StopIteration) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
