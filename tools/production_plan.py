"""Batch authored canonical records, with optimistic locking and preserved revisions."""
import hashlib
import copy
import json
from pathlib import Path, PurePosixPath
import re

from project_records import validate_continuity
from studio_common import atomic_json, atomic_text, fingerprint, read_json, record_lock, sha256_file, utc_now

EXACT = {
    'world/cast.json',
    'creative/part-plan.json', 'creative/part-plan.md', 'creative/all-parts-review.md',
    'creative/scene-map.md', 'creative/reveal-map.md', 'creative/continuous-edit.md',
    'continuity/entities.json', 'continuity/dependencies.json', 'continuity/state-ledger.json',
    'continuity/story-ledger.json', 'audio/requirements.json', 'audio/sound-plan.md', 'audio/voice-plan.json',
}


def target(project, name):
    if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_./-]+', name):
        raise ValueError('Use plain project-relative canonical paths')
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or str(path) != name:
        raise ValueError('Canonical paths must stay inside this project')
    allowed = (name in EXACT or re.fullmatch(r'world/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+\.md', name)
               or re.fullmatch(r'parts/part_[0-9]{3}/(?:part\.json|shots\.json|speech\.json|timeline\.json|narration\.txt|storyboard\.md)', name))
    if not allowed:
        raise ValueError('Not an authored plan artifact: ' + name + '; use the dedicated source/configuration/voice/review command')
    result = (project / name).resolve()
    if not result.is_relative_to(project):
        raise ValueError('Canonical path escapes the project: ' + name)
    return result


def snapshot(project):
    project = Path(project).resolve()
    base = {}
    paths = [project / name for name in EXACT]
    paths += list((project / 'world').rglob('*.md'))
    paths += [part / name for part in (project / 'parts').glob('part_*') if part.is_dir()
              for name in ('part.json', 'shots.json', 'speech.json', 'timeline.json', 'narration.txt', 'storyboard.md')]
    for path in paths:
        if path.is_file():
            name = path.relative_to(project).as_posix()
            target(project, name)
            base[name] = sha256_file(path)
    return {'schema_version': 1, 'source_sha256': sha256_file(project / 'creative/original.md'),
            'base': base, 'artifacts': {}}


