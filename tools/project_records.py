"""Structured project decisions, exact approval snapshots and continuity validation."""
import argparse
from pathlib import Path

from studio_common import ROOT, atomic_json, atomic_text, read_json, sha256_file, utc_now
from camera_motion import normalize_motion

GATES = ('G1', 'G2', 'G3', 'G4', 'G5', 'G6')
PATTERNS = {
    'G1': ['creative/original.md', 'creative/source.json', 'creative/audit-report.md',
           'creative/audit-issues.json', 'creative/editorial-decisions.md', 'creative/change-log.md',
           'creative/story-approved.md', 'creative/story-revised.md', 'creative/reveal-map.md',
           'continuity/story-ledger.json'],
    'G2': ['creative/intake.json', 'creative/part-plan.md', 'parts/*/part.json'],
    'G3': ['world/**/*', 'references/**/*', 'continuity/entities.json',
           'continuity/dependencies.json', 'continuity/state-ledger.json', 'production/cast-reviews.json'],
    'G4': ['parts/*/storyboard.md', 'parts/*/shots.json', 'parts/*/narration.txt', 'parts/*/speech.json', 'creative/all-parts-review.md',
           'audio/sound-plan.md', 'audio/requirements.json'],
    'G5': ['audio/narrator.json', 'audio/narrator.md', 'audio/voice-plan.json', 'audio/voice-decisions.json',
           'audio/voice-references/**/*', 'audio/auditions/*', 'audio/sound-plan.md'],
    'G6': ['production/plan.md', 'production/settings.json', 'production/authorizations.json', 'production/workflow.json'],
}
DEPENDENTS = {'G1': ['G2', 'G3', 'G4', 'G5', 'G6'], 'G2': ['G4', 'G6'],
              'G3': ['G4', 'G6'], 'G4': ['G6'], 'G5': ['G6'], 'G6': []}


def artifact_path(project, name):
    base = ROOT if name.startswith('@studio/') else Path(project).resolve()
    relative = name.removeprefix('@studio/')
    path = (base / relative).resolve()
    if not path.is_relative_to(base):
        raise ValueError(f'Artifact path escapes its registry root: {name}')
    return path


def snapshot(project, gate):
    project = Path(project).resolve()
    result = {}
    for pattern in PATTERNS[gate]:
        for path in sorted(project.glob(pattern)):
            if path.is_file() and path.name != '.gitkeep':
                result[path.relative_to(project).as_posix()] = sha256_file(path)
    if gate in ('G5', 'G6'):
        names = ['models/kokoro/manifest.json']
        if gate == 'G6':
            names += ['studio.json', 'requirements.lock.txt']
        for name in names:
            path = ROOT / name
            if path.is_file():
                result['@studio/' + name] = sha256_file(path)
    return result


def approval_status(project, refresh=False):
    project = Path(project).resolve()
    log = read_json(project / 'approvals.json', {'schema_version': 1, 'gates': {}, 'history': []})
    changed = {}
    for gate in GATES:
        decision = log.get('gates', {}).get(gate, {})
        if decision.get('status') == 'approved':
            current = snapshot(project, gate)
            if not decision.get('artifacts') or current != decision['artifacts']:
                changed[gate] = 'Approved artifact contents or membership changed'
    for gate in list(changed):
        for dependent in DEPENDENTS[gate]:
            if log.get('gates', {}).get(dependent, {}).get('status') == 'approved':
                changed.setdefault(dependent, f'Depends on stale {gate}')
    if refresh and changed:
        impacted = impact_report(project, log, changed)
        atomic_json(project / 'production/impact.json', impacted)
        for gate, reason in changed.items():
            previous = dict(log['gates'][gate])
            log.setdefault('history', []).append({'gate': gate, 'decision': previous})
            log['gates'][gate].update(status='stale', stale_reason=reason, stale_at=utc_now())
        atomic_json(project / 'approvals.json', log)
        render_approvals(project, log)
        status = read_json(project / 'production/status.json', {'jobs': {}})
        for job in status.get('jobs', {}).values():
            if job.get('status') == 'complete':
                altered = [name for name, digest in job.get('inputs', {}).items()
                           if not Path(name).is_file() or sha256_file(name) != digest]
                if altered:
                    job.update(status='stale', stale_reason='Actual job inputs changed', changed_inputs=altered)
                else:
                    job['approval_blocked'] = list(changed)
        atomic_json(project / 'production/status.json', status)
    return log, changed


