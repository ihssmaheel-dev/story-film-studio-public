"""Fast project configuration, scoped delegation and a single preview decision.

Delegation authorizes work inside a recorded scope. It never manufactures G1-G6
approvals, artistic reviews, listening evidence or permission for another story.
Projects without a workflow record retain the legacy strict policy.
"""
import argparse
import hashlib
import copy
from pathlib import Path
import re

from studio_common import ROOT, atomic_json, fingerprint, hash_session, read_json, sha256_file, utc_now

AUDIT_AREAS = (
    'plot', 'scene_continuity', 'characters', 'chronology', 'cause_effect', 'knowledge',
    'world_rules', 'dialogue', 'clarity', 'setups_payoffs', 'pacing', 'emotion',
)
PREFERENCES = (
    'mode', 'duration_policy', 'desired_part_count', 'continuous_edition', 'audience', 'platform', 'language',
    'performance', 'visual_style', 'visual_preference', 'frame_format', 'camera_motion',
    'subtitles', 'sound_preferences', 'sound_acquisition_permissions', 'budget', 'privacy_constraints',
)
LEGACY_VOICE_FIELDS = ('voice', 'speed', 'language', 'pause', 'spoken_forms', 'pronunciations')
VOICE_FIELDS = LEGACY_VOICE_FIELDS + ('provider', 'model', 'providers', 'cast')
PROJECT_FIELDS = ('story_complete', 'protected_story_choices', 'review_scope')
TOOLS = {'kokoro', 'chatterbox', 'elevenlabs', 'inworld', 'cartesia', 'custom-http', 'provided',
         'procedural-audio', 'provided-audio', 'https-audio', 'codex-imagegen'}
STAGES = {'reference', 'audition', 'production', 'narration', 'alignment', 'timeline', 'sound',
          'mix', 'subtitles', 'images', 'render', 'master', 'qa', 'release'}
DEFAULT_WORKFLOW = {
    'schema_version': 1, 'mode': 'fast', 'task': 'film', 'audit': 'focused',
    'minor_edits': 'delegate',
    'scope': {'tools': ['kokoro', 'procedural-audio', 'provided-audio'],
              'budget': {'limit': 0, 'currency': 'USD'}, 'external_upload': [], 'download_domains': []},
}


def policy(project):
    path = Path(project) / 'production/workflow.json'
    if not path.is_file():
        return dict(copy.deepcopy(DEFAULT_WORKFLOW), mode='strict')
    value = read_json(path)
    validate_policy(value)
    return value


def validate_policy(value):
    from camera_motion import number
    if not isinstance(value, dict) or set(value) - {'schema_version', 'mode', 'task', 'audit', 'minor_edits', 'scope'}:
        raise ValueError('Unsupported workflow fields')
    if value.get('mode') not in ('fast', 'strict') or value.get('task') not in ('story', 'storyboard', 'film'):
        raise ValueError('Choose workflow mode fast/strict and task story/storyboard/film')
    if value.get('audit') not in ('focused', 'full') or value.get('minor_edits') not in ('ask', 'delegate'):
        raise ValueError('Choose audit focused/full and minor_edits ask/delegate')
    scope = value.get('scope', {})
    if not isinstance(scope, dict) or set(scope) - {'tools', 'budget', 'external_upload', 'download_domains', 'builtin_images'}:
        raise ValueError('Unsupported workflow scope fields')
    for name in ('tools', 'external_upload', 'download_domains'):
        if not isinstance(scope.get(name), list) or any(not isinstance(item, str) or not item for item in scope[name]):
            raise ValueError(f'workflow.scope.{name} must be a list of names')
    if set(scope['tools']) - TOOLS or not set(scope['external_upload']).issubset(set(scope['tools'])):
        raise ValueError('Unknown tool or upload permission outside the selected tools')
    images = scope.get('builtin_images')
    if images is not None:
        if (not isinstance(images, dict) or set(images) != {'max_calls', 'unreported_cost_accepted'} or
                type(images.get('max_calls')) is not int or images['max_calls'] <= 0 or
                images.get('unreported_cost_accepted') is not True or
                'codex-imagegen' not in scope['tools'] or 'codex-imagegen' not in scope['external_upload']):
            raise ValueError('Built-in image scope needs a positive call cap, explicit acceptance of unreported cost and matching tool/upload scope')
    budget = scope.get('budget', {})
    if not isinstance(budget, dict) or not number(budget.get('limit')) or budget['limit'] < 0 or not re.fullmatch(r'[A-Z]{3}', str(budget.get('currency', ''))):
        raise ValueError('Use a finite nonnegative budget and a three-letter uppercase currency')
    for domain in scope['download_domains']:
        if not re.fullmatch(r'[a-z0-9.-]+', domain) or '..' in domain or domain.startswith('.'):
            raise ValueError('Download domains must be explicit host names without schemes or wildcards')


def selected_parts(project, parts=None):
    project = Path(project).resolve()
    available = {path.name: path for path in (project / 'parts').glob('part_*') if path.is_dir()}
    names = list(parts) if parts is not None else sorted(available)
    if not names or any(name not in available or not re.fullmatch(r'part_\d{3,}', name) for name in names):
        raise ValueError('Select existing planned part_### folders')
    return [available[name] for name in names]


def part_for_path(project, path):
    try:
        relative = Path(path).resolve().relative_to(Path(project).resolve() / 'parts')
        return [relative.parts[0]] if relative.parts else None
    except ValueError:
        return None


