"""Actual complete-preview listening can cover the used sound ranges in Fast mode."""
from pathlib import Path

from production_inputs import mix_plan
from studio_common import atomic_json, read_json, sha256_file, utc_now


def context(project, part_id):
    project = Path(project).resolve()
    part = project / 'parts' / part_id
    timeline = read_json(part / 'timeline.json')
    manifest = (part / timeline.get('audio_manifest', '../../audio/assets.json')).resolve()
    assets = read_json(manifest)['assets']
    sound = {}
    for cue in timeline.get('audio_cues', []):
        asset = assets[cue['asset_id']]
        actual = sha256_file(manifest.parent / asset['file'])
        if actual != asset['sha256']:
            raise ValueError(cue['asset_id'] + ': sound bytes changed')
        sound[cue['asset_id']] = {'file': asset['file'], 'sha256': actual}
    narration = part / timeline['narration_file'] if timeline.get('narration_file') else None
    return {'plan': mix_plan(timeline), 'sound': sound,
            'narration_sha256': sha256_file(narration) if narration else None,
            'mix_sha256': sha256_file(part / timeline['audio_file'])}


def current(project, part_id):
    from workflow import policy
    if policy(project)['mode'] != 'fast':
        return False
    record = read_json(Path(project) / 'production/preview-listening.json', {}).get('reviews', {}).get(part_id, {})
    if not record.get('decision_quote') or not record.get('decision_reference') or record.get('reviewer') != 'user':
        return False
    try:
        return record.get('inputs') == context(project, part_id)
    except (OSError, ValueError, KeyError):
        return False


def record(project, part_id, quote, reference):
    from workflow import policy
    if policy(project)['mode'] != 'fast' or not quote.strip() or not reference.strip():
        raise ValueError('Fast listening review needs the actual user decision and source')
    path = Path(project) / 'production/preview-listening.json'
    value = read_json(path, {'reviews': {}, 'history': []})
    if part_id in value['reviews']:
        value['history'].append(value['reviews'][part_id])
    value['reviews'][part_id] = {'reviewer': 'user', 'decision_quote': quote, 'decision_reference': reference,
                               'inputs': context(project, part_id), 'at': utc_now(),
                               'scope': 'Actual complete mixed preview, its selected voices, and the used sound ranges; no unused source range or agent listening is claimed.'}
    atomic_json(path, value)
    plan_path = Path(project) / 'audio/voice-plan.json'
    plan = read_json(plan_path, {})
    plan.setdefault('complete_preview_listening', {})[part_id] = {
        'receipt': 'production/preview-listening.json', 'decision_reference': reference,
        'evidence': 'Actual user listened to the selected voices in this complete mixed preview.'}
    atomic_json(plan_path, plan)
    return path


def problems(project, part_id, allow_pending=False):
    part = Path(project) / 'parts' / part_id
    timeline = read_json(part / 'timeline.json')
    manifest = (part / timeline.get('audio_manifest', '../../audio/assets.json')).resolve()
    assets = read_json(manifest, {'assets': {}})['assets']
    reviewed_mix = current(project, part_id)
    issues = []
    for identity in {cue['asset_id'] for cue in timeline.get('audio_cues', [])}:
        asset = assets.get(identity, {})
        if asset.get('rights_status') != 'verified' or not asset.get('rights_evidence'):
            issues.append(identity + ': verify actual sound usage rights')
        elif asset.get('qa_status') == 'failed':
            issues.append(identity + ': failed sound QA needs repair')
        elif not (asset.get('qa_status') == 'passed' and asset.get('qa_notes')) and not (reviewed_mix or allow_pending):
            issues.append(identity + ': actual listening review is pending')
    return issues