def impact_report(project, log, changed):
    project = Path(project).resolve()
    altered = set()
    for gate in changed:
        before = log.get('gates', {}).get(gate, {}).get('artifacts', {})
        after = snapshot(project, gate)
        altered.update(name for name in set(before) | set(after) if before.get(name) != after.get(name))
    current = read_json(project / 'continuity/entities.json', {})
    previous = log.get('gates', {}).get('G3', {}).get('entity_registry', {})
    affected = set()
    for registry in (current, previous):
        for group in ('styles', 'characters', 'locations', 'props'):
            for identity, entity in registry.get(group, {}).items():
                names = {entity.get('canonical_file'), *entity.get('reference_paths', [])}
                if names & altered or (previous and current.get(group, {}).get(identity) != previous.get(group, {}).get(identity)):
                    affected.add(identity)
    shots, audio_parts = set(), set()
    for path in (project / 'parts').glob('*/shots.json'):
        part = path.parent.name
        part_changed = any(name.startswith('parts/' + part + '/') for name in altered)
        if 'G5' in changed or any(name == f'parts/{part}/narration.txt' for name in altered):
            audio_parts.add(part)
        for shot in read_json(path).get('shots', []):
            visible = {shot.get('style_id'), shot.get('location_id'), *shot.get('character_ids', []), *shot.get('prop_ids', [])}
            if visible & affected or part_changed or 'G1' in changed:
                shots.add(part + '/' + shot['id'])
    return {'at': utc_now(), 'stale_gates': list(changed), 'changed_artifacts': sorted(altered),
            'entity_ids': sorted(affected), 'shot_ids': sorted(shots), 'audio_parts': sorted(audio_parts),
            'note': 'Review this impact map; exact local job input/output hashes control reuse. No assets were deleted.'}


def require_gates(project, gates):
    log, changed = approval_status(project, refresh=True)
    problems = []
    for gate in gates:
        record = log.get('gates', {}).get(gate, {})
        if record.get('status') != 'approved' or not record.get('decision_quote') or not record.get('artifacts'):
            problems.append(f'{gate} has no explicit approved decision with artifact hashes')
        elif gate in changed:
            problems.append(f'{gate} is stale: {changed[gate]}')
    if problems:
        raise ValueError('Production approval check failed: ' + '; '.join(problems))


def render_approvals(project, log):
    lines = ['# Approval log', '', 'Generated view of `approvals.json`; record decisions there through the CLI.', '',
             '| Gate | Revision | Status | Decision / timestamp |', '|---|---|---|---|']
    for gate in GATES:
        record = log.get('gates', {}).get(gate, {})
        quote = str(record.get('decision_quote', '')).replace('|', '\\|').replace('\n', ' ')
        lines.append(f'| {gate} | {record.get("revision", "r1")} | {record.get("status", "draft")} | {quote} {record.get("at", "")} |')
    lines.extend(['', 'Correction permission is separate; source evidence and historical gate decisions remain preserved.'])
    atomic_text(Path(project) / 'approvals.md', '\n'.join(lines) + '\n')