def delivery_outputs(project):
    """Describe requested outputs without inventing additional planned parts.

    New intakes explicitly default continuous_edition to true. A legacy record
    without this preference retains its existing scope until configured.
    """
    intake = read_json(Path(project) / 'creative/intake.json')
    if intake.get('mode') == 'single':
        return ['one complete full-length video']
    if intake.get('mode') == 'parts':
        outputs = ['individual part videos']
        if intake.get('continuous_edition') is True:
            outputs.append('one continuous full-length video')
        return outputs
    return []


def delivery_problems(project):
    project = Path(project)
    intake = read_json(project / 'creative/intake.json')
    errors = []
    if intake.get('mode') == 'single':
        parts = sorted(path.name for path in (project / 'parts').glob('part_*') if path.is_dir())
        if parts != ['part_001'] or not (project / 'parts/part_001/part.json').is_file():
            errors.append('A single video must use exactly one planned part (part_001)')
    if intake.get('continuous_edition') is not None and not isinstance(intake['continuous_edition'], bool):
        errors.append('continuous_edition must be true, false or unanswered')
    return errors


def questions(project, include_authorization=True):
    """Only human choices; missing internal work is reported separately."""
    project = Path(project)
    value, intake = policy(project), read_json(project / 'creative/intake.json')
    result = []
    limited_story = value['task'] == 'story' and intake.get('story_complete') is False and intake.get('review_scope')
    if intake.get('story_complete') is not True and not limited_story:
        result.append('Confirm that the supplied story includes its ending, or define the limited scope.')
    if value['task'] != 'film':
        return result
    format_missing = [name for name in ('mode', 'duration_policy') if not intake.get(name)]
    if len(format_missing) == 2:
        result.append('Choose one video or parts and a target length or explicitly flexible duration.')
    elif 'mode' in format_missing:
        result.append('Choose one complete video or part-by-part delivery; reuse the recorded duration policy.')
    elif 'duration_policy' in format_missing:
        target = 'each part' if intake.get('mode') == 'parts' else 'the complete video'
        result.append(f'Choose a target length or explicitly flexible duration for {target}.')
    if not intake.get('performance') or (intake.get('performance') != 'none' and not intake.get('language')):
        result.append('Choose the spoken language and narration, dialogue, mixed or speech-free delivery.')
    look_missing = [name for name in ('visual_style', 'frame_format') if not intake.get(name)]
    if look_missing:
        result.append('Choose the visual treatment and frame format; reuse your saved preferences if suitable.')
    if include_authorization and value['mode'] == 'fast' and delegation_status(project)[0] != 'authorized':
        result.append('Authorize the displayed configuration, tools, spending cap and upload scope together.')
    return result


def configuration_problems(project):
    from camera_motion import number
    intake, value = read_json(Path(project) / 'creative/intake.json'), policy(project)
    errors = questions(project, include_authorization=False)
    if value['task'] != 'film':
        return errors
    if intake.get('mode') not in ('single', 'parts'):
        errors.append('Delivery mode must be single or parts')
    errors.extend(delivery_problems(project))
    duration = intake.get('duration_policy')
    if not isinstance(duration, dict) or not isinstance(duration.get('flexible'), bool):
        errors.append('Specify a flexible or bounded duration policy')
    elif not duration['flexible']:
        low, high = duration.get('min_seconds', 0), duration.get('max_seconds')
        if not number(low) or not number(high) or not 0 <= low <= high or high <= 0:
            errors.append('A fixed duration policy needs finite positive bounds')
    if intake.get('performance') not in ('narration', 'dialogue', 'mixed', 'none'):
        errors.append('Performance must be narration, dialogue, mixed or none')
    if intake.get('performance') != 'none':
        from speech_providers import validate_profile, voice_config
        narrator = read_json(Path(project) / 'audio/narrator.json')
        try:
            validate_profile(narrator)
            configured = [voice_config(narrator, speaker) for speaker in ['NARRATOR', *narrator.get('cast', {})]]
            if value['mode'] == 'fast':
                for provider in {item['provider'] for item in configured}:
                    if provider not in value['scope']['tools']:
                        errors.append('Include the selected speech provider in the displayed tool scope: ' + provider)
            for config in configured:
                if config['provider'] == 'custom-http':
                    from speech_providers import ready_problems
                    errors.extend(ready_problems(project, config))
        except ValueError as error:
            errors.append(str(error))
    frame = intake.get('frame_format')
    if isinstance(frame, dict):
        if any(not isinstance(frame.get(key), int) or isinstance(frame[key], bool) or frame[key] <= 0 or frame[key] % 2
               for key in ('width', 'height')) or not number(frame.get('fps', 30)) or frame.get('fps', 30) <= 0:
            errors.append('Use positive even frame dimensions and a finite positive FPS')
    elif frame not in ('landscape', 'portrait', 'square'):
        errors.append('Choose landscape, portrait, square or explicit frame dimensions')
    return list(dict.fromkeys(errors))


