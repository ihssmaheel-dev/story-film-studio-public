"""Provider-independent, cast-aware speech with measured clips and resumable cloud calls."""
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.request import Request, build_opener

from project_records import artifact_path
from speech_providers import (NoRedirect, PROVIDERS, decode_audio, fetch_audio, http_request,
                              number, ready_problems, remote, validate_profile, voice_config)
from studio_common import (ROOT, atomic_json, configuration, executable, fingerprint, process,
                           read_json, record_lock, sha256_file, utc_now)


def _segments(text, limit):
    result, current = [], ''
    for sentence in re.split(r'(?<=[.!?])\s+|\n\s*\n', text.strip()):
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence.encode('utf-16-le')) // 2 > limit:
            raise ValueError('A speech sentence exceeds this provider turn limit; write an explicit shorter speech.json turn')
        candidate = (current + ' ' + sentence).strip()
        if current and len(candidate.encode('utf-16-le')) // 2 > limit:
            result.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        result.append(current)
    return result


def plan_speech(project, profile, text, script=None, *, require_runtime=True):
    """Resolve only the selected part; no credentials, network or model inference."""
    project = Path(project).resolve()
    validate_profile(profile)
    explicit = read_json(script, {}).get('utterances', []) if script else []
    if not isinstance(explicit, list):
        raise ValueError('speech.json utterances must be a list')
    if explicit:
        turns = [dict(item) for item in explicit]
    else:
        base = voice_config(profile)
        limit = base['options'].get('max_characters', 450 if base['provider'] == 'chatterbox' else 1800)
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 10000:
            raise ValueError('max_characters must be an integer from 1 to 10000')
        turns = [{'id': f'UTT-{index:04d}', 'speaker': 'NARRATOR', 'text': item}
                 for index, item in enumerate(_segments(text, limit), 1)]
    if not turns or any(not isinstance(item.get('text'), str) or not item['text'].strip() for item in turns):
        raise ValueError('Speech text must contain actual spoken words')
    if ' '.join(item['text'] for item in turns).split() != text.split():
        raise ValueError('speech.json spoken text must match narration.txt exactly; speaker names/directions stay outside spoken text')
    resolved, ids = [], set()
    for index, turn in enumerate(turns):
        if set(turn) - {'id', 'speaker', 'text', 'direction', 'pause_after', 'audio_file', 'sha256', 'source', 'take'}:
            raise ValueError('Unsupported speech turn fields')
        identity, speaker = turn.get('id', ''), turn.get('speaker', 'NARRATOR')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', identity) or identity in ids:
            raise ValueError('Speech turns need unique stable IDs')
        ids.add(identity)
        if speaker != 'NARRATOR' and speaker not in profile.get('cast', {}):
            raise ValueError('Assign an explicit cast voice for speaker ' + str(speaker))
        config = voice_config(profile, speaker)
        problems = ready_problems(project, config, require_runtime=require_runtime)
        if problems:
            raise ValueError('; '.join(problems))
        direction = turn.get('direction', '')
        take = turn.get('take', 1)
        if not isinstance(take, int) or isinstance(take, bool) or take < 1:
            raise ValueError('A speech take must be a positive integer; change it only for an intentional retake')
        pause = turn.get('pause_after', profile.get('pause', 0.15) if index < len(turns) - 1 else 0)
        if not isinstance(direction, str) or len(direction) > 200 or not number(pause) or not 0 <= pause <= 10:
            raise ValueError('Use a short acting direction and a finite pause between zero and ten seconds')
        sources = {}
        if config['options'].get('reference_audio'):
            source = artifact_path(project, config['options']['reference_audio'])
            sources[source.relative_to(project).as_posix()] = sha256_file(source)
        if config['provider'] == 'provided':
            if not turn.get('audio_file') or not turn.get('sha256'):
                raise ValueError('Imported voice turns require audio_file and its actual sha256')
            source = artifact_path(project, turn['audio_file'])
            if sha256_file(source) != turn['sha256']:
                raise ValueError('Imported voice file differs from its recorded checksum')
            sources[source.relative_to(project).as_posix()] = turn['sha256']
            if direction:
                raise ValueError('Directions for imported audio must already be performed in the supplied recording')
        elif config['provider'] == 'kokoro':
            if direction:
                raise ValueError('Kokoro does not interpret acting tags; choose a supported provider/control or an auditioned recording')
        else:
            # Validate directions, limits and provider-specific fields before any paid turn.
            if config['provider'] == 'chatterbox' and len(turn['text']) > 500:
                raise ValueError('Chatterbox turns must fit 500 characters; split at meaningful speech boundaries')
            http_request(config, turn['text'], direction)
        resolved.append(dict(turn, speaker=speaker, direction=direction, take=take, pause_after=pause, config=config, source_hashes=sources))
    return resolved


