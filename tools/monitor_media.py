"""Actual preview, voice revisions and measured timeline data for the local monitor."""
from pathlib import Path
from urllib.parse import urlencode

from speech_providers import voice_config
from studio_common import fingerprint
from workflow import presentation


def url(project_id, part, kind, **fields):
    return '/api/media?' + urlencode({'project': project_id, 'part': part, 'kind': kind, **fields})


def inside(project, value):
    if not isinstance(value, str) or not value:
        return None
    path = (project / value).resolve()
    return path if path.is_relative_to(project) else None


def character_name(project, speaker, record):
    if record.get('name'):
        return str(record['name'])[:100]
    source = inside(project, record.get('canonical_file'))
    if source:
        try:
            with source.open(encoding='utf-8-sig') as file:
                heading = file.readline(500).lstrip('# ').strip()
            if heading.startswith(speaker):
                return heading.removeprefix(speaker).lstrip(' —–:|-')[:100] or speaker
        except OSError:
            pass
    return speaker


def part_view(reader, info, part, timeline, chunks):
    project = Path(info['path'])
    read, digest = reader.json, reader.digest
    profile = read(project / 'audio/narrator.json')
    characters = read(project / 'continuity/entities.json').get('characters', {})
    script = read(part / 'speech.json').get('utterances', [])
    written = {shot.get('id'): shot for shot in read(part / 'shots.json').get('shots', [])}
    source = timeline.get('narration_file')
    narration = inside(project, str(part.relative_to(project) / source)) if source else None
    manifest = read(narration.with_suffix('.chunks.json')) if narration else {}
    roles, missing_voice = {}, False
    speakers = list(dict.fromkeys([turn.get('speaker', 'NARRATOR') for turn in script] or [chunk.get('speaker', 'NARRATOR') for chunk in chunks]))
    for speaker in speakers:
        try:
            config = voice_config(profile, speaker)
        except (ValueError, TypeError, KeyError):
            config = {'provider': 'unconfigured', 'voice': None, 'model': None}
        actual = [chunk for chunk in chunks if chunk.get('speaker', 'NARRATOR') == speaker]
        expected = [turn for turn in script if turn.get('speaker', 'NARRATOR') == speaker]
        matches = bool(actual) and (not expected or len(actual) == len(expected)) and all(
            chunk.get('voice', manifest.get('voice')) == config['voice'] and chunk.get('provider', manifest.get('provider', profile.get('provider', 'kokoro'))) == config['provider'] for chunk in actual)
        roles[speaker] = {'speaker': speaker, 'name': 'Narrator' if speaker == 'NARRATOR' else character_name(project, speaker, characters.get(speaker, {})),
                          'provider': config['provider'], 'voice': config['voice'], 'model': config['model'],
                          'rendered_voices': sorted({str(chunk.get('voice', manifest.get('voice')) or 'unrecorded') for chunk in actual}),
                          'clips': len(actual), 'expected_clips': len(expected) or None, 'current': matches}
        missing_voice |= not matches
    audio_invalid = bool(narration and (not digest(narration) or manifest.get('audio_sha256') != digest(narration)))
    audio_invalid |= bool(script and ' '.join(turn.get('text', '') for turn in script).split() != ' '.join(chunk.get('text', '') for chunk in chunks).split())
    if manifest.get('speech_input_fingerprint'):
        # Reuse the core read-only performance check, including model/options/directions.
        from speech import current_problems
        audio_invalid |= bool(current_problems(project, [part], require_runtime=False))
    if audio_invalid:
        missing_voice = True
        for role in roles.values():
            role['current'] = False
    video, log_path = part / 'preview.mp4', part / 'preview.render-log.json'
    log = read(log_path)
    current, reasons, files = video.is_file(), [], {}
    if video.is_file():
        video_hash = digest(video)
        files[video.relative_to(project).as_posix()] = video_hash
        if not video_hash or log.get('output_sha256') != video_hash:
            reasons.append('Preview output is still being written or differs from its render record')
        if log.get('presentation_fingerprint') != fingerprint(presentation(timeline)):
            reasons.append('The preview needs the current picture, timing or captions')
        mix = inside(project, str(part.relative_to(project) / timeline.get('audio_file', '')))
        if not mix or log.get('audio_sha256') != digest(mix):
            reasons.append('The preview needs the current sound mix')
        elif mix.is_file():
            files[mix.relative_to(project).as_posix()] = digest(mix)
            mix_log = read(mix.with_suffix('.mix-log.json'))
            if (narration or timeline.get('audio_cues')) and not mix_log.get('source_input_hashes'):
                reasons.append('The current sound sources need a mix record')
            for name, recorded in mix_log.get('source_input_hashes', {}).items():
                path = Path(name).resolve()
                if not path.is_relative_to(project) or digest(path) != recorded:
                    reasons.append('The sound mix needs the latest voice or sound sources')
                    break
    else:
        reasons.append('A preview has not been rendered yet')
        video_hash = None
    shots = []
    for shot in timeline.get('shots', []):
        image = inside(project, str(part.relative_to(project) / shot.get('image', '')))
        image_hash = digest(image) if image else None
        if image_hash:
            files[image.relative_to(project).as_posix()] = image_hash
        if video.is_file() and (not image_hash or log.get('source_image_hashes', {}).get(str(image)) != image_hash):
            reasons.append('The preview needs the latest shot images')
        shots.append({'id': shot.get('id'), 'start': shot.get('start'), 'end': shot.get('end'),
                      'description': str(written.get(shot.get('id'), {}).get('visual_description') or shot.get('camera_direction', ''))[:1500],
                      'narration': str(shot.get('narration', ''))[:1500],
                      'image_url': url(info['id'], part.name, 'shot', shot=shot.get('id'), v=(image_hash or '')[:12]) if image_hash else None})
    subtitles = part / 'subtitles.srt'
    intake = read(project / 'creative/intake.json')
    if intake.get('subtitles') is not False and subtitles.is_file():
        files[subtitles.relative_to(project).as_posix()] = digest(subtitles)
    elif intake.get('subtitles') is not False and video.is_file():
        reasons.append('The requested subtitle file is missing')
    if video.is_file() and log.get('subtitles_sha256') and log['subtitles_sha256'] != digest(subtitles):
        reasons.append('The preview needs the current burned captions')
    if missing_voice:
        reasons.append('The selected voice has not been fully applied to the current speech')
    reasons = list(dict.fromkeys(reasons))
    current = bool(current and not reasons)
    decision = read(project / 'production/preview-decisions.json').get('decisions', {}).get(part.name, {})
    inputs = {'presentation': fingerprint(presentation(timeline)), 'files': files}
    approved = current and decision.get('status') == 'accepted' and bool(decision.get('decision_quote')) and bool(decision.get('decision_reference')) and decision.get('inputs') == inputs
    master = part / 'final.mp4'
    master_log = read(part / 'final.render-log.json')
    master_current = bool(current and master.is_file() and
                          master_log.get('output_sha256') == digest(master) and
                          master_log.get('presentation_fingerprint') == log.get('presentation_fingerprint') and
                          master_log.get('audio_sha256') == log.get('audio_sha256') and
                          master_log.get('source_image_hashes') == log.get('source_image_hashes') and
                          master_log.get('subtitles_sha256') == log.get('subtitles_sha256'))
    changes = []
    for change in read(project / 'audio/voice-decisions.json').get('changes', [])[-12:]:
        speaker = change.get('speaker', 'NARRATOR')
        selected = change.get('selected', {})
        active = roles.get(speaker, {}).get('voice') == selected.get('voice') and roles.get(speaker, {}).get('provider') == selected.get('provider')
        changes.append({'id': change.get('id'), 'at': change.get('at'), 'speaker': speaker,
                        'from_voice': change.get('previous', {}).get('voice'), 'to_voice': selected.get('voice'),
                        'reason': str(change.get('reason', ''))[:500],
                        'request': str(change.get('decision_quote') or '')[:500],
                        'state': 'superseded' if not active else 'speech_pending' if missing_voice else 'review_ready' if current else 'preview_pending'})
    onset = timeline.get('narration_start', 0)
    speech = [{'id': chunk.get('id', str(i)), 'speaker': chunk.get('speaker', 'NARRATOR'),
               'voice': chunk.get('voice', manifest.get('voice')), 'start': chunk.get('start', 0) + onset,
               'end': chunk.get('end', 0) + onset, 'text': str(chunk.get('text', ''))[:1500]}
              for i, chunk in enumerate(chunks)]
    return {'part': part.name, 'duration': timeline.get('duration'), 'shots': shots, 'speech': speech,
            'captions': [{'start': cue.get('start'), 'end': cue.get('end'), 'text': str(cue.get('text', ''))[:1500]} for cue in timeline.get('subtitles', [])],
            'sounds': [{'id': cue.get('id'), 'start': cue.get('start'), 'end': cue.get('end'), 'role': cue.get('role', 'sound')} for cue in timeline.get('audio_cues', [])],
            'voices': list(roles.values()), 'voice_changes': changes, 'requires_speech': bool(narration or script),
            'preview': {'exists': video.is_file(), 'current': current, 'approved': bool(approved),
                        'version': (video_hash or '')[:12], 'reasons': reasons,
                        'url': url(info['id'], part.name, 'preview', v=(video_hash or '')[:12]) if video.is_file() else None,
                        'review_state': 'approved' if approved else 'decision_needed' if current else 'updating',
                        'at': log_path.stat().st_mtime if log_path.is_file() else None},
            'master_exists': master.is_file(), 'master_current': master_current}