def configuration_snapshot(project, intake_fields=None, delegate_voice=False, pronunciation_keys=None, speech_choices=None,
                           narrator_override=None):
    """Bind user choices, original source and runtime settings; exclude generated work."""
    project = Path(project).resolve()
    result = {name: sha256_file(project / name) for name in (
        'creative/original.md', 'production/workflow.json')}
    from studio_common import configuration
    settings = configuration(project)
    provider = settings.get('image_provider', {})
    result['provider_route'] = fingerprint({key: provider.get(key) for key in ('mode', 'currency')})
    intake = read_json(project / 'creative/intake.json')
    fields = intake_fields if intake_fields is not None else configured_intake_fields(intake)
    result['intake_choices'] = fingerprint({key: intake.get(key) for key in fields})
    source = read_json(project / 'creative/source.json')
    result['source_identity'] = fingerprint({'sha256': source.get('sha256'), 'snapshot_path': source.get('snapshot_path')})
    narrator = narrator_override if narrator_override is not None else read_json(project / 'audio/narrator.json', {})
    names = VOICE_FIELDS if speech_choices is not None or any(key in narrator for key in ('provider', 'model', 'providers', 'cast')) else LEGACY_VOICE_FIELDS
    preferences = {key: narrator.get(key) for key in names}
    if delegate_voice:
        preferences['voice'] = None
    if pronunciation_keys is not None:
        for name, keys in pronunciation_keys.items():
            preferences[name] = {key: narrator.get(name, {}).get(key) for key in keys}
    if speech_choices is not None:
        from speech_providers import voice_config
        effective_narrator = voice_config(narrator)
        for name in ('provider', 'voice', 'model', 'speed', 'language'):
            preferences[name] = effective_narrator[name]
        if delegate_voice:
            preferences['voice'] = None
        preferences['cast'] = {}
        for speaker, fields in speech_choices['cast'].items():
            current = narrator.get('cast', {}).get(speaker, {})
            preferences['cast'][speaker] = {name: current.get(name) for name in fields if name != 'options'}
            if 'options' in fields:
                preferences['cast'][speaker]['options'] = {key: current.get('options', {}).get(key) for key in fields['options']}
        preferences['providers'] = {provider: {key: narrator.get('providers', {}).get(provider, {}).get(key) for key in fields}
                                    for provider, fields in speech_choices['providers'].items()}
        preferences['cast_effective'] = {speaker: {key: voice_config(narrator, speaker)[key] for key in fields}
                                         for speaker, fields in speech_choices.get('cast_effective', {}).items()}
        if speech_choices['delegate_model']:
            preferences['model'] = None
    result['voice_preferences'] = fingerprint(preferences)
    result['@studio/runtime'] = fingerprint(settings.get('runtime', {}))
    if (ROOT / 'requirements.lock.txt').is_file():
        result['@studio/requirements.lock.txt'] = dependency_lock_hashes()[0]
    return result


def dependency_lock_hashes():
    """Equivalent LF/CRLF checkouts bind the same dependency text, including versions."""
    content = (ROOT / 'requirements.lock.txt').read_bytes().replace(b'\r\n', b'\n')
    return [hashlib.sha256(value).hexdigest() for value in (content, content.replace(b'\n', b'\r\n'))]


def configured_intake_fields(intake):
    fields = {key for key in PREFERENCES if intake.get(key) is not None}
    if intake.get('mode') != 'parts':
        fields.discard('continuous_edition')
    fields.update(PROJECT_FIELDS)
    return sorted(fields)


def delegation_status(project):
    project = Path(project)
    record = read_json(project / 'production/delegation.json', {})
    if record.get('status') != 'authorized' or not record.get('decision_quote') or not record.get('decision_reference'):
        return 'missing', record
    expected = dict(record.get('configuration', {}))
    if (ROOT / 'requirements.lock.txt').is_file():
        variants = dependency_lock_hashes()
        if expected.get('@studio/requirements.lock.txt') in variants:
            expected['@studio/requirements.lock.txt'] = variants[0]
    if (expected != configuration_snapshot(project, record.get('intake_fields'), record.get('delegate_voice', False), record.get('pronunciation_keys'), record.get('speech_choices'))
            or record.get('scope') != policy(project)['scope']):
        return 'stale', record
    return 'authorized', record


def authorize(project, quote, reference):
    project = Path(project).resolve()
    value = policy(project)
    if value['mode'] != 'fast':
        raise ValueError('Strict projects use the explicit G1-G6 workflow')
    if not quote.strip() or not reference.strip():
        raise ValueError('Record the actual user authorization and its chat/source reference')
    missing = configuration_problems(project)
    if missing:
        raise ValueError('Complete the material configuration first: ' + ' '.join(missing))
    source = read_json(project / 'creative/source.json')
    if source.get('sha256') != sha256_file(project / 'creative/original.md'):
        raise ValueError('The preserved original differs from its source record')
    path = project / 'production/delegation.json'
    previous = read_json(path, {})
    history = previous.get('history', [])
    if previous:
        history = [*history, {key: val for key, val in previous.items() if key != 'history'}]
    fields = configured_intake_fields(read_json(project / 'creative/intake.json'))
    narrator = read_json(project / 'audio/narrator.json', {})
    from speech_providers import validate_profile, voice_config
    validate_profile(narrator)
    delegate_voice = not voice_config(narrator).get('voice')
    pronunciation_keys = {name: sorted(narrator.get(name, {})) for name in ('spoken_forms', 'pronunciations')}
    # Bind explicit voice/model/route choices. New cast members and delegated
    # voices are ordinary execution inside the allowed providers/budget.
    speech_choices = {'delegate_model': not narrator.get('model'),
                      'providers': {name: sorted(key for key, val in options.items() if val is not None and key != 'price_per_1000_characters')
                                    for name, options in narrator.get('providers', {}).items()}, 'cast': {}, 'cast_effective': {}}
    for speaker, options in narrator.get('cast', {}).items():
        cast_fields = {key: True for key, val in options.items() if val is not None and key != 'options'}
        if options.get('options'):
            cast_fields['options'] = sorted(key for key, val in options['options'].items() if val is not None and key != 'price_per_1000_characters')
        speech_choices['cast'][speaker] = cast_fields
        resolved = voice_config(narrator, speaker)
        effective = ['provider']
        if options.get('voice'):
            effective.append('voice')
        if (options.get('model') or options.get('options', {}).get('model') or
                narrator.get('providers', {}).get(resolved['provider'], {}).get('model') or
                (resolved['provider'] == narrator.get('provider', 'kokoro') and narrator.get('model'))):
            effective.append('model')
        speech_choices['cast_effective'][speaker] = effective
    record = {'schema_version': 1, 'status': 'authorized', 'decision_quote': quote,
              'decision_reference': reference, 'at': utc_now(), 'scope': value['scope'],
              'intake_fields': fields, 'delegate_voice': delegate_voice,
              'pronunciation_keys': pronunciation_keys,
              'speech_choices': speech_choices,
              'configuration': configuration_snapshot(project, fields, delegate_voice, pronunciation_keys, speech_choices), 'history': history}
    atomic_json(path, record)
    return record