def record_gate(project, gate, revision, quote, decision_reference, approved_by='user'):
    project = Path(project).resolve()
    from story_git import require_story_branch
    require_story_branch(project)
    if not quote.strip() or not decision_reference.strip():
        raise ValueError('The actual human decision quotation and its chat/source reference are required')
    require_gates(project, GATES[:GATES.index(gate)])
    if gate == 'G1':
        ledger = read_json(project / 'continuity/story-ledger.json')
        coverage = ledger.get('review_coverage', {})
        if not coverage.get('full_read_complete') or not coverage.get('second_pass_complete'):
            raise ValueError('G1 requires actual full-read and second-pass coverage records')
        source = read_json(project / 'creative/source.json')
        if ledger.get('source_sha256') != source.get('sha256') or source['sha256'] != sha256_file(project / 'creative/original.md'):
            raise ValueError('Audit/source hashes do not match the preserved original')
        scenes = {scene['id'] for scene in ledger.get('scenes', [])}
        if not scenes or scenes != set(coverage.get('reviewed_scene_ids', [])):
            raise ValueError('G1 requires complete, nonempty scene coverage')
    if gate == 'G2':
        intake = read_json(project / 'creative/intake.json')
        if intake.get('mode') not in ('single', 'parts') or not intake.get('duration_policy'):
            raise ValueError('Decide single/parts and the requested or flexible duration policy before G2')
        if not intake.get('frame_format') or not intake.get('performance'):
            raise ValueError('Decide frame format and performance approach before G2')
        if intake['performance'] != 'none' and not intake.get('language'):
            raise ValueError('Decide the spoken language before G2')
        count = len(list((project / 'parts').glob('part_*/part.json')))
        if intake['mode'] == 'single' and count != 1:
            raise ValueError('Single-video delivery must have exactly one planned part')
    if gate in ('G3', 'G4'):
        issues = validate_continuity(project)
        if issues:
            raise ValueError('; '.join(issues))
    if gate == 'G3':
        from cast import plan_problems, sheet_problems
        errors = plan_problems(project)
        errors += [issue for identity in read_json(project / 'continuity/entities.json').get('characters', {})
                   for issue in sheet_problems(project, identity)]
        if errors:
            raise ValueError('; '.join(errors))
        dependencies = read_json(project / 'continuity/dependencies.json')
        if dependencies.get('review_status') != 'complete':
            raise ValueError('Finish the whole-story inventory/dependency review before G3')
        styles = read_json(project / 'continuity/entities.json').get('styles', {})
        if not styles or any(not style.get('reference_paths') for style in styles.values()):
            raise ValueError('G3 requires actual style proof/canonical reference paths')
    if gate == 'G4':
        from shot_planning import problems as image_plan_problems
        for part in (project / 'parts').glob('part_*'):
            shots = read_json(part / 'shots.json')
            issues = image_plan_problems(project, part, shots)
            if issues:
                raise ValueError('; '.join(issues))
            if not shots.get('shots'):
                raise ValueError(f'{part.name}: no complete written shot records')
            for shot in shots['shots']:
                if not shot.get('visual_description') or not shot.get('camera_direction'):
                    raise ValueError(f'{part.name}/{shot.get("id")}: complete the visual and camera specification')
            narration = part / 'narration.txt'
            expected = ' '.join(shot.get('narration', '') for shot in shots['shots']).split()
            if expected and (not narration.is_file() or narration.read_text(encoding='utf-8-sig').split() != expected):
                raise ValueError(f'{part.name}: narration.txt must match the complete approved shot dialogue/narration')
    if gate == 'G5':
        intake = read_json(project / 'creative/intake.json')
        narrator = read_json(project / 'audio/narrator.json')
        if intake.get('performance') != 'none' and (not narrator.get('voice') or not narrator.get('model_sha256') or not narrator.get('voices_sha256')):
            raise ValueError('Select/audition the voice and record exact model/voice hashes before G5')
        if intake.get('performance') != 'none':
            from studio_common import configuration
            runtime = configuration(project)['runtime']
            for field, name in (('model_sha256', 'model'), ('voices_sha256', 'voices')):
                if narrator[field] != sha256_file(ROOT / runtime[name]):
                    raise ValueError('G5 narrator hashes differ from the actual installed model/voice files')
    artifacts = snapshot(project, gate)
    if not artifacts:
        raise ValueError(f'No review artifacts exist for {gate}')
    log = read_json(project / 'approvals.json', {'schema_version': 1, 'gates': {}, 'history': []})
    previous = log.setdefault('gates', {}).get(gate)
    if previous:
        log.setdefault('history', []).append({'gate': gate, 'decision': previous})
    log['gates'][gate] = {'revision': revision, 'status': 'approved', 'approved_by': approved_by,
                          'decision_quote': quote, 'decision_reference': decision_reference,
                          'at': utc_now(), 'artifacts': artifacts}
    if gate == 'G3':
        log['gates'][gate]['entity_registry'] = read_json(project / 'continuity/entities.json')
    atomic_json(project / 'approvals.json', log)
    render_approvals(project, log)