def input_fingerprint(turns):
    return fingerprint({'revision': 1, 'turns': [_performance_turn(turn) for turn in turns]})


def _performance_turn(turn, clip=False):
    value = dict(turn, config=dict(turn['config'], options={key: item for key, item in turn['config']['options'].items()
                                                         if key not in ('price_per_1000_characters', 'currency', 'timeout_seconds')}))
    value.pop('source', None)  # Usage-evidence notes do not change the performed audio.
    if clip:
        value.pop('pause_after', None)
        value.pop('id', None)
    return value


def current_problems(project, parts, *, require_runtime=True):
    project = Path(project)
    profile = read_json(project / 'audio/narrator.json')
    errors = []
    for part in parts:
        timeline = read_json(part / 'timeline.json')
        if not timeline.get('narration_file'):
            continue
        chunks = read_json((part / timeline['narration_file']).with_suffix('.chunks.json'), {})
        if chunks.get('speech_input_fingerprint'):
            try:
                turns = plan_speech(project, profile, (part / 'narration.txt').read_text(encoding='utf-8-sig'), part / 'speech.json', require_runtime=require_runtime)
                if chunks['speech_input_fingerprint'] != input_fingerprint(turns):
                    errors.append(part.name + ': rebuild speech for the current cast, provider or performance script')
            except (ValueError, OSError) as error:
                errors.append(part.name + ': ' + str(error))
    return errors