def audit_problems(project, block_findings=True):
    project = Path(project)
    ledger = read_json(project / 'continuity/story-ledger.json', {})
    audit = read_json(project / 'creative/audit-issues.json', {})
    coverage = ledger.get('review_coverage', {})
    original = sha256_file(project / 'creative/original.md')
    final = project / 'creative/story-revised.md'
    final = final if final.is_file() else project / 'creative/original.md'
    final_hash = sha256_file(final)
    scenes = [scene['id'] for scene in ledger.get('scenes', [])]
    errors = []
    if not coverage.get('full_read_complete') or not scenes or len(scenes) != len(set(scenes)) or set(scenes) != set(coverage.get('reviewed_scene_ids', [])):
        errors.append('Finish the complete source read and record every scene once')
    if ledger.get('source_sha256') != original or audit.get('source_sha256') != original:
        errors.append('The story review must identify the preserved original hash')
    if set(coverage.get('audit_areas_reviewed', [])) != set(AUDIT_AREAS):
        errors.append('Finish the twelve internal story checks')
    if policy(project)['audit'] == 'full':
        if not coverage.get('second_pass_complete'):
            errors.append('Full audit mode requires the complete second pass')
    elif not (coverage.get('focused_check_complete') or coverage.get('second_pass_complete')):
        errors.append('Finish the focused opening/ending, knowledge and payoff cross-check')
    if coverage.get('checked_story_sha256') != final_hash or audit.get('final_story_sha256') != final_hash:
        errors.append('The final story or revision needs its current consistency check')
    if not audit.get('assessment') or not audit.get('verdict'):
        errors.append('Record the concise story assessment and remaining issues')
    if final_hash != original:
        receipt = read_json(project / 'creative/revision.json', {})
        permitted = (receipt.get('decision_kind') == 'user' and receipt.get('decision_quote') and receipt.get('decision_reference'))
        if receipt.get('decision_kind') == 'delegated' and policy(project)['minor_edits'] == 'delegate' and receipt.get('scope') == 'minor':
            status, grant = delegation_status(project)
            valid = {fingerprint(grant.get('configuration', {}))}
            for change in grant.get('voice_changes', []):
                previous = change.get('previous_configuration', {})
                if (change.get('decision_quote') and change.get('decision_reference') and
                        {key: val for key, val in previous.items() if key != 'voice_preferences'} ==
                        {key: val for key, val in grant.get('configuration', {}).items() if key != 'voice_preferences'}):
                    valid.add(fingerprint(previous))
            permitted = status == 'authorized' and receipt.get('authorization_fingerprint') in valid
        if not permitted or receipt.get('source_sha256') != original or receipt.get('revision_sha256') != final_hash or not receipt.get('summary'):
            errors.append('Record the actual permission or delegated minor-edit receipt for this story revision')
    for finding in audit.get('findings', []):
        resolved = finding.get('disposition') == 'resolved'
        accepted = finding.get('disposition') == 'accepted' and finding.get('decision_quote') and finding.get('decision_reference')
        blocking = finding.get('requires_user_decision') or (
            finding.get('classification') == 'confirmed issue' and finding.get('severity') in ('HIGH', 'CRITICAL'))
        if block_findings and blocking and not (resolved or accepted):
            errors.append(f'{finding.get("id", "Finding")}: resolve the material story decision')
    return errors


def record_revision(project, scope, summary, issue_ids=None, quote=None, reference=None):
    project = Path(project)
    if policy(project)['mode'] != 'fast' or scope not in ('minor', 'major') or not summary.strip():
        raise ValueError('Fast revision receipts need scope minor/major and an actual change summary')
    status, grant = delegation_status(project)
    if status != 'authorized':
        raise ValueError('Record the actual configuration authorization before delegated editing')
    delegated = scope == 'minor' and policy(project)['minor_edits'] == 'delegate' and not quote and not reference
    if not delegated and (not quote or not quote.strip() or not reference or not reference.strip()):
        raise ValueError('This revision requires the actual issue-specific user permission and source reference')
    record = {'source_sha256': sha256_file(project / 'creative/original.md'),
              'revision_sha256': sha256_file(project / 'creative/story-revised.md'), 'scope': scope,
              'summary': summary, 'issue_ids': issue_ids or [], 'at': utc_now(),
              'decision_kind': 'delegated' if delegated else 'user',
              'authorization_fingerprint': fingerprint(grant['configuration']) if delegated else None,
              'decision_quote': quote, 'decision_reference': reference}
    path = project / 'creative/revision.json'
    previous = read_json(path, {})
    record['history'] = [*previous.get('history', []), {key: val for key, val in previous.items() if key != 'history'}] if previous else []
    atomic_json(path, record)
    return path