def validate_continuity(project, parts=None):
    project = Path(project).resolve()
    registry = read_json(project / 'continuity/entities.json')
    errors, entities = [], {}
    motion_preference = read_json(project / 'creative/intake.json', {}).get('camera_motion')
    if motion_preference not in (None, 'static', 'selective'):
        errors.append('intake camera_motion must be static, selective or null')
    for group in ('styles', 'characters', 'locations', 'props'):
        for identity, record in registry.get(group, {}).items():
            if identity in entities:
                errors.append(f'Duplicate entity ID {identity}')
            entities[identity] = record
            canonical = record.get('canonical_file')
            if not canonical or not artifact_path(project, canonical).is_file():
                errors.append(f'{identity}: canonical file missing')
            for reference in record.get('reference_paths', []):
                if not artifact_path(project, reference).is_file():
                    errors.append(f'{identity}: missing reference {reference}')
    from visual_continuity import binding_problems
    bindings = binding_problems(project, parts)
    if bindings:
        return errors + bindings
    dependencies = read_json(project / 'continuity/dependencies.json')
    event_ids = {event.get('id') for event in dependencies.get('events', []) if isinstance(event, dict)}
    scene_ids = {scene.get('id') for scene in read_json(project / 'continuity/story-ledger.json', {}).get('scenes', [])}
    shot_ids = {path.parent.name + '/' + shot['id'] for path in (project / 'parts').glob('*/shots.json')
                for shot in read_json(path).get('shots', [])}
    for link in dependencies.get('links', []):
        for field in ('source', 'target'):
            identity = link.get(field)
            if identity not in entities and identity not in event_ids and identity not in scene_ids and identity not in shot_ids:
                errors.append(f'Dependency {field} refers to unknown ID {identity}')
    changes = read_json(project / 'continuity/state-ledger.json').get('changes', [])
    states = {identity: dict(record.get('initial_state', {})) for identity, record in entities.items()}
    ordered_changes = sorted(changes, key=lambda change: change.get('story_time', -1))
    for change in ordered_changes:
        identity = change.get('entity_id')
        if identity not in entities or not isinstance(change.get('story_time'), (int, float)):
            errors.append(f'Invalid state ledger change: {change.get("id")}')
            continue
        for field, value in change.get('before', {}).items():
            if states[identity].get(field) != value:
                errors.append(f'{change.get("id")}: historical {identity}.{field} contradicts previous state')
        states[identity].update(change.get('after', {}))
    seen_shots = set()
    for timeline in sorted((project / 'parts').glob('*/timeline.json')):
        if parts is not None and timeline.parent.name not in parts:
            continue
        data = read_json(timeline)
        approved_path = timeline.parent / 'shots.json'
        written = read_json(approved_path, {'shots': []}).get('shots', [])
        approved = {shot['id']: shot for shot in written}
        if len(approved) != len(written):
            errors.append(f'{timeline.parent.name}: duplicate written shot IDs')
        if data.get('part_id') != timeline.parent.name:
            errors.append(f'{timeline.parent.name}: timeline part identity differs from its folder')
        for source, shot in [('written', shot) for shot in written] + [('timeline', shot) for shot in data.get('shots', [])]:
            key = (data.get('part_id'), shot.get('id'), source)
            if key in seen_shots:
                errors.append(f'Duplicate composite shot identity {key}')
            seen_shots.add(key)
            try:
                motion = normalize_motion(shot.get('motion'))
                if motion_preference == 'static' and motion['type'] != 'static':
                    errors.append(f'{key}: camera movement conflicts with the static-only intake choice')
                if source == 'timeline' and shot.get('id') in approved:
                    if motion != normalize_motion(approved[shot['id']].get('motion')):
                        errors.append(f'{key}: camera movement conflicts with the G4 written shot registry')
            except ValueError as error:
                errors.append(f'{key}: {error}')
            if approved and shot.get('id') not in approved:
                errors.append(f'{key}: not present in the written shot registry')
            if shot.get('id') in approved:
                for field in ('style_id', 'style_revision', 'location_id', 'character_ids', 'prop_ids', 'narration'):
                    if field in approved[shot['id']] and shot.get(field) != approved[shot['id']][field]:
                        errors.append(f'{key}: {field} conflicts with the written shot registry')
            visible = shot.get('character_ids', []) + shot.get('prop_ids', [])
            visible += [shot.get('location_id'), shot.get('style_id')]
            for identity in filter(None, visible):
                if identity not in entities:
                    errors.append(f'{key}: unknown entity {identity}')
            style = entities.get(shot.get('style_id'), {})
            if style and style.get('revision') != shot.get('style_revision'):
                errors.append(f'{key}: style revision conflicts with canon')
            for identity, asserted in shot.get('entity_states', {}).items():
                expected = dict(entities.get(identity, {}).get('initial_state', {}))
                time = shot.get('story_time')
                if not isinstance(time, (int, float)):
                    errors.append(f'{key}: state assertions require story_time')
                    continue
                for change in ordered_changes:
                    if change.get('entity_id') == identity and change.get('story_time', float('inf')) <= time:
                        expected.update(change.get('after', {}))
                for field, value in asserted.items():
                    if expected.get(field) != value:
                        errors.append(f'{key}: {identity}.{field} conflicts with event/state ledger')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('check')
    sub.add_parser('refresh')
    record = sub.add_parser('record')
    record.add_argument('--gate', required=True, choices=GATES)
    record.add_argument('--revision', required=True)
    record.add_argument('--decision', required=True)
    record.add_argument('--decision-reference', required=True)
    args = parser.parse_args()
    try:
        if args.action == 'record':
            record_gate(args.project, args.gate, args.revision, args.decision, args.decision_reference)
        else:
            log, changed = approval_status(args.project, args.action == 'refresh')
            print({'gates': {gate: log.get('gates', {}).get(gate, {}).get('status', 'draft') for gate in GATES},
                   'stale': changed, 'continuity_issues': validate_continuity(args.project)})
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
