"""One conservative spending ledger for image and speech requests."""
import base64
import json
import math
from pathlib import Path
import re

from studio_common import atomic_json, read_json, record_lock, sha256_file, utc_now


def reserved_cost(record):
    if record.get('cost_mode') == 'unreported_builtin' and record.get('actual_cost') is None:
        # The separately authorized built-in call count is not a zero-dollar
        # price. Its unknown charge is reported separately from this cash ledger.
        return sum(reserved_cost(item) for item in record.get('history', []))
    amount = record.get('actual_cost')
    if amount is None:
        amount = record.get('estimated_cost', 0)
    return amount + sum(reserved_cost(item) for item in record.get('history', []))


def spent_or_reserved(project, currency, shared=True, kind='final'):
    total = 0.0
    for folder in ('production/image-jobs', 'production/speech-jobs'):
        for path in (Path(project) / folder).glob('*.json'):
            record = read_json(path)
            if not shared and record.get('budget_kind', record.get('kind', 'final')) != kind:
                continue
            amount = reserved_cost(record)
            if amount and record.get('currency') != currency:
                raise ValueError('Outstanding provider costs use a different currency; reconcile the budget first')
            total += amount
    return total


def speech_scope(project, provider, currency, parts=None, purpose='final', external=True, endpoint=None):
    from workflow import policy, require_stage
    from project_records import require_gates
    project = Path(project)
    require_stage(project, 'audition' if purpose == 'audition' else 'narration', parts, tool=provider)
    value = policy(project)
    if value['mode'] == 'fast':
        scope = value['scope']
        if external and provider not in scope['external_upload']:
            raise ValueError('Selected speech provider is outside the authorized upload scope')
        if provider == 'custom-http' and external:
            grant = read_json(project / 'production/delegation.json')
            profile = read_json(project / 'audio/narrator.json')
            choices = grant.get('speech_choices', {})
            allowed = set()
            if 'endpoint' in choices.get('providers', {}).get(provider, []):
                allowed.add(profile.get('providers', {}).get(provider, {}).get('endpoint'))
            for speaker, fields in choices.get('cast', {}).items():
                current = profile.get('cast', {}).get(speaker, {})
                if current.get('provider', profile.get('provider', 'kokoro')) == provider and 'endpoint' in fields.get('options', []):
                    allowed.add(current.get('options', {}).get('endpoint'))
            if endpoint not in allowed:
                raise ValueError('Include the actual custom speech endpoint in the displayed authorization before external uploads')
        budget, shared = scope['budget'], True
    else:
        authorization = read_json(project / 'production/authorizations.json')
        if purpose == 'audition':
            work = authorization.get('audition_work', {})
            if work.get('status') != 'approved' or not work.get('decision_quote') or provider not in work.get('tools', []):
                raise ValueError('Selected speech provider needs actual audition tool/expense authorization')
            budget = work
        else:
            require_gates(project, ['G1', 'G2', 'G3', 'G4', 'G5', 'G6'])
            budget = authorization.get('final_production_budget', {})
        if external:
            upload = authorization.get('external_upload', {})
            if upload.get('status') != 'approved' or not upload.get('decision_quote') or provider not in upload.get('tools', []):
                raise ValueError('Selected speech provider needs actual upload authorization')
        shared = False
    if budget.get('currency') != currency:
        raise ValueError('Speech currency differs from the authorized budget')
    return budget, shared


def reconcile_speech(project, request_id, outcome, actual_cost, evidence, audio=None):
    """Record a known provider outcome. Evidence is an actual receipt/history reference."""
    project = Path(project).resolve()
    if (not re.fullmatch(r'[0-9a-f]{64}', request_id) or outcome not in ('failed', 'received')
            or isinstance(actual_cost, bool) or not isinstance(actual_cost, (int, float))
            or not math.isfinite(actual_cost) or actual_cost < 0 or not evidence.strip()):
        raise ValueError('Use an actual request ID, failed/received outcome, finite billed cost and real evidence')
    path = project / 'production/speech-jobs' / (request_id + '.json')
    with record_lock(project / 'production/provider-budget.lock'):
        record = read_json(path)
        if record.get('status') not in ('requesting', 'needs_attention', 'received'):
            raise ValueError('The speech request has no outcome awaiting reconciliation')
        if outcome == 'received':
            if audio is None or not Path(audio).is_file():
                raise ValueError('Import the actual audio recovered from the provider')
            raw_audio = Path(audio).read_bytes()
            # Check this is decodable audio before replacing any response record.
            from studio_common import executable, process
            probe = process([executable('ffprobe'), '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', str(Path(audio).resolve())])
            if probe.stdout.strip() != 'audio':
                raise ValueError('The recovered provider file has no actual audio stream')
            field = record['recipe']['base64_field']
            if field:
                result, current = {}, None
                current = result
                for key in field.split('.')[:-1]:
                    current[key] = {}
                    current = current[key]
                current[field.split('.')[-1]] = base64.b64encode(raw_audio).decode('ascii')
                raw = json.dumps(result).encode('utf-8')
            else:
                raw = raw_audio
            target = project / 'production/cache/speech-responses' / (request_id + '.response')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            record.update(status='received', response_file=target.relative_to(project).as_posix(), response_sha256=sha256_file(target))
        else:
            if record.get('status') == 'received':
                raise ValueError('A received audio result cannot be relabeled as an ungenerated failure')
            record['status'] = 'known_failed'
        record.update(actual_cost=actual_cost, reconciliation={'at': utc_now(), 'evidence': evidence, 'outcome': outcome})
        atomic_json(path, record)
    return path