def written_problems(project, parts):
    from shot_planning import problems as image_plan_problems
    from visual_continuity import binding_problems
    errors = binding_problems(project, parts)
    for part in selected_parts(project, parts):
        errors.extend(image_plan_problems(project, part))
        shots = read_json(part / 'shots.json', {}).get('shots', [])
        if not shots:
            errors.append(f'{part.name}: finish the written shots')
        for shot in shots:
            if not shot.get('visual_description') or not shot.get('camera_direction'):
                errors.append(f'{part.name}/{shot.get("id")}: finish visual intent and camera geography')
        expected = ' '.join(shot.get('narration', '') for shot in shots).split()
        narration = part / 'narration.txt'
        if expected and (not narration.is_file() or narration.read_text(encoding='utf-8-sig').split() != expected):
            errors.append(f'{part.name}: narration.txt differs from the written shots')
        speech = read_json(part / 'speech.json', {}).get('utterances', [])
        if speech and ' '.join(item.get('text', '') for item in speech).split() != expected:
            errors.append(f'{part.name}: speech.json differs from the written spoken text')
        if read_json(Path(project) / 'creative/intake.json').get('performance') in ('dialogue', 'mixed') and not speech:
            errors.append(f'{part.name}: write the cast-aware speech.json turns for the dialogue')
    return errors


def require_stage(project, stage='production', parts=None, tool=None):
    """Authorize the work, then check only its actual prerequisites."""
    project = Path(project).resolve()
    from story_git import require_story_branch
    require_story_branch(project)
    if stage not in STAGES:
        raise ValueError(f'Unknown production stage: {stage}')
    value = policy(project)
    if value['task'] != 'film':
        raise ValueError(f'This is a {value["task"]} task; media production is outside its configuration')
    delivery_errors = delivery_problems(project)
    if delivery_errors:
        raise ValueError('; '.join(delivery_errors))
    if value['mode'] == 'strict':
        from project_records import GATES, require_gates
        gates = GATES[:2] if stage == 'reference' else GATES[:4] if stage == 'audition' else GATES
        require_gates(project, gates)
        if stage in ('images', 'production', 'render', 'master', 'release'):
            from cast import ready_problems
            from visual_continuity import binding_problems
            problems = binding_problems(project, parts) + ready_problems(project, parts)
            if problems:
                raise ValueError('; '.join(problems))
        if stage in ('master', 'release'):
            from speech import current_problems
            problems = current_problems(project, selected_parts(project, parts))
            if stage == 'master':
                problems.extend(master_problems(project, parts))
            if problems:
                raise ValueError('; '.join(problems))
        return
    status, grant = delegation_status(project)
    if status != 'authorized':
        raise ValueError(f'Fast configuration authorization is {status}; record the actual decision once for this scope')
    if tool and tool not in grant['scope']['tools']:
        raise ValueError(f'{tool} is outside the authorized tool scope')
    errors = audit_problems(project)
    from part_continuity import problems as part_problems
    errors.extend(part_problems(project))
    if stage not in ('reference', 'audition', 'sound'):
        errors.extend(written_problems(project, parts))
    if stage in ('reference', 'images', 'production', 'render', 'master', 'qa', 'release'):
        dependencies = read_json(project / 'continuity/dependencies.json', {})
        if dependencies.get('review_status') != 'complete':
            errors.append('Finish the whole-story inventory and dependency map')
    if stage in ('images', 'production', 'render', 'master', 'qa', 'release'):
        from cast import ready_problems
        errors.extend(ready_problems(project, parts))
        from project_records import validate_continuity
        errors.extend(validate_continuity(project, parts))
        styles = read_json(project / 'continuity/entities.json').get('styles', {})
        style_ids = {shot.get('style_id') for part in selected_parts(project, parts)
                     for shot in read_json(part / 'shots.json').get('shots', [])}
        if not style_ids or any(not styles.get(identity, {}).get('reference_paths') for identity in style_ids):
            errors.append('Inspect and register the actual style proof/canonical references')
    if stage in ('narration', 'production', 'release'):
        intake = read_json(project / 'creative/intake.json')
        if intake.get('performance') != 'none':
            from studio_common import configuration
            narrator = read_json(project / 'audio/narrator.json')
            from speech_providers import ready_problems, validate_profile, voice_config
            try:
                validate_profile(narrator)
                speakers = {item.get('speaker', 'NARRATOR') for part in selected_parts(project, parts)
                            for item in read_json(part / 'speech.json', {}).get('utterances', [])} or {'NARRATOR'}
                configs = [voice_config(narrator, speaker) for speaker in speakers]
                for config in configs:
                    errors.extend(ready_problems(project, config))
                    if config['provider'] not in grant['scope']['tools']:
                        errors.append(config['provider'] + ' is outside the authorized speech tool scope')
                if any(config['provider'] == 'kokoro' for config in configs):
                    for field, name in (('model_sha256', 'model'), ('voices_sha256', 'voices')):
                        path = ROOT / configuration(project)['runtime'][name]
                        if not path.is_file() or narrator.get(field) != sha256_file(path):
                            errors.append(f'Record the actual Kokoro narrator {name} hash before speech production')
            except (ValueError, OSError) as error:
                errors.append(str(error))
    if stage in ('master', 'release'):
        for part in selected_parts(project, parts):
            try:
                require_preview(project, part.name)
            except (ValueError, OSError) as error:
                errors.append(str(error))
    if stage == 'master':
        errors.extend(master_problems(project, parts))
    if stage in ('master', 'release'):
        from speech import current_problems
        errors.extend(current_problems(project, selected_parts(project, parts)))
    if errors:
        raise ValueError('Studio work required: ' + '; '.join(dict.fromkeys(errors)))


