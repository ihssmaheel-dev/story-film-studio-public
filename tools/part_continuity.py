"""Structural part boundaries and reusable handoffs; never write a story or approval."""
from pathlib import Path

from studio_common import read_json, sha256_file


def problems(project):
    project = Path(project).resolve()
    path = project / 'creative/part-plan.json'
    if not path.is_file():
        return []  # Existing projects retain their recorded workflow.
    plan = read_json(path)
    errors = []
    if not isinstance(plan, dict):
        return ['Part plan must be a JSON object']
    final = 'creative/story-revised.md' if (project / 'creative/story-revised.md').is_file() else 'creative/original.md'
    if plan.get('schema_version') != 1 or plan.get('story_file') != final:
        return ['Part plan must identify the authoritative final-story file: ' + final]
    story = project / plan['story_file']
    if not story.is_file() or plan.get('story_sha256') != sha256_file(story):
        return ['Part plan belongs to a different final-story revision; update its actual boundaries']
    lines = story.read_text(encoding='utf-8-sig').splitlines()
    parts = plan.get('parts')
    if not isinstance(parts, list) or not parts:
        return ['Write the complete ordered part plan before producing it']
    folders = sorted(p.name for p in (project / 'parts').glob('part_*') if p.is_dir())
    ids = [p.get('id') for p in parts if isinstance(p, dict)]
    expected = [f'part_{n:03d}' for n in range(1, len(parts) + 1)]
    if ids != expected or folders != expected:
        return ['Part plan and folders must agree in order: ' + ', '.join(expected)]
    intake = read_json(project / 'creative/intake.json')
    if intake.get('mode') == 'single' and len(parts) != 1:
        errors.append('A single complete film uses only part_001')
    if intake.get('desired_part_count') is not None and intake['desired_part_count'] != len(parts):
        errors.append('Part count differs from the recorded delivery choice')
    registry = read_json(project / 'continuity/entities.json')
    entities = {key: value for group in ('styles', 'characters', 'locations', 'props')
                for key, value in registry.get(group, {}).items()}
    changes = {c.get('id'): c for c in read_json(project / 'continuity/state-ledger.json').get('changes', [])}
    cursor, carried, promise, promises = 1, {}, None, set()
    for index, part in enumerate(parts):
        identity = part['id']
        for field in ('title', 'opening_hook', 'dramatic_progress', 'ending'):
            if not isinstance(part.get(field), str) or not part[field].strip():
                errors.append(f'{identity}: write its {field}')
        start, end = part.get('start_line'), part.get('end_line')
        if (type(start) is not int or type(end) is not int or start != cursor or not start <= end <= len(lines)):
            errors.append(f'{identity}: story line spans must cover the complete story once, in order')
        else:
            cursor = end + 1
        payoffs = part.get('pays_off', [])
        if not isinstance(payoffs, list):
            errors.append(f'{identity}: pays_off must list earlier continuation IDs')
            payoffs = []
        if promise and promise not in payoffs:
            errors.append(f'{identity}: explicitly develop/pay off continuation {promise}')
        if any(not isinstance(p, str) or p not in promises for p in payoffs):
            errors.append(f'{identity}: payoff IDs must identify actual earlier continuation promises')
        entry, exit_state = part.get('entry_state'), part.get('exit_state')
        if not isinstance(entry, dict) or not isinstance(exit_state, dict):
            errors.append(f'{identity}: entry_state and exit_state must map stable entity IDs to facts')
            continue
        expected_entry = {entity: dict(facts) for entity, facts in carried.items()}
        events = part.get('handoff_events', [])
        if not isinstance(events, list):
            errors.append(f'{identity}: handoff_events must list actual state-ledger event IDs')
            events = []
        for event_id in events:
            if not isinstance(event_id, str):
                errors.append(f'{identity}: handoff event IDs must be strings')
                continue
            event = changes.get(event_id)
            if not event:
                errors.append(f'{identity}: unknown handoff event {event_id}')
                continue
            current = expected_entry.setdefault(event['entity_id'], {})
            if any(current.get(key) != value for key, value in event.get('before', {}).items()):
                errors.append(f'{identity}: handoff event {event_id} contradicts the previous ending')
            current.update(event.get('after', {}))
        for entity, facts in expected_entry.items():
            if not isinstance(entry.get(entity), dict) or any(entry[entity].get(k) != v for k, v in facts.items()):
                errors.append(f'{identity}: {entity} loses or contradicts inherited story state')
        for state in (entry, exit_state):
            for entity, facts in state.items():
                if entity not in entities or not isinstance(facts, dict):
                    errors.append(f'{identity}: invalid state for canonical entity {entity}')
        carried = {entity: {**(entry.get(entity) if isinstance(entry.get(entity), dict) else {}), **facts}
                   for entity, facts in exit_state.items() if isinstance(facts, dict)}
        carried.update({entity: facts for entity, facts in entry.items() if entity not in exit_state and isinstance(facts, dict)})
        continuation = part.get('continuation')
        if index == len(parts) - 1:
            if continuation is not None:
                errors.append(f'{identity}: the final part ends the story without another release promise')
        elif (not isinstance(continuation, dict) or continuation.get('next_part') != parts[index + 1]['id']
              or any(not isinstance(continuation.get(k), str) or not continuation[k].strip()
                     for k in ('id', 'promise', 'payoff'))):
            errors.append(f'{identity}: record its earned continuation promise and next-part payoff')
        promise = continuation.get('id') if isinstance(continuation, dict) else None
        if promise:
            if promise in promises:
                errors.append(f'{identity}: continuation promise IDs must be unique')
            promises.add(promise)
    if cursor != len(lines) + 1:
        errors.append('Part narratives must cover the complete authoritative story through its ending')
    return list(dict.fromkeys(errors))


def handoff(project, part_id):
    project = Path(project).resolve()
    errors = problems(project)
    if errors:
        raise ValueError('; '.join(errors))
    plan = read_json(project / 'creative/part-plan.json', {})
    parts = plan.get('parts', [])
    index = next((i for i, p in enumerate(parts) if p['id'] == part_id), None)
    if index is None:
        return {'part': part_id, 'structured_plan': False,
                'instruction': 'Reuse canonical part-plan.md, registry, state ledger and current written shots.'}
    part = parts[index]
    lines = (project / plan['story_file']).read_text(encoding='utf-8-sig').splitlines(keepends=True)
    registry = read_json(project / 'continuity/entities.json')
    return {'part': part_id, 'structured_plan': True, 'story_sha256': plan['story_sha256'],
            'story_excerpt': ''.join(lines[part['start_line'] - 1:part['end_line']]),
            'opening_hook': part['opening_hook'], 'dramatic_progress': part['dramatic_progress'],
            'ending': part['ending'], 'previous_ending': parts[index - 1]['ending'] if index else None,
            'entry_state': part['entry_state'], 'exit_state': part['exit_state'],
            'pays_off': part.get('pays_off', []), 'continuation': part.get('continuation'),
            'canonical_revisions': {key: {'revision': value.get('revision'), 'canonical_file': value['canonical_file'],
                                          'references': value.get('reference_paths', [])}
                                    for group in ('styles', 'characters', 'locations', 'props')
                                    for key, value in registry.get(group, {}).items()}}