def proposed(project, bundle):
    if (not isinstance(bundle, dict) or bundle.get('schema_version') != 1
            or set(bundle) - {'schema_version', 'source_sha256', 'base', 'artifacts'}):
        raise ValueError('Use the production-plan bundle schema, not configuration or approval data')
    if bundle.get('source_sha256') != sha256_file(project / 'creative/original.md'):
        raise ValueError('Production bundle belongs to a different story source')
    if not isinstance(bundle.get('base'), dict) or not isinstance(bundle.get('artifacts'), dict) or not bundle['artifacts']:
        raise ValueError('Include a captured base and the actual authored artifacts')
    contents = {}
    for name, value in bundle['artifacts'].items():
        target(project, name)
        if name.endswith('.json'):
            if not isinstance(value, dict):
                raise ValueError(name + ': canonical JSON must be an object')
            contents[name] = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        elif isinstance(value, str):
            contents[name] = value
        else:
            raise ValueError(name + ': write the actual document text')
    if 'world/cast.json' in bundle['artifacts']:
        from cast import profile_problems, profiles, render_profile, sheet_problems
        data = bundle['artifacts']['world/cast.json']
        if data.get('schema_version') != 1 or not isinstance(data.get('characters'), dict):
            raise ValueError('Use the structured cast schema_version 1 with a characters map')
        registry = copy.deepcopy(bundle['artifacts'].get('continuity/entities.json', read_json(project / 'continuity/entities.json')))
        previous = profiles(project)
        for identity, profile in data['characters'].items():
            if not re.fullmatch(r'CHAR-[0-9]{3}', identity):
                raise ValueError('Use stable CHAR-### character IDs')
            errors = profile_problems(project, identity, profile, registry)
            if errors:
                raise ValueError('; '.join(errors))
            if identity in previous and previous[identity] != profile and not sheet_problems(project, identity):
                raise ValueError('Use studio cast revise with the actual change request for an inspected character design')
            document = 'world/characters/' + identity + '.md'
            rendered = render_profile(identity, profile)
            if document in contents and contents[document] != rendered:
                raise ValueError('The cast profile is authoritative; do not author a conflicting character document')
            contents[document] = rendered
            record = registry.setdefault('characters', {}).setdefault(identity, {'reference_paths': [], 'inspiration_paths': []})
            record.update(canonical_file=document, revision=profile['revision'], style_id=profile['style_id'])
        contents['continuity/entities.json'] = json.dumps(registry, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    # The spoken words already exist in authored shots/turns; don't write another timing helper.
    for name, value in list(bundle['artifacts'].items()):
        if not name.endswith('/shots.json'):
            continue
        prefix = name.rsplit('/', 1)[0]
        from shot_planning import problems as image_plan_problems
        errors = image_plan_problems(project, project / prefix, value)
        if errors:
            raise ValueError('; '.join(errors))
        speech = bundle['artifacts'].get(prefix + '/speech.json')
        if speech is None:
            speech = read_json(project / prefix / 'speech.json', {})
        texts = [item.get('text', '') for item in speech.get('utterances', [])]
        spoken = [s.get('narration', '') for s in value.get('shots', [])]
        if texts and ' '.join(texts).split() != ' '.join(spoken).split():
            raise ValueError(prefix + ': speech turns differ from the written shot narration')
        contents.setdefault(prefix + '/narration.txt', '\n\n'.join(filter(None, texts or spoken)) + '\n')
        # A new measured shot plan has no measured durations yet. Discard its old
        # derived tracks; the core builder will recreate them from actual speech.
        previous = read_json(project / name, {})
        timing_plan = lambda doc: {key: item for key, item in doc.items() if key != 'image_planning'}
        if (value.get('timing_mode') == 'speech_turns' and timing_plan(previous) != timing_plan(value)
                and prefix + '/timeline.json' not in contents):
            timeline = read_json(project / prefix / 'timeline.json')
            timeline.update(shots=[], subtitles=[], audio_cues=[], duration=0,
                            alignment={}, timing_source={'status': 'pending_actual_speech'})
            contents[prefix + '/timeline.json'] = json.dumps(timeline, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    changes = {}
    for name, text in contents.items():
        path = target(project, name)
        before = path.read_bytes() if path.is_file() else None
        after = text.encode('utf-8')
        if before == after:
            continue
        actual = hashlib.sha256(before).hexdigest() if before is not None else None
        if bundle['base'].get(name) != actual:
            raise ValueError(name + ' changed after the captured base; reread and merge the actual changes')
        changes[name] = (before, after)
    return changes


def apply(project, bundle, check=False):
    from story_git import require_story_branch
    from part_continuity import problems as part_problems
    from production_session import session_lock
    project = Path(project).resolve()
    require_story_branch(project)
    with session_lock(project), record_lock(project / 'production/plan.lock'):
        changes = proposed(project, bundle)
        if check or not changes:
            return {'status': 'checked' if check else 'unchanged', 'files': list(changes),
                    'validation': 'Source, allowed paths, current base, JSON and spoken-text agreement; semantic continuity is checked on apply.'}
        identity = fingerprint(bundle)
        revision = (project / 'production/plan-revisions' / identity).resolve()
        if not revision.is_relative_to(project):
            raise ValueError('Plan revision history must stay inside its project')
        # Preserve exact prior bytes before publishing any changes.
        for name, (before, _) in changes.items():
            if before is not None:
                path = revision / 'before' / name
                path.parent.mkdir(parents=True, exist_ok=True)
                if not path.exists():
                    path.write_bytes(before)
        written = []
        try:
            for name, (before, after) in changes.items():
                path = target(project, name)
                current = path.read_bytes() if path.is_file() else None
                if current != before:
                    raise ValueError(name + ' changed during the batch; reconcile the concurrent edit')
                atomic_text(path, after.decode('utf-8'))
                written.append(name)
            if sha256_file(project / 'creative/original.md') != bundle['source_sha256']:
                raise ValueError('Story source changed during planning; preserve the edit and rebuild its plan')
            errors = validate_continuity(project) + part_problems(project)
            if errors:
                raise ValueError('; '.join(errors))
            receipt = {'schema_version': 1, 'at': utc_now(), 'source_sha256': bundle['source_sha256'],
                       'files': {name: hashlib.sha256(after).hexdigest() for name, (_, after) in changes.items()},
                       'scope': 'Authored planning records only; no source revision, authorization, inspection or listening is asserted.'}
            atomic_json(revision / 'receipt.json', receipt)
        except BaseException:
            for name in reversed(written):
                before, after = changes[name]
                path = target(project, name)
                # A concurrent edit is never replaced during rollback.
                if path.is_file() and path.read_bytes() == after:
                    if before is None:
                        path.unlink()
                    else:
                        path.write_bytes(before)
            raise
    return {'status': 'applied', 'files': list(changes), 'receipt': str(revision / 'receipt.json')}