def master_problems(project, parts):
    """Direct renderer calls enforce the same genuine review boundary as the runner."""
    from align_audio import reviewed_alignment
    project = Path(project)
    errors = []
    for part in selected_parts(project, parts):
        data = read_json(part / 'timeline.json')
        from listening import problems as listening_problems
        errors.extend(listening_problems(project, part.name))
        alignment = reviewed_alignment(part / data['narration_file']) if data.get('narration_file') else data.get('alignment', {})
        if alignment.get('review_warning') or any(not item.get('reviewed') for item in alignment.get('uncertain_ranges', [])):
            errors.append(f'{part.name}: inspect outstanding/stale word alignment ranges')
    errors.extend(image_problems(project, parts))
    return errors


def image_problems(project, parts):
    from quality import image_review_context
    project = Path(project)
    reviews = read_json(project / 'production/image-reviews.json', {}).get('reviews', {})
    errors = []
    for part in selected_parts(project, parts):
        data = read_json(part / 'timeline.json')
        written = {shot['id']: shot for shot in read_json(part / 'shots.json')['shots']}
        for shot in data['shots']:
            review = reviews.get(part.name + '/' + shot['id'], {})
            if (shot['id'] not in written or review.get('verdict') != 'passed'
                    or review.get('sha256') != sha256_file(part / shot['image'])
                    or review.get('context') != image_review_context(project, part.name, written[shot['id']])):
                errors.append(f'{part.name}/{shot["id"]}: current image/reference inspection is required')
    return errors


def require_download(project, url):
    from urllib.parse import urlparse
    if policy(project)['mode'] == 'strict':
        return None
    require_stage(project, 'sound', tool='https-audio')
    hosts = policy(project)['scope']['download_domains']
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.username or parsed.password:
        raise ValueError('The sound download host is outside the configured HTTPS source scope')
    return hosts


def image_scope(project, kind, provider, currency, parts=None):
    """The cumulative Fast budget covers image references/finals and cloud speech."""
    value = policy(project)
    if value['mode'] == 'fast':
        require_stage(project, 'reference' if kind == 'reference' else 'images', parts, tool=provider)
        scope = value['scope']
        if provider not in scope['external_upload']:
            raise ValueError('Image provider uploads are outside the authorized privacy scope')
        budget = scope['budget']
    else:
        authorization = read_json(Path(project) / 'production/authorizations.json')
        upload = authorization.get('external_upload', {})
        if upload.get('status') != 'approved' or not upload.get('decision_quote') or provider not in upload.get('tools', []):
            raise ValueError('Record the actual G6/reference-work privacy decision permitting story excerpts and reference uploads to this provider')
        budget = authorization.get('reference_work', {}) if kind == 'reference' else authorization.get('final_production_budget', {})
    if budget.get('currency') != currency:
        raise ValueError('Request currency differs from the authorized budget')
    return budget, value['mode'] == 'fast'


def presentation(data):
    """Review metadata can change without changing the picture/sound the user saw."""
    return {key: value for key, value in data.items() if key not in ('alignment', 'timing_source')}


def preview_inputs(project, part_id):
    project = Path(project).resolve()
    part = selected_parts(project, [part_id])[0]
    timeline = read_json(part / 'timeline.json')
    log = read_json(part / 'preview.render-log.json')
    current = fingerprint(presentation(timeline))
    if log.get('presentation_fingerprint') != current:
        raise ValueError(f'{part_id}: render the current preview before its review')
    files = [part / 'preview.mp4', part / timeline['audio_file']]
    if log.get('output_sha256') != sha256_file(files[0]) or log.get('audio_sha256') != sha256_file(files[1]):
        raise ValueError(f'{part_id}: preview bytes or audio changed since rendering')
    for shot in timeline['shots']:
        path = (part / shot['image']).resolve()
        if log.get('source_image_hashes', {}).get(str(path)) != sha256_file(path):
            raise ValueError(f'{part_id}: preview images changed since rendering')
        files.append(path)
    if read_json(project / 'creative/intake.json').get('subtitles') is not False:
        files.append(part / 'subtitles.srt')
    if log.get('subtitles_sha256') and log['subtitles_sha256'] != sha256_file(part / 'subtitles.srt'):
        raise ValueError(f'{part_id}: preview has older burned subtitles')
    for path in files:
        if not path.resolve().is_relative_to(project):
            raise ValueError('Snapshot preview assets inside the story project')
    return {'presentation': current, 'files': {path.resolve().relative_to(project).as_posix(): sha256_file(path) for path in files}}


def record_preview(project, part_id, quote, reference, listening_reviewed=False):
    if not quote.strip() or not reference.strip():
        raise ValueError('Record the actual user preview decision and its source reference')
    require_stage(project, 'render', [part_id])
    inputs = preview_inputs(project, part_id)
    path = Path(project) / 'production/preview-decisions.json'
    data = read_json(path, {'decisions': {}, 'history': []})
    if part_id in data['decisions']:
        data['history'].append(data['decisions'][part_id])
    data['decisions'][part_id] = {'part_id': part_id, 'status': 'accepted', 'decision_quote': quote,
                                'decision_reference': reference, 'at': utc_now(), 'inputs': inputs}
    if listening_reviewed:
        from listening import record
        record(project, part_id, quote, reference)
    atomic_json(path, data)
    return path


def require_preview(project, part_id):
    decision = read_json(Path(project) / 'production/preview-decisions.json', {}).get('decisions', {}).get(part_id, {})
    if decision.get('status') != 'accepted' or not decision.get('decision_quote') or not decision.get('decision_reference'):
        raise ValueError(f'{part_id}: present the preview and record the user decision before the master')
    if decision.get('inputs') != preview_inputs(project, part_id):
        raise ValueError(f'{part_id}: the preview decision is stale; present the changed preview')


