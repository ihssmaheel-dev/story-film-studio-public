#!/usr/bin/env python3
"""Inspect or change a story voice without generating speech or expanding provider scope."""
import argparse
import copy
from pathlib import Path
import re

from speech_providers import PROVIDERS, remote, validate_profile, voice_config
from story_git import require_story_branch
from studio_common import atomic_json, read_json, record_lock, sha256_file, utc_now


def audition_profile(profile, speaker='NARRATOR', provider=None, voice=None, model=None):
    if speaker != 'NARRATOR' and speaker not in profile.get('cast', {}):
        raise ValueError('Assign the character voice before auditioning speaker ' + speaker)
    resolved = voice_config(profile, speaker)
    result = copy.deepcopy(profile)
    chosen = provider or resolved['provider']
    result.update(provider=chosen, model=model or (resolved['model'] if chosen == resolved['provider'] else None),
                  voice=voice or (resolved['voice'] if chosen == resolved['provider'] else None),
                  speed=resolved['speed'], language=resolved['language'], cast={})
    if chosen == resolved['provider']:
        result.setdefault('providers', {})[chosen] = resolved['options']
    validate_profile(result)
    return result


def snapshot_for(project, grant, profile, **overrides):
    from workflow import configuration_snapshot
    return configuration_snapshot(project, grant.get('intake_fields'),
                                  overrides.get('delegate_voice', grant.get('delegate_voice', False)),
                                  grant.get('pronunciation_keys'),
                                  overrides.get('speech_choices', grant.get('speech_choices')),
                                  narrator_override=profile)


def choice_mask(grant, speaker, explicit_model):
    """Bind only the user's new role choice; keep other delegated casting delegated."""
    choices = copy.deepcopy(grant.get('speech_choices'))
    if choices is None:
        choices = {'delegate_model': True, 'providers': {}, 'cast': {}, 'cast_effective': {}}
    fields = choices.setdefault('cast', {}).setdefault(speaker, {})
    fields.update(provider=True, voice=True)
    effective = choices.setdefault('cast_effective', {}).setdefault(speaker, [])
    for name in ('provider', 'voice', *(['model'] if explicit_model else [])):
        if name not in effective:
            effective.append(name)
    if explicit_model:
        fields['model'] = True
        if speaker == 'NARRATOR':
            choices['delegate_model'] = False
    return {'delegate_voice': False if speaker == 'NARRATOR' else grant.get('delegate_voice', False),
            'speech_choices': choices}


def affected_parts(project, before, after):
    """Compare effective roles actually used, leaving other speakers and image assets reusable."""
    result = []
    for part in sorted((Path(project) / 'parts').glob('part_*')):
        timeline = read_json(part / 'timeline.json', {})
        if not timeline.get('narration_file'):
            continue
        turns = read_json(part / 'speech.json', {}).get('utterances', [])
        speakers = {turn.get('speaker', 'NARRATOR') for turn in turns} if turns else {'NARRATOR'}
        changed = sorted(speaker for speaker in speakers if voice_config(before, speaker) != voice_config(after, speaker))
        if changed:
            result.append({'part': part.name, 'speakers': changed,
                           'rebuild': ['changed speech clips', 'alignment/timeline', 'mix/subtitles', 'preview/master/playback'],
                           'images': 'reuse unchanged source images; re-check timing and existing camera plan'})
    return result


