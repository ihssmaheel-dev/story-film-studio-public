#!/usr/bin/env python3
"""Validate a part timeline's structure/assets, not story logic or semantic sync."""
import argparse
import json
import math
import re
import sys
from pathlib import Path

from camera_motion import normalize_motion, source_motion_issues


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def load_audio_assets(timeline, data):
    reference = data.get('audio_manifest')
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError('audio_cues require an audio_manifest path')
    manifest_path = (Path(timeline).parent / reference).resolve()
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or not isinstance(manifest.get('assets'), dict):
        raise ValueError('audio manifest must contain an assets object keyed by asset ID')
    return manifest_path, manifest['assets']


def validate(path, check_assets=False):
    path = Path(path).resolve()
    errors = []
    try:
        data = read_json(path)
    except (OSError, ValueError) as error:
        return [f'Cannot read timeline: {error}']
    if not isinstance(data, dict):
        return ['Timeline must be a JSON object']
    if data.get('schema_version') != 2:
        errors.append('schema_version must be 2; use the current part timeline template')
    if not isinstance(data.get('part_id'), str) or not re.fullmatch(r'part_\d{3,}', data['part_id']):
        errors.append('part_id must use part_### naming')
    duration = data.get('duration')
    if not finite_number(duration) or duration <= 0:
        errors.append('duration must be finite and positive')
        duration = 0
    for field in ('width', 'height'):
        value = data.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0 or value % 2:
            errors.append(f'{field} must be a positive even integer')
    fps = data.get('fps')
    if not finite_number(fps) or fps <= 0:
        errors.append('fps must be finite and positive')
        fps = 30
    if data.get('scale_filter', 'lanczos') not in ('lanczos', 'neighbor', 'bicubic'):
        errors.append('scale_filter must be lanczos, neighbor or bicubic')
    tolerance = 0.5 / fps + 0.000001

    def records(field, nonempty=False):
        values = data.get(field, [])
        if not isinstance(values, list) or (nonempty and not values):
            errors.append(f'{field} must be a {"nonempty " if nonempty else ""}array')
            return []
        return values

    def interval(record, label):
        start, end = record.get('start'), record.get('end')
        if not all(finite_number(value) for value in (start, end)):
            errors.append(f'{label}: start/end must be finite numbers')
            return None
        if start < 0 or end <= start or end > duration + tolerance:
            errors.append(f'{label}: interval must be positive and within the presentation')
        return start, end

    def path_field(record, field, label, required=True):
        value = record.get(field)
        if value is None and not required:
            return None
        if not isinstance(value, str) or not value.strip():
            errors.append(f'{label}: missing/invalid {field} path')
            return None
        result = path.parent / value
        if check_assets and not result.is_file():
            errors.append(f'{label}: missing file {value}')
        return result

    shots = records('shots', nonempty=True)
    previous, ids = 0.0, set()
    for index, shot in enumerate(shots):
        if not isinstance(shot, dict):
            errors.append(f'shots[{index}] must be an object')
            continue
        identity = shot.get('id')
        if not isinstance(identity, str) or not identity:
            errors.append(f'shots[{index}] requires an ID')
        elif identity in ids:
            errors.append(f'duplicate shot ID {identity}')
        else:
            ids.add(identity)
        times = interval(shot, f'shots[{index}]')
        if times:
            start, end = times
            if abs(start - previous) > tolerance:
                errors.append(f'{identity}: gap/overlap from {previous:.3f} to {start:.3f}')
            previous = end
        image_path = path_field(shot, 'image', f'shots[{index}]')
        try:
            motion = normalize_motion(shot.get('motion'))
            if motion['type'] != 'static' and data.get('scale_filter') == 'neighbor':
                errors.append(f'{identity}: zoompan resamples pixels; use a static hold for a locked nearest-neighbor pixel grid')
            if motion['type'] != 'static' and times and round(times[1] * fps) - round(times[0] * fps) < 2:
                errors.append(f'{identity}: moving shot must span at least two output frames')
            if check_assets and image_path and image_path.is_file() and motion['type'] != 'static':
                from PIL import Image, ImageOps
                with Image.open(image_path) as image:
                    size = ImageOps.exif_transpose(image).size
                width, height = data.get('width'), data.get('height')
                if all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in (width, height)):
                    issues, _ = source_motion_issues(size, width, height, motion)
                    errors.extend(f'{identity}: {issue}' for issue in issues)
        except (ValueError, OSError) as error:
            errors.append(f'{identity}: {error}')
        for field in ('style_id', 'style_revision'):
            if not isinstance(shot.get(field), str) or not shot[field].strip():
                errors.append(f'{identity}: {field} required')
    if shots and abs(previous - duration) > tolerance:
        errors.append(f'last shot ends at {previous:.3f}, expected {duration:.3f}')

    previous = 0.0
    for index, cue in enumerate(records('subtitles')):
        if not isinstance(cue, dict):
            errors.append(f'subtitles[{index}] must be an object')
            continue
        times = interval(cue, f'subtitles[{index}]')
        if times:
            start, end = times
            if start < previous - 0.001:
                errors.append(f'subtitles[{index}]: unordered or overlapping cue')
            previous = end
        if not isinstance(cue.get('text'), str) or not cue['text'].strip():
            errors.append(f'subtitles[{index}]: text required')

    narration = path_field(data, 'narration_file', 'narration', required=False)
    narration_start = data.get('narration_start', 0.0)
    if not finite_number(narration_start) or narration_start < 0 or narration_start >= duration:
        errors.append('narration_start must be within the presentation')
    narration_gain = data.get('narration_gain_db', 0.0)
    if not finite_number(narration_gain) or not -120 <= narration_gain <= 24:
        errors.append('narration_gain_db must be finite and between -120 and 24')
    path_field(data, 'audio_file', 'final mix')

    cues = records('audio_cues')
    assets, manifest_path = {}, None
    if cues:
        reference = data.get('audio_manifest')
        if not isinstance(reference, str) or not reference.strip():
            errors.append('audio_cues require an audio_manifest path')
        elif check_assets:
            try:
                manifest_path, assets = load_audio_assets(path, data)
            except (OSError, ValueError) as error:
                errors.append(f'Cannot read audio manifest: {error}')
    ids = set()
    for index, cue in enumerate(cues):
        label = f'audio_cues[{index}]'
        if not isinstance(cue, dict):
            errors.append(f'{label} must be an object')
            continue
        identity = cue.get('id')
        if not isinstance(identity, str) or not identity or identity in ids:
            errors.append(f'{label}: unique nonempty ID required')
        else:
            ids.add(identity)
        times = interval(cue, label)
        if cue.get('role') not in ('ambience', 'sfx', 'music'):
            errors.append(f'{label}: role must be ambience, sfx or music')
        for field in ('source_offset', 'fade_in', 'fade_out'):
            value = cue.get(field, 0.0)
            if not finite_number(value) or value < 0:
                errors.append(f'{label}: {field} must be finite and nonnegative')
        if times and all(finite_number(cue.get(field, 0.0)) for field in ('fade_in', 'fade_out')):
            if cue.get('fade_in', 0.0) + cue.get('fade_out', 0.0) > times[1] - times[0] + 0.000001:
                errors.append(f'{label}: fades exceed cue duration')
        gain = cue.get('gain_db', 0.0)
        if not finite_number(gain) or not -120 <= gain <= 24:
            errors.append(f'{label}: gain_db must be finite and between -120 and 24')
        for field in ('loop', 'duck_under_narration'):
            if not isinstance(cue.get(field, False), bool):
                errors.append(f'{label}: {field} must be boolean')
        if cue.get('duck_under_narration') and narration is None:
            errors.append(f'{label}: narration ducking requested without narration_file')
        asset_id = cue.get('asset_id')
        if not isinstance(asset_id, str) or not asset_id:
            errors.append(f'{label}: asset_id required')
        elif check_assets and manifest_path:
            asset = assets.get(asset_id)
            if not isinstance(asset, dict) or not isinstance(asset.get('file'), str) or not asset['file'].strip():
                errors.append(f'{label}: asset {asset_id} missing/invalid in registry')
            elif not (manifest_path.parent / asset['file']).is_file():
                errors.append(f'{label}: asset {asset_id} file missing')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('timeline', type=Path)
    parser.add_argument('--check-assets', action='store_true')
    args = parser.parse_args()
    errors = validate(args.timeline, args.check_assets)
    for error in errors:
        print('ERROR:', error, file=sys.stderr)
    if errors:
        sys.exit(1)
    print('Part timeline structure passed; story, approvals, listening and semantic alignment require review.')


if __name__ == '__main__':
    main()