def preset_path(name):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,59}', name):
        raise ValueError('Use a lowercase preset name with letters, digits and hyphens')
    return ROOT / 'presets' / (name + '.json')


def load_preset(name):
    data = read_json(preset_path(name))
    if set(data) - {'schema_version', 'workflow', 'intake', 'narrator', 'settings', 'style_references', 'voice_references'}:
        raise ValueError('Presets contain preferences only, never decisions or approval records')
    validate_policy(data['workflow'])
    if set(data.get('intake', {})) - set(PREFERENCES) or set(data.get('narrator', {})) - set(VOICE_FIELDS):
        raise ValueError('A preset contains story-specific data or unsupported voice fields')
    if data.get('narrator', {}).get('cast'):
        raise ValueError('Assign story-specific cast IDs in the project; presets store provider/narrator preferences')
    validate_preferences(data)
    return data


def validate_preferences(data):
    if not isinstance(data, dict) or set(data) - {'schema_version', 'workflow', 'intake', 'narrator', 'settings', 'style_references', 'voice_references'}:
        raise ValueError('Configuration accepts preferences only')
    for section, allowed in (('intake', PREFERENCES + PROJECT_FIELDS), ('narrator', VOICE_FIELDS)):
        if not isinstance(data.get(section, {}), dict) or set(data.get(section, {})) - set(allowed):
            raise ValueError(f'Unsupported {section} preference')
    if 'workflow' in data:
        validate_policy(data['workflow'])
    if not isinstance(data.get('settings', {}), dict) or set(data.get('settings', {})) - {'render_profiles', 'mix', 'image_provider', 'jobs'}:
        raise ValueError('Presets configure render, mix, image provider and job settings only')
    reference_sources(data.get('style_references', []))
    voice_reference_sources(data.get('voice_references', []))


def apply_preferences(project, data, replace=False):
    project = Path(project)
    validate_preferences(data)
    for section, name, allowed in (
        ('intake', 'creative/intake.json', PREFERENCES + PROJECT_FIELDS),
        ('narrator', 'audio/narrator.json', VOICE_FIELDS),
    ):
        record = read_json(project / name)
        for key, value in data.get(section, {}).items():
            if key not in allowed:
                raise ValueError(f'Unsupported {section} preference: {key}')
            if replace or record.get(key) in (None, '', [], {}):
                record[key] = value
        atomic_json(project / name, record)
    if 'workflow' in data:
        validate_policy(data['workflow'])
        atomic_json(project / 'production/workflow.json', data['workflow'])
    if data.get('settings'):
        settings = read_json(project / 'production/settings.json')
        for section, values in data['settings'].items():
            if isinstance(values, dict) and isinstance(settings.get(section), dict):
                settings[section].update(values)
            else:
                settings[section] = values
        atomic_json(project / 'production/settings.json', settings)
    if data.get('style_references'):
        snapshot_references(project, data['style_references'])
    if data.get('voice_references'):
        snapshot_voice_references(project, data['voice_references'])


def voice_reference_sources(records):
    if not isinstance(records, list):
        raise ValueError('voice_references must be a list of exact selected audio snapshots')
    sources = []
    for record in records:
        if set(record) != {'provider', 'source_path', 'sha256'} or record['provider'] != 'chatterbox':
            raise ValueError('Voice snapshots record a local Chatterbox provider, source path and actual SHA-256')
        source = Path(record['source_path']).expanduser()
        source = (source if source.is_absolute() else ROOT / source).resolve()
        if not source.is_file() or source.suffix.lower() not in ('.wav', '.mp3', '.flac', '.ogg', '.m4a') or sha256_file(source) != record['sha256']:
            raise ValueError('A selected voice reference is missing, changed or unsupported')
        sources.append(source)
    return sources


def snapshot_voice_references(project, records):
    import shutil
    project = Path(project).resolve()
    sources = voice_reference_sources(records)
    profile = read_json(project / 'audio/narrator.json')
    manifest_path = project / 'audio/voice-references/manifest.json'
    manifest = read_json(manifest_path, {'schema_version': 1, 'references': []})
    for record, source in zip(records, sources):
        relative = 'audio/voice-references/' + record['provider'] + '-' + record['sha256'][:16] + source.suffix.lower()
        target = project / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and sha256_file(target) != record['sha256']:
            raise ValueError('A voice snapshot filename already contains different bytes')
        if not target.exists():
            shutil.copy2(source, target)
        if not any(item['sha256'] == record['sha256'] for item in manifest['references']):
            manifest['references'].append(dict(record, snapshot_path=relative, copied_at_utc=utc_now(), rights_status='requires actual usage evidence'))
        profile.setdefault('providers', {}).setdefault(record['provider'], {})['reference_audio'] = relative
    atomic_json(project / 'audio/narrator.json', profile)
    atomic_json(manifest_path, manifest)


def reference_sources(records):
    sources = []
    for record in records:
        source = Path(record['source_path']).expanduser()
        source = (source if source.is_absolute() else ROOT / source).resolve()
        if source.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp') or not source.is_file():
            raise ValueError('A saved style reference is missing or has an unsupported format')
        if sha256_file(source) != record.get('sha256'):
            raise ValueError('A saved style reference changed; resolve its original path/hash')
        sources.append(source)
    return sources