def set_voice(project, speaker, voice, reason, provider=None, model=None, decision=None, reference=None):
    """Record agent casting or a real user's scoped change; perform no provider requests."""
    from workflow import delegation_status, policy
    project = Path(project).resolve()
    require_story_branch(project)
    if not re.fullmatch(r'NARRATOR|CHAR-\d{3,}', speaker):
        raise ValueError('Select NARRATOR or a canonical CHAR-### speaker')
    if not isinstance(voice, str) or not voice.strip() or not reason or not reason.strip():
        raise ValueError('Supply an actual selected voice ID/label and a story-specific selection reason')
    if bool(decision) != bool(reference) or (decision is not None and (not decision.strip() or not reference.strip())):
        raise ValueError('A user voice change needs its actual decision quotation and source reference together')
    if provider is not None and provider not in PROVIDERS:
        raise ValueError('Choose a supported speech provider')
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ValueError('A model override must be an actual nonempty model ID')
    if speaker != 'NARRATOR' and speaker not in read_json(project / 'continuity/entities.json', {}).get('characters', {}):
        raise ValueError('Register the story character before assigning its voice: ' + speaker)
    with record_lock(project / 'production/voice-choice.lock'):
        path = project / 'audio/narrator.json'
        before = read_json(path)
        validate_profile(before)
        previous = voice_config(before, speaker)
        after = copy.deepcopy(before)
        chosen = provider or previous['provider']
        role = after.setdefault('cast', {}).setdefault(speaker, {})
        if chosen != previous['provider']:
            role.pop('options', None)
        role.update(provider=chosen, voice=voice.strip(),
                    model=model or (previous['model'] if chosen == previous['provider'] else PROVIDERS[chosen]['model']))
        # Other speakers retain their global defaults; narrator changes are role-specific.
        validate_profile(after)
        selected = voice_config(after, speaker)
        if selected == previous and not decision:
            return {'changed': False, 'speaker': speaker, 'voice': selected, 'affected_parts': []}
        value = policy(project)
        status, grant = delegation_status(project) if value['mode'] == 'fast' else ('strict', {})
        if status == 'stale':
            raise ValueError('Resolve the stale configuration first; a voice change cannot authorize unrelated changes')
        if grant:
            if selected['provider'] not in grant['scope']['tools']:
                raise ValueError('The new provider is outside the authorized tools; configure its scope first')
            if remote(selected) and selected['provider'] not in grant['scope']['external_upload']:
                raise ValueError('The new provider is outside the authorized upload scope')
        before_snapshot = snapshot_for(project, grant, before) if status == 'authorized' else None
        after_snapshot = snapshot_for(project, grant, after) if status == 'authorized' else None
        delegated = status == 'authorized' and before_snapshot == after_snapshot
        previous_selected = previous.get('voice') and (speaker == 'NARRATOR' or speaker in before.get('cast', {}))
        if not decision and not delegated and previous_selected:
            raise ValueError('This replaces a selected voice. Record the actual user change request; do not ask for the full configuration again.')
        if status == 'authorized' and before_snapshot != after_snapshot and not decision:
            raise ValueError('This changes a bound provider/model/voice; record the actual user change request')
        history_path = project / 'audio/voice-decisions.json'
        history = read_json(history_path, {'schema_version': 1, 'changes': []})
        plan_path = project / 'audio/voice-plan.json'
        plan = read_json(plan_path, {'schema_version': 1, 'roles': {}, 'selection_policy': 'story-fit'})
        if (not isinstance(history.get('changes'), list) or not isinstance(plan.get('roles', {}), dict)
                or not isinstance(plan.get('roles', {}).get(speaker, {}), dict)):
            raise ValueError('Voice history changes must be a list and the plan must contain role objects')
        old_hash = sha256_file(path)
        revision_path = project / 'audio/voice-revisions' / (old_hash + '.json')
        if revision_path.exists() and sha256_file(revision_path) != old_hash:
            raise ValueError('The retained voice revision differs from its source profile')
        # Retain the exact former bytes, including selected local-reference paths.
        revision_path.parent.mkdir(parents=True, exist_ok=True)
        if not revision_path.exists():
            revision_path.write_bytes(path.read_bytes())
        impact = affected_parts(project, before, after)
        receipt = {'id': 'VOICE-' + str(len(history['changes']) + 1).zfill(3), 'at': utc_now(),
                   'speaker': speaker, 'previous': previous, 'selected': selected,
                   'reason': reason.strip(), 'source_sha256': sha256_file(project / 'creative/original.md'),
                   'decision_kind': 'user' if decision else 'delegated' if delegated else 'draft-selection',
                   'decision_quote': decision, 'decision_reference': reference,
                   'previous_profile_sha256': old_hash,
                   'previous_profile': revision_path.relative_to(project).as_posix(), 'affected_parts': impact,
                   'audition_status': 'requires actual listening evidence or current suitable audition; no listening performed by this command'}
        new_grant = None
        if status == 'authorized' and decision:
            new_grant = copy.deepcopy(grant)
            mask = choice_mask(grant, speaker, model is not None)
            new_grant.update(mask)
            new_grant['configuration'] = snapshot_for(project, grant, after, **mask)
            if any(new_grant['configuration'][name] != grant['configuration'][name]
                   for name in grant['configuration'] if name != 'voice_preferences'):
                raise ValueError('Only the voice choice can be amended; another configuration input changed')
            new_grant['history'] = [*grant.get('history', []),
                                    {key: val for key, val in grant.items() if key != 'history'}]
            new_grant.setdefault('voice_changes', []).append({
                'id': receipt['id'], 'decision_quote': decision, 'decision_reference': reference,
                'at': receipt['at'], 'speaker': speaker, 'previous_configuration': grant['configuration'],
                'configuration': new_grant['configuration']})
        atomic_json(path, after)
        receipt['profile_sha256'] = sha256_file(path)
        history['changes'].append(receipt)
        atomic_json(history_path, history)
        plan['source_sha256'] = receipt['source_sha256']
        entry = plan.setdefault('roles', {}).setdefault(speaker, {})
        entry.update(selected=selected, selection_reason=reason.strip(), decision_id=receipt['id'])
        if selected != previous:
            entry['listening_status'] = 'pending actual audition/listening evidence for this selection'
            plan['status'] = 'provisional'
        atomic_json(plan_path, plan)
        if new_grant is not None:
            atomic_json(project / 'production/delegation.json', new_grant)
        if value['mode'] == 'strict':
            from project_records import approval_status
            approval_status(project, refresh=True)
        return {'changed': True, 'speaker': speaker, 'voice': selected, 'receipt': receipt['id'],
                'affected_parts': impact, 'speech_generated': False,
                'configuration_status': delegation_status(project)[0] if value['mode'] == 'fast' else 'strict; affected gates require review'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    status = sub.add_parser('status')
    status.add_argument('project', type=Path)
    change = sub.add_parser('set')
    change.add_argument('project', type=Path)
    change.add_argument('--speaker', default='NARRATOR')
    change.add_argument('--voice', required=True)
    change.add_argument('--provider', choices=tuple(PROVIDERS))
    change.add_argument('--model')
    change.add_argument('--reason', required=True)
    change.add_argument('--decision')
    change.add_argument('--decision-reference')
    args = parser.parse_args()
    try:
        if args.action == 'set':
            result = set_voice(args.project, args.speaker, args.voice, args.reason,
                               args.provider, args.model, args.decision, args.decision_reference)
        else:
            profile = read_json(args.project / 'audio/narrator.json')
            validate_profile(profile)
            result = {'roles': {speaker: voice_config(profile, speaker)
                                for speaker in dict.fromkeys(['NARRATOR', *profile.get('cast', {})])},
                      'plan': read_json(args.project / 'audio/voice-plan.json', {}),
                      'changes': read_json(args.project / 'audio/voice-decisions.json', {}).get('changes', [])}
        import json
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
