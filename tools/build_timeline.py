#!/usr/bin/env python3
"""Derive shot boundaries from approved speech and actual word alignment; never guess mismatches."""
import argparse
from pathlib import Path
import re
import math

from studio_common import atomic_json, read_json, sha256_file
from validate_timeline import validate


def tokens(text):
    return re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?|[0-9]+", text.lower().replace('\u2019', "'"))


def anchor_time(anchor, turns, shots, onset, speech_duration, default_edge='start'):
    edge, offset = anchor.get('edge', default_edge), anchor.get('offset', 0)
    if edge not in ('start', 'end') or isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(offset):
        raise ValueError('Timing anchors need start/end and a finite numeric offset')
    if 'utterance_id' in anchor:
        source = turns.get(anchor['utterance_id'])
        if source is None:
            raise ValueError('Unknown measured utterance anchor: ' + str(anchor['utterance_id']))
        return round(source[edge] + onset + offset, 6)
    if 'shot_id' in anchor:
        if anchor['shot_id'] not in shots:
            raise ValueError('Unknown shot anchor: ' + str(anchor['shot_id']))
        return round(shots[anchor['shot_id']][edge] + offset, 6)
    if anchor.get('narration') is True:
        return round(onset + (speech_duration if edge == 'end' else 0) + offset, 6)
    raise ValueError('Use a measured utterance_id, shot_id or narration timing anchor')


def build(project, part_id):
    project = Path(project).resolve()
    part = (project / 'parts' / part_id).resolve()
    if part.parent != project / 'parts':
        raise ValueError('Invalid part path')
    approved = read_json(part / 'shots.json')
    timeline_path = part / 'timeline.json'
    previous = read_json(timeline_path)
    audio = part / previous.get('narration_file', 'audio/narration.wav')
    alignment_path = audio.with_suffix('.alignment.json')
    from align_audio import reviewed_alignment
    alignment = reviewed_alignment(audio)
    if alignment['source_sha256'] != sha256_file(audio):
        raise ValueError('Alignment source does not match actual narration')
    chunks = read_json(audio.with_suffix('.chunks.json'))
    if chunks.get('audio_sha256') and chunks['audio_sha256'] != sha256_file(audio):
        raise ValueError('Measured speech manifest belongs to different audio')
    tail = approved.get('audio_tail_seconds', 0.3)
    onset = previous.get('narration_start', 0.0)
    duration = round(chunks['duration'] + onset + tail, 6)
    intake = read_json(project / 'creative/intake.json')
    frame = intake.get('frame_format')
    if isinstance(frame, dict):
        previous.update({key: frame[key] for key in ('width', 'height', 'fps') if key in frame})
    elif frame in ('landscape', 'portrait', 'square'):
        previous['width'], previous['height'] = {'landscape': (1920, 1080), 'portrait': (1080, 1920), 'square': (1080, 1080)}[frame]
    policy = read_json(part / 'part.json', {}).get('duration_policy') or intake.get('duration_policy') or {}
    if isinstance(policy, dict) and not policy.get('flexible', True):
        minimum, maximum = policy.get('min_seconds', 0), policy.get('max_seconds', float('inf'))
        if not minimum <= duration <= maximum:
            raise ValueError(f'Actual {duration:.3f}s conflicts with the approved duration policy; revise scope/duration and renew G2')
    aligned = alignment['words']
    flat = [tokens(word['text']) for word in aligned]
    flat = [token for group in flat for token in group]
    if len(flat) != len(aligned):
        raise ValueError('Compound/display tokens need explicit manual shot boundaries; no approximate timing will be invented')
    old_images = {shot['id']: shot['image'] for shot in previous.get('shots', [])}
    by_turn = {turn['id']: turn for turn in chunks.get('chunks', []) if turn.get('id')}
    turn_timing = approved.get('timing_mode') == 'speech_turns'
    if turn_timing and not chunks.get('audio_sha256'):
        raise ValueError('Speech-turn timing requires an audio-bound measured manifest')
    if turn_timing and (not by_turn or len(by_turn) != len(chunks.get('chunks', [])) or
                        tokens(' '.join(shot.get('narration', '') for shot in approved['shots'])) != flat):
        raise ValueError('Speech-turn timing needs unique measured turn IDs and complete written speech coverage')
    result, cursor = [], 0
    for index, shot in enumerate(approved['shots']):
        expected = tokens(shot.get('narration', ''))
        if not expected and not turn_timing:
            raise ValueError('Speech-free/action holds require explicit written timing; use a manually verified timeline for those shots')
        if not turn_timing and flat[cursor:cursor + len(expected)] != expected:
            raise ValueError(f'{shot["id"]}: approved speech differs from the aligned transcript; resolve the source instead of guessing')
        # Preserve the G4 camera plan verbatim; normalized move timing follows the measured hold.
        item = {key: value for key, value in shot.items() if key not in ('visual_description', 'sound_requirements')}
        item['image'] = old_images.get(shot['id'], shot.get('image', f'images/shot_{index + 1:03d}.png'))
        if turn_timing:
            anchor = shot.get('start_anchor')
            if index and not anchor:
                raise ValueError(shot['id'] + ': provide a measured start_anchor; no shot timing is guessed')
            item['start'] = anchor_time(anchor, by_turn, {}, onset, chunks['duration']) if anchor else 0.0
        else:
            item['start'] = 0.0 if index == 0 else round(aligned[cursor]['start'] + onset, 6)
        if result:
            result[-1]['end'] = item['start']
        cursor += len(expected)
        result.append(item)
    if not result or cursor != len(aligned):
        raise ValueError('Written shots must cover the complete aligned narration, without omitted words')
    result[-1]['end'] = duration
    if approved.get('audio_cues'):
        previous['audio_cues'] = approved['audio_cues']
    by_id = {shot['id']: shot for shot in result}
    for cue in previous.get('audio_cues', []):
        for edge in ('start', 'end'):
            anchor = cue.get(edge + '_anchor')
            if anchor:
                cue[edge] = anchor_time(anchor, by_turn, by_id, onset, chunks['duration'], edge)
    previous.update(duration=duration, part_id=part_id, shots=result,
                    alignment={key: value for key, value in alignment.items() if key not in ('words', 'subtitles')},
                    subtitles=[dict(cue, start=cue['start'] + onset, end=cue['end'] + onset) for cue in alignment['subtitles']],
                    timing_source={'shots_sha256': sha256_file(part / 'shots.json'),
                                   'alignment_sha256': sha256_file(alignment_path),
                                   'chunks_sha256': sha256_file(audio.with_suffix('.chunks.json')),
                                   'method': 'measured speech-turn anchors' if turn_timing else 'acoustic word boundaries'})
    # Preserve explicitly authored audio cues; validate rather than stretching them silently.
    atomic_json(timeline_path.with_suffix('.candidate.json'), previous)
    errors = validate(timeline_path.with_suffix('.candidate.json'))
    if errors:
        raise ValueError('Derived timeline needs review: ' + '; '.join(errors))
    timeline_path.with_suffix('.candidate.json').replace(timeline_path)
    return previous


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--part', required=True)
    args = parser.parse_args()
    try:
        timeline = build(args.project, args.part)
        print(f'{args.part}: {timeline["duration"]:.3f}s; {len(timeline["shots"])} verified speech-driven intervals')
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