def snapshot_references(project, records):
    import shutil
    project = Path(project).resolve()
    sources = reference_sources(records)
    path = project / 'references/style/manifest.json'
    manifest = read_json(path)
    for source in sources:
        digest = sha256_file(source)
        if any(record.get('sha256') == digest for record in manifest['references']):
            continue
        index = len(manifest['references']) + 1
        target = project / 'references/style' / f'ref_{index:03d}{source.suffix.lower()}'
        if target.exists():
            raise ValueError('A style snapshot filename is already used; preserve it and resolve its registry')
        shutil.copy2(source, target)
        manifest['references'].append({'id': f'REF-STYLE-{index:03d}', 'source_path': str(source),
                                      'snapshot_path': target.relative_to(project).as_posix(), 'sha256': digest,
                                      'role': 'visual treatment only', 'status': 'draft', 'copied_at_utc': utc_now()})
    atomic_json(path, manifest)


def save_preset(project, name, replace=False):
    project, path = Path(project).resolve(), preset_path(name)
    if path.exists() and not replace:
        raise ValueError('Preset exists; use --replace for an intentional configuration update')
    intake, narrator = read_json(project / 'creative/intake.json'), read_json(project / 'audio/narrator.json')
    # A user may have changed NARRATOR through a role override. Save that actual
    # narrator preference without carrying another story's character mappings.
    from speech_providers import voice_config
    selected_narrator = voice_config(narrator)
    narrator = copy.deepcopy(narrator)
    narrator.update({key: selected_narrator[key] for key in ('provider', 'model', 'voice', 'speed', 'language')})
    narrator.setdefault('providers', {})[selected_narrator['provider']] = selected_narrator['options']
    references = []
    for record in read_json(project / 'references/style/manifest.json', {}).get('references', []):
        source = (project / record['snapshot_path']).resolve()
        if record.get('sha256') != sha256_file(source):
            raise ValueError('Selected style snapshot changed; resolve its provenance before saving a preset')
        references.append({'source_path': str(source), 'sha256': record['sha256'], 'role': 'visual treatment only'})
    voice_references = []
    for provider, options in narrator.get('providers', {}).items():
        if options.get('reference_audio'):
            from project_records import artifact_path
            source = artifact_path(project, options['reference_audio'])
            voice_references.append({'provider': provider, 'source_path': str(source), 'sha256': sha256_file(source)})
    data = {'schema_version': 1, 'workflow': policy(project),
            'intake': {key: intake[key] for key in PREFERENCES if intake.get(key) is not None},
            'narrator': {key: narrator[key] for key in VOICE_FIELDS if key != 'cast' and narrator.get(key) is not None},
            'settings': read_json(project / 'production/settings.json'), 'style_references': references,
            'voice_references': voice_references}
    validate_preferences(data)
    atomic_json(path, data)
    return path


@hash_session()
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    configure = sub.add_parser('configure')
    configure.add_argument('project', type=Path)
    configure.add_argument('--file', type=Path)
    configure.add_argument('--preset')
    configure.add_argument('--mode', choices=('fast', 'strict'))
    configure.add_argument('--task', choices=('story', 'storyboard', 'film'))
    consent = sub.add_parser('authorize')
    consent.add_argument('project', type=Path)
    consent.add_argument('--decision', required=True)
    consent.add_argument('--decision-reference', required=True)
    preview = sub.add_parser('approve-preview')
    preview.add_argument('project', type=Path)
    preview.add_argument('--part', required=True)
    preview.add_argument('--decision', required=True)
    preview.add_argument('--decision-reference', required=True)
    preview.add_argument('--listening-reviewed', action='store_true', help='Actual user also listened to the complete preview voices/sound')
    revision = sub.add_parser('record-revision')
    revision.add_argument('project', type=Path)
    revision.add_argument('--scope', choices=('minor', 'major'), required=True)
    revision.add_argument('--summary', required=True)
    revision.add_argument('--issue-ids', nargs='*', default=[])
    revision.add_argument('--decision')
    revision.add_argument('--decision-reference')
    presets = sub.add_parser('preset')
    presets.add_argument('operation', choices=('list', 'show', 'save'))
    presets.add_argument('name', nargs='?')
    presets.add_argument('--from-project', type=Path)
    presets.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    try:
        if getattr(args, 'project', None):
            from story_git import require_story_branch
            require_story_branch(args.project)
        if args.action == 'configure':
            if args.file and args.preset:
                raise ValueError('Choose a configuration file or a saved preset')
            data = read_json(args.file) if args.file else load_preset(args.preset) if args.preset else {}
            if set(data) - {'schema_version', 'workflow', 'intake', 'narrator', 'settings', 'style_references'}:
                raise ValueError('Configuration accepts preferences, not authorization or review records')
            value = copy.deepcopy(data.get('workflow', policy(args.project)))
            if args.mode:
                value['mode'] = args.mode
            if args.task:
                value['task'] = args.task
            data['workflow'] = value
            apply_preferences(args.project, data, replace=True)
            print(args.project / 'production/workflow.json')
            print('Configuration saved. Prior permissions are never copied from a preset.')
        elif args.action == 'authorize':
            authorize(args.project, args.decision, args.decision_reference)
            print(args.project / 'production/delegation.json')
        elif args.action == 'approve-preview':
            print(record_preview(args.project, args.part, args.decision, args.decision_reference, args.listening_reviewed))
        elif args.action == 'record-revision':
            print(record_revision(args.project, args.scope, args.summary, args.issue_ids, args.decision, args.decision_reference))
        elif args.operation == 'list':
            print('\n'.join(path.stem for path in sorted((ROOT / 'presets').glob('*.json'))))
        elif args.operation == 'show':
            import json
            print(json.dumps(load_preset(args.name or 'default'), indent=2, ensure_ascii=False))
        else:
            if not args.name or not args.from_project:
                raise ValueError('Saving a preset needs a name and --from-project')
            print(save_preset(args.from_project, args.name, args.replace))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
