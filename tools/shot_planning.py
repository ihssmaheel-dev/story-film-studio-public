"""Story-bound shot reasoning and honest timing context; never choose a count by runtime."""
import math
from pathlib import Path

from studio_common import read_json, sha256_file


GUIDE = 'instructions/shot-planning.md'


def problems(project, part, document=None):
    project, part = Path(project).resolve(), Path(part).resolve()
    document = read_json(part / 'shots.json', {}) if document is None else document
    # Old plans stay usable. Empty scaffolds are not a completed shot plan.
    if 'image_planning' not in document or not document.get('shots'):
        return []
    plan = document['image_planning']
    prefix = part.name + ': '
    if not isinstance(plan, dict) or plan.get('schema_version') != 1:
        return [prefix + 'image_planning must use schema_version 1']
    errors = []
    final = 'creative/story-revised.md' if (project / 'creative/story-revised.md').is_file() else 'creative/original.md'
    if (plan.get('story_file') != final or not (project / final).is_file()
            or plan.get('story_sha256') != sha256_file(project / final)):
        errors.append(prefix + 'image planning belongs to a different final-story revision; analyse the current story')
    if not isinstance(plan.get('rationale'), str) or not plan['rationale'].strip():
        errors.append(prefix + 'explain the story-driven image count, pacing and intentional holds')
    rows = plan.get('shots')
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return errors + [prefix + 'image planning must list the purpose and entry_reason of every shot']
    ids = [shot.get('id') for shot in document['shots']]
    if (any(not isinstance(identity, str) or not identity.strip() for identity in ids)
            or [row.get('shot_id') for row in rows] != ids
            or len({identity for identity in ids if isinstance(identity, str)}) != len(ids)):
        errors.append(prefix + 'image planning must cover every written shot exactly once, in order')
    for row in rows:
        for field in ('purpose', 'entry_reason'):
            if not isinstance(row.get(field), str) or not row[field].strip():
                errors.append(prefix + str(row.get('shot_id')) + ': explain its ' + field)
    return errors


def summary(project, part):
    """Read-only context for the agent's pacing judgment, not an engagement score."""
    project, part = Path(project).resolve(), Path(part).resolve()
    written = read_json(part / 'shots.json', {})
    shots = written.get('shots', [])
    plan = written.get('image_planning')
    timeline = read_json(part / 'timeline.json', {})
    rows = timeline.get('shots', [])
    same_order = [s.get('id') for s in rows] == [s.get('id') for s in shots] and bool(shots)
    manual = same_order and written.get('timing_mode') == 'manual'
    measured = (same_order and not manual
                and timeline.get('timing_source', {}).get('shots_sha256') == sha256_file(part / 'shots.json'))
    holds = []
    if measured or manual:
        for shot in rows:
            start, end = shot.get('start'), shot.get('end')
            if (type(start) in (int, float) and type(end) in (int, float)
                    and math.isfinite(start) and math.isfinite(end) and end > start):
                holds.append({'shot_id': shot['id'], 'seconds': round(end - start, 6)})
    sources = {str((part / row['image']).resolve()) for row in rows if isinstance(row.get('image'), str)}
    registry = read_json(project / 'continuity/entities.json', {})
    references = {str((project / name).resolve()) for group in ('styles', 'characters', 'locations', 'props')
                  for entity in registry.get(group, {}).values() for name in entity.get('reference_paths', [])}
    return {'strategy': 'story_beats', 'guide': GUIDE,
            'status': ('draft' if not shots else 'needs_update' if problems(project, part, written)
                       else 'recorded' if plan else 'unrecorded'),
            'written_shot_count': len(shots), 'rationale': plan.get('rationale') if isinstance(plan, dict) else None,
            'timing_basis': 'measured_speech' if measured else 'authored_manual' if manual else 'pending_current_timing',
            'holds': holds, 'distinct_timeline_image_files': len(sources),
            'missing_timeline_image_files': sum(not Path(name).is_file() for name in sources),
            'registered_reference_files': len(references),
            'scope': 'Counts describe current records, not new provider calls. Judge pacing against the story and actual preview.'}