class SpeechSession:
    def __init__(self, project, profile, cache=None, purpose='final'):
        self.project = Path(project).resolve()
        self.profile, self.purpose = profile, purpose
        self.cache = Path(cache or self.project / 'production/cache/tts').resolve()
        if not self.cache.is_relative_to(self.project):
            raise ValueError('Keep speech cache clips inside their story project')
        self.cache.mkdir(parents=True, exist_ok=True)
        self.kokoro, self.server_info = None, {}
        self.cache_hits = self.generated_chunks = 0

    def _kokoro(self):
        if self.kokoro is None:
            from narration import NarrationSession
            settings = configuration(self.project)['runtime']
            self.kokoro = NarrationSession(ROOT / settings['model'], ROOT / settings['voices'], self.cache)
            if self.profile.get('model_sha256') != self.kokoro.identity['model'] or self.profile.get('voices_sha256') != self.kokoro.identity['voices']:
                raise ValueError('Installed Kokoro model/voice hashes differ from the configured narrator')
        return self.kokoro

    def prepare(self, text, script=None):
        self.server_info = {}  # Re-check a local server once per part, not once per film.
        turns = plan_speech(self.project, self.profile, text, script)
        runtimes = {}
        for turn in turns:
            config = turn['config']
            if config['provider'] == 'kokoro':
                runtimes['kokoro'] = self._kokoro().identity
            elif config['provider'] == 'chatterbox':
                url = config['options'].get('endpoint', PROVIDERS['chatterbox']['endpoint']).rsplit('/', 1)[0] + '/info'
                if url not in self.server_info:
                    try:
                        with build_opener(NoRedirect).open(Request(url), timeout=5) as response:
                            info = json.loads(response.read(1024 * 1024))
                    except Exception:
                        raise ValueError('Start the configured local Chatterbox server before generating its selected voices') from None
                    if not info.get('model_fingerprint') or info.get('model') != config['model']:
                        raise ValueError('The local Chatterbox server model differs from the selected model')
                    expected = config['options'].get('model_fingerprint')
                    if expected and expected != info['model_fingerprint']:
                        raise ValueError('Chatterbox checkpoint bytes differ from the configured fingerprint')
                    self.server_info[url] = info
                runtimes[url] = self.server_info[url]
        return {'turns': turns, 'input_fingerprint': input_fingerprint(turns), 'runtimes': runtimes}

    def _request_audio(self, recipe, config, request_id, parts, asset_id):
        from provider_budget import speech_scope, spent_or_reserved
        options, external = config['options'], remote(config)
        if external:
            currency = options.get('currency', 'USD')
        else:
            from workflow import policy
            value = policy(self.project)
            if value['mode'] == 'fast':
                currency = value['scope']['budget']['currency']
            else:
                authorizations = read_json(self.project / 'production/authorizations.json')
                currency = authorizations.get('audition_work' if self.purpose == 'audition' else 'final_production_budget', {}).get('currency', 'USD')
        budget, shared = speech_scope(self.project, config['provider'], currency, parts, self.purpose, external, recipe['url'])
        raw = self.project / 'production/cache/speech-responses' / (request_id + '.response')
        path = self.project / 'production/speech-jobs' / (request_id + '.json')
        with record_lock(self.project / 'production/provider-budget.lock'):
            prior = read_json(path, {})
            if prior:
                if prior.get('status') == 'received' and raw.is_file() and sha256_file(raw) == prior.get('response_sha256'):
                    return decode_audio(recipe, raw.read_bytes()), prior
                if prior.get('status') != 'known_failed':
                    raise ValueError('Speech request ' + request_id + ' has an unresolved or damaged result; reconcile it before another provider call')
            for other in (self.project / 'production/speech-jobs').glob('*.json'):
                pending = read_json(other)
                if pending.get('asset_id') == asset_id and pending.get('status') in ('requesting', 'needs_attention'):
                    raise ValueError('This speech turn has an unresolved provider outcome; reconcile it before a retake')
            problems = ready_problems(self.project, config, credentials=True)
            if problems:
                raise ValueError('; '.join(problems))
            price = options.get('price_per_1000_characters')
            if external and (not number(price) or price < 0):
                raise ValueError('Set the verified speech price_per_1000_characters before a cloud request')
            # Count the actual submitted directions/context too. Preserve an estimate,
            # rather than pretending this is a provider invoice.
            billed = sum(len(value.encode('utf-16-le')) // 2 for value in _text_fields(recipe['body']))
            estimate = billed / 1000 * (price or 0) if external else 0
            if external and (not number(budget.get('limit')) or spent_or_reserved(self.project, currency, shared, 'audition' if self.purpose == 'audition' else 'final') + estimate > budget['limit'] + 1e-9):
                raise ValueError('Speech request exceeds the remaining combined provider budget')
            record = {'request_id': request_id, 'provider': config['provider'], 'kind': 'speech',
                      'asset_id': asset_id,
                      'budget_kind': 'audition' if self.purpose == 'audition' else 'final',
                      'created_at': utc_now(), 'status': 'requesting', 'recipe': recipe,
                      'estimated_cost': estimate, 'actual_cost': None, 'currency': currency,
                      'cost_note': 'Conservative configured-rate reservation, not verified billed cost.'}
            if prior:
                record['history'] = [*prior.get('history', []), {key: value for key, value in prior.items() if key != 'history'}]
            atomic_json(path, record)
        try:
            payload, metadata = fetch_audio(recipe, timeout=options.get('timeout_seconds', 120))
            raw.parent.mkdir(parents=True, exist_ok=True)
            candidate = raw.with_suffix('.partial')
            candidate.write_bytes(payload)
            candidate.replace(raw)
            record.update(status='received', response_sha256=sha256_file(raw), response_file=raw.relative_to(self.project).as_posix(), **metadata)
            atomic_json(path, record)
        except Exception as error:
            record.update(status='needs_attention', error_type=type(error).__name__, failed_at=utc_now())
            atomic_json(path, record)
            raise
        return decode_audio(recipe, payload), record

    def render(self, text, output, prepared=None, script=None, part_id=None):
        import numpy as np
        import soundfile as sf
        output = Path(output).resolve()
        if not output.is_relative_to(self.project) or output.suffix.lower() != '.wav':
            raise ValueError('Speech output must be a WAV inside this story project')
        if self.purpose == 'audition' and not output.is_relative_to(self.project / 'audio/auditions'):
            raise ValueError('Auditions belong in audio/auditions and cannot overwrite production speech')
        if self.purpose == 'final':
            from workflow import selected_parts
            if not part_id:
                raise ValueError('Final speech requires its planned part ID')
            part = selected_parts(self.project, [part_id])[0]
            timeline = read_json(part / 'timeline.json')
            if (not timeline.get('narration_file') or output != (part / timeline['narration_file']).resolve()
                    or text.split() != (part / 'narration.txt').read_text(encoding='utf-8-sig').split()
                    or self.profile != read_json(self.project / 'audio/narrator.json')):
                raise ValueError('Final speech must use the configured cast, exact part text and declared output')
        prepared = prepared or self.prepare(text, script)
        turns = prepared['turns']
        if any(artifact_path(self.project, name) == output for turn in turns for name in turn['source_hashes']):
            raise ValueError('Speech output cannot overwrite a supplied voice recording or reference clip')
        from workflow import require_stage
        for provider in {turn['config']['provider'] for turn in turns}:
            require_stage(self.project, 'audition' if self.purpose == 'audition' else 'narration', [part_id] if part_id else None, tool=provider)
            if self.purpose == 'audition':
                from studio_common import require_authorized_work
                require_authorized_work(self.project, 'audition', provider)
        explicit = read_json(script, {}).get('utterances', []) if script else []
        if not explicit and not self.profile.get('cast') and self.profile.get('provider', 'kokoro') == 'kokoro':
            engine = self._kokoro()
            result = engine.render(text, output, self.profile['voice'], self.profile.get('speed', 1), self.profile.get('language', 'en-us'), self.profile.get('pause', 0.15))
            result.update(speech_input_fingerprint=prepared['input_fingerprint'], provider='kokoro')
            atomic_json(output.with_suffix('.chunks.json'), result)
            self.cache_hits, self.generated_chunks = engine.cache_hits, engine.generated_chunks
            return result
        output.parent.mkdir(parents=True, exist_ok=True)
        cursor, rate, chunks = 0, 48000, []
        with tempfile.TemporaryDirectory(prefix='.speech-', dir=output.parent) as temporary:
            target = Path(temporary) / 'speech.wav'
            with sf.SoundFile(target, 'w', samplerate=rate, channels=1, subtype='PCM_16') as writer:
                for index, turn in enumerate(turns):
                    config = turn['config']
                    recipe = None
                    if config['provider'] not in ('kokoro', 'provided'):
                        recipe = http_request(config, turn['text'], turn['direction'],
                                              turns[index - 1]['text'] if index else '',
                                              turns[index + 1]['text'] if index + 1 < len(turns) else '')
                        if config['provider'] == 'chatterbox' and config['options'].get('reference_audio'):
                            recipe['body']['reference_audio'] = str(artifact_path(self.project, config['options']['reference_audio']))
                    runtime_key = None
                    if config['provider'] == 'kokoro':
                        runtime_key = 'kokoro'
                    elif config['provider'] == 'chatterbox':
                        runtime_key = config['options'].get('endpoint', PROVIDERS['chatterbox']['endpoint']).rsplit('/', 1)[0] + '/info'
                    runtime = prepared['runtimes'].get(runtime_key)
                    config_key = fingerprint({'turn': _performance_turn(turn, clip=True), 'runtime': runtime, 'recipe': recipe,
                                              'assembler': sha256_file(Path(__file__)), 'revision': 1})
                    cached = self.cache / 'voices' / (config_key + '.wav')
                    receipt = cached.with_suffix('.json')
                    record = read_json(receipt, {})
                    intact = cached.is_file() and record.get('sha256') == sha256_file(cached)
                    if intact:
                        self.cache_hits += 1
                    else:
                        raw_source = Path(temporary) / ('source-' + str(index))
                        request_id = None
                        if config['provider'] == 'kokoro':
                            raw_source = self._kokoro().sentence(turn['text'], config['voice'], config['speed'], config['language'])
                        elif config['provider'] == 'provided':
                            raw_source = artifact_path(self.project, turn['audio_file'])
                        else:
                            request_id = fingerprint({'recipe': recipe, 'source_hashes': turn['source_hashes'], 'runtime': runtime, 'take': turn['take']})
                            payload, _ = self._request_audio(recipe, config, request_id, [part_id] if part_id else None,
                                                             (part_id or 'audition') + '/' + turn['id'] + '/' + turn['speaker'])
                            raw_source.write_bytes(payload)
                        cached.parent.mkdir(parents=True, exist_ok=True)
                        partial = cached.with_suffix('.partial.wav')
                        process([executable('ffmpeg'), '-v', 'error', '-y', '-i', str(raw_source), '-ar', str(rate), '-ac', '1', '-c:a', 'pcm_s16le', str(partial)])
                        with sf.SoundFile(partial) as source:
                            if source.frames <= 0:
                                raise ValueError('Speech provider returned empty audio')
                        partial.replace(cached)
                        record = {'sha256': sha256_file(cached), 'provider': config['provider'], 'model': config['model'],
                                  'voice': config['voice'], 'request_id': request_id, 'turn': turn,
                                  'runtimes': prepared['runtimes'], 'created_at': utc_now(), 'sample_rate': rate}
                        atomic_json(receipt, record)
                        self.generated_chunks += 1
                    start = cursor / rate
                    with sf.SoundFile(cached) as source:
                        if source.samplerate != rate or source.channels != 1:
                            raise ValueError('Speech clip format differs from its cache contract')
                        for block in source.blocks(blocksize=65536, dtype='float32'):
                            writer.write(block)
                            cursor += len(block)
                    chunks.append({'id': turn['id'], 'speaker': turn['speaker'], 'text': turn['text'],
                                   'provider': config['provider'], 'voice': config['voice'], 'request_id': record.get('request_id'),
                                   'language': config['language'],
                                   'file': os.path.relpath(cached, output.parent).replace('\\', '/'), 'sha256': sha256_file(cached),
                                   'start': start, 'end': cursor / rate})
                    frames = round(turn['pause_after'] * rate)
                    for offset in range(0, frames, 65536):
                        writer.write(np.zeros(min(65536, frames - offset), dtype=np.float32))
                    cursor += frames
                    from progress_records import advance
                    advance(index + 1, len(turns), 'clips', 'Assembling voice clips')
            target.replace(output)
        manifest = {'schema_version': 2, 'audio_sha256': sha256_file(output), 'duration': cursor / rate,
                    'sample_rate': rate, 'speech_input_fingerprint': prepared['input_fingerprint'],
                    'text_sha256': fingerprint(text), 'runtimes': prepared['runtimes'], 'chunks': chunks,
                    'alignment_status': 'word_alignment_pending'}
        atomic_json(output.with_suffix('.chunks.json'), manifest)
        return manifest


def _text_fields(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in ('text', 'transcript', 'previous_text', 'next_text', 'future_text', 'direction') and isinstance(child, str):
                yield child
            elif isinstance(child, (dict, list)):
                yield from _text_fields(child)
    elif isinstance(value, list):
        for child in value:
            yield from _text_fields(child)
