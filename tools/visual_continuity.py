"""Require explicit visual bindings instead of accepting character IDs only inside prose."""
import math
from pathlib import Path
import re

from studio_common import read_json


def binding_problems(project, parts=None):
    project = Path(project)
    registry = read_json(project / 'continuity/entities.json', {})
    changes = read_json(project / 'continuity/state-ledger.json', {}).get('changes', [])
    entities = {key: value for group in ('characters', 'locations', 'props') for key, value in registry.get(group, {}).items()}
    errors = []
    for part in sorted((project / 'parts').glob('part_*')):
        if parts is not None and part.name not in parts:
            continue
        for shot in read_json(part / 'shots.json', {}).get('shots', []):
            prefix = part.name + '/' + str(shot.get('id')) + ': '
            if not isinstance(shot.get('visual_description', ''), str):
                errors.append(prefix + 'write a text visual_description')
                continue
            groups = [('characters', 'character_ids'), ('props', 'prop_ids')]
            for group, field in groups:
                values = shot.get(field)
                if registry.get(group) or field in shot:
                    if not isinstance(values, list) or any(not isinstance(v, str) for v in values) or len(set(v for v in (values or []) if isinstance(v, str))) != len(values or []):
                        errors.append(prefix + 'explicitly list ' + field + ' (empty only when none is visible)')
            if registry.get('locations') and (not isinstance(shot.get('location_id'), str) or shot['location_id'] not in registry['locations']):
                if shot.get('location_id') is not None or not str(shot.get('location_note', '')).strip():
                    errors.append(prefix + 'bind location_id or explain a location-independent frame in location_note')
            declared = []
            for field in ('character_ids', 'prop_ids', 'offscreen_character_ids', 'offscreen_prop_ids'):
                values = shot.get(field, [])
                if isinstance(values, list):
                    declared += [v for v in values if isinstance(v, str)]
                elif field.startswith('offscreen_'):
                    errors.append(prefix + 'explicitly list ' + field)
            declared += [shot.get('location_id')]
            mentioned = set(re.findall(r'\b(?:CHAR|PROP|LOC)-[0-9]{3}\b', shot.get('visual_description', '')))
            for identity in sorted(mentioned - set(declared)):
                errors.append(prefix + identity + ' appears in prose without a structured visible/offscreen binding')
            if registry.get('characters') and shot.get('character_ids') == [] and not shot.get('offscreen_character_ids') and not str(shot.get('no_characters_reason', '')).strip():
                errors.append(prefix + 'explain the character-free frame in no_characters_reason')
            offscreen = [v for field in ('offscreen_character_ids', 'offscreen_prop_ids') for v in (shot.get(field) or []) if isinstance(v, str)]
            visible = [identity for identity in declared if identity in entities and identity not in offscreen]
            known = any(entities[identity].get('initial_state') or any(c.get('entity_id') == identity for c in changes) for identity in visible)
            if visible and (registry.get('characters') or known):
                time = shot.get('story_time')
                if type(time) not in (int, float) or not math.isfinite(time):
                    errors.append(prefix + 'record a finite story_time for visual-state continuity')
                    continue
                asserted = shot.get('entity_states')
                if not isinstance(asserted, dict):
                    errors.append(prefix + 'record entity_states, including each known visual-state field')
                    continue
                for identity in visible:
                    expected = dict(entities[identity].get('initial_state', {}))
                    for change in sorted(changes, key=lambda item: item.get('story_time', -1)):
                        if change.get('entity_id') == identity and change.get('story_time', float('inf')) <= time:
                            expected.update(change.get('after', {}))
                    actual = asserted.get(identity, {})
                    if not isinstance(actual, dict) or any(key not in actual for key in expected):
                        errors.append(prefix + identity + ': assert all known state fields rather than omitting the checks')
    return errors
