#!/usr/bin/env python3
"""Technical image/audio/video checks and reference comparison sheets; no artistic auto-approval."""
import argparse
import json
import math
from pathlib import Path
import re
import tempfile

from studio_common import atomic_json, executable, find_project, fingerprint, process, read_json, sha256_file, utc_now
from validate_timeline import validate
from camera_motion import normalize_motion, source_motion_issues


def audio_metrics(path):
    from media_cache import measured
    return measured('audio', path, lambda: _audio_metrics(path))


def _audio_metrics(path):
    ffmpeg = executable('ffmpeg')
    if not ffmpeg:
        raise ValueError('FFmpeg is required for audio measurements')
    result = process([ffmpeg, '-hide_banner', '-i', str(path), '-af',
                      'silencedetect=noise=-50dB:d=0.25,loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json',
                      '-f', 'null', '-'])
    blocks = re.findall(r'\{[^{}]*"input_i"[^{}]*\}', result.stderr, re.S)
    if not blocks:
        raise ValueError('No audio measurement returned')
    measurement = json.loads(blocks[-1])
    values = {}
    for source, target in [('input_i', 'integrated_lufs'), ('input_tp', 'true_peak_db'), ('input_lra', 'loudness_range')]:
        value = float(measurement[source])
        values[target] = value if math.isfinite(value) else None
    starts = [float(value) for value in re.findall(r'silence_start: ([\d.]+)', result.stderr)]
    ends = [float(value) for value in re.findall(r'silence_end: ([\d.]+)', result.stderr)]
    values['silence_ranges'] = [{'start': start, 'end': ends[index] if index < len(ends) else None}
                                for index, start in enumerate(starts)]
    return values


def comparison_sheet(timeline, output):
    from PIL import Image, ImageDraw, ImageOps
    timeline, output = Path(timeline).resolve(), Path(output).resolve()
    data, project = read_json(timeline), find_project(timeline)
    tiles = []
    if project:
        registry = read_json(project / 'continuity/entities.json')
        seen = set()
        for group in ('styles', 'characters', 'locations', 'props'):
            for identity, entity in registry.get(group, {}).items():
                for reference in entity.get('reference_paths', []):
                    path = (project / reference).resolve()
                    if path not in seen:
                        tiles.append((identity + ' CANONICAL REFERENCE', path))
                        seen.add(path)
    tiles.extend((data['part_id'] + '/' + shot['id'], timeline.parent / shot['image']) for shot in data['shots'])
    from PIL import __version__ as pillow_version
    from studio_common import ROOT
    key = fingerprint({'tiles': [(label, str(path.resolve()), sha256_file(path) if path.is_file() else None)
                                  for label, path in tiles], 'pillow': pillow_version,
                       'code': sha256_file(__file__), 'output': str(output)})
    receipt = ROOT / '.runtime/cache/review-sheets' / (fingerprint(str(output)) + '.json')
    try:
        old = read_json(receipt, {})
        if old.get('key') == key and old.get('pages') and all(
                Path(path).is_file() and sha256_file(path) == digest for path, digest in old['pages'].items()):
            return list(old['pages'])
    except (OSError, ValueError, TypeError):
        pass
    width, height, columns = 360, 230, 3
    pages = []
    # Page the sheet so a long film does not allocate a giant diagnostic image.
    for page_index in range(0, len(tiles), 24):
        subset = tiles[page_index:page_index + 24]
        canvas = Image.new('RGB', (columns * width, max(1, math.ceil(len(subset) / columns)) * height), '#202127')
        draw = ImageDraw.Draw(canvas)
        for index, (label, path) in enumerate(subset):
            x, y = index % columns * width, index // columns * height
            draw.text((x + 8, y + 5), label, fill='white')
            if path.is_file():
                try:
                    with Image.open(path) as image:
                        thumbnail = ImageOps.contain(ImageOps.exif_transpose(image).convert('RGB'), (width - 16, height - 45))
                        canvas.paste(thumbnail, (x + (width - thumbnail.width) // 2, y + 30))
                except (OSError, ValueError):
                    draw.text((x + 8, y + 50), 'INVALID IMAGE - REVIEW REQUIRED', fill='#ff7777')
            else:
                draw.text((x + 8, y + 50), 'MISSING IMAGE', fill='#ff7777')
        page = output if page_index == 0 else output.with_name(output.stem + f'-{page_index // 24 + 1}' + output.suffix)
        page.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(page)
        pages.append(str(page))
    atomic_json(receipt, {'key': key, 'pages': {path: sha256_file(path) for path in pages}})
    return pages


def check_part(timeline, video=None):
    from PIL import Image
    timeline = Path(timeline).resolve()
    data = read_json(timeline)
    errors, warnings, images = validate(timeline, check_assets=True), [], []
    for shot in data.get('shots', []):
        path = timeline.parent / shot['image']
        if not path.is_file():
            continue
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                from PIL import ImageOps
                size = ImageOps.exif_transpose(image).size
            image_ratio = size[0] / size[1]
            target = data['width'] / data['height']
            if abs(image_ratio - target) > 0.02:
                warnings.append(f'{shot["id"]}: source aspect differs from delivery; inspect padding/crop')
            if size[0] < data['width'] or size[1] < data['height']:
                warnings.append(f'{shot["id"]}: source is smaller than the master frame')
            motion = normalize_motion(shot.get('motion'))
            motion_errors, motion_warnings = source_motion_issues(size, data['width'], data['height'], motion)
            errors.extend(f'{shot["id"]}: {issue}' for issue in motion_errors)
            warnings.extend(f'{shot["id"]}: {issue}' for issue in motion_warnings)
            if motion['type'] != 'static' and (shot['end'] - shot['start']) * (motion['end_at'] - motion['start_at']) < 1:
                warnings.append(f'{shot["id"]}: camera move lasts under one second; inspect speed/comfort')
            images.append({'id': shot['id'], 'file': shot['image'], 'size': size,
                           'motion': motion, 'sha256': sha256_file(path)})
        except (OSError, ValueError) as error:
            errors.append(f'{shot["id"]}: corrupt/unsupported image: {error}')
    if any(item['motion']['type'] != 'static' for item in images):
        warnings.append('Camera movement requires playback inspection of framing, smoothness, sharpness, reveal timing and subtitle safety')
    audio = timeline.parent / data['audio_file']
    measurements = audio_metrics(audio) if audio.is_file() else None
    if audio.is_file() and data.get('audio_cues') and not errors:
        from audio_check import mix_coverage_errors
        errors.extend(mix_coverage_errors(timeline, audio, warnings=warnings))
    if measurements and measurements['true_peak_db'] is not None and measurements['true_peak_db'] > -0.5:
        warnings.append('Final WAV true peak has less than 0.5 dB headroom')
    if measurements and measurements['integrated_lufs'] is None:
        warnings.append('Final audio is silent; verify this is intentional')
    unresolved = [item for item in data.get('alignment', {}).get('uncertain_ranges', []) if not item.get('reviewed')]
    if unresolved:
        warnings.append(f'{len(unresolved)} uncertain alignment ranges remain unreviewed')
    stream_info, black_ranges = None, []
    if video:
        video = Path(video).resolve()
        ffprobe, ffmpeg = executable('ffprobe'), executable('ffmpeg')
        from media_cache import measured as cached_measurement
        def scan_video():
            streams = json.loads(process([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(video)]).stdout)
            dark = process([ffmpeg, '-hide_banner', '-i', str(video), '-an', '-vf', 'blackdetect=d=0.1:pix_th=0.02', '-f', 'null', '-'])
            return {'streams': streams, 'black_ranges': [{'start': float(start), 'end': float(end)} for start, end in
                    re.findall(r'black_start:([\d.]+) black_end:([\d.]+)', dark.stderr)]}
        scan = cached_measurement('video', video, scan_video, tools=('ffmpeg', 'ffprobe'))
        stream_info, black_ranges = scan['streams'], scan['black_ranges']
        stream_info['format']['filename'] = str(video)
        duration = float(stream_info['format']['duration'])
        if abs(duration - data['duration']) > max(0.1, 2 / data['fps']):
            errors.append('Encoded duration does not match the presentation')
        if black_ranges:
            warnings.append('Detected dark/black ranges; compare them with planned darkness before accepting')
        video_streams = [stream for stream in stream_info['streams'] if stream['codec_type'] == 'video']
        if not video_streams or not any(stream['codec_type'] == 'audio' for stream in stream_info['streams']):
            errors.append('Encoded delivery must contain video and audio streams')
        for stream in video_streams:
            if abs(float(stream.get('start_time', 0))) > 1 / data['fps'] or abs(float(stream.get('duration', 0)) - data['duration']) > 2 / data['fps']:
                errors.append('Video stream starts late or does not cover the complete presentation')
        if measurements is not None:
            measurements['encoded_audio'] = audio_metrics(video)
    return {'checked_at': utc_now(), 'timeline_sha256': sha256_file(timeline), 'technical_errors': errors,
            'warnings': warnings, 'images': images, 'audio': measurements, 'video': stream_info,
            'black_ranges': black_ranges, 'manual_visual_and_listening_status': 'pending',
            'release_ready': False}


def image_review_context(project, part, shot):
    project = Path(project).resolve()
    from project_records import artifact_path
    registry = read_json(project / 'continuity/entities.json')
    inputs = {'shot': shot}
    motion = normalize_motion(shot.get('motion'))
    if motion['type'] != 'static':
        inputs['camera_motion'] = motion
        inputs['camera_motion_compiler_sha256'] = sha256_file(Path(__file__).with_name('camera_motion.py'))
    visible = [shot.get('style_id'), shot.get('location_id')] + shot.get('character_ids', []) + shot.get('prop_ids', [])
    known = set()
    for group in ('styles', 'characters', 'locations', 'props'):
        for identity, entity in registry.get(group, {}).items():
            if identity in visible:
                inputs[identity] = entity
                for name in [entity['canonical_file'], *entity.get('reference_paths', [])]:
                    path = artifact_path(project, name)
                    inputs[name] = sha256_file(path)
                    known.add(str(path))
    from image_references import collect
    refs, _ = collect(project, {'kind': 'final', 'part_id': part, 'shot_id': shot['id']})
    additional = {item['artifact_path']: item['sha256'] for item in refs.bindings if item['path'] not in known}
    if additional:
        inputs['additional_style_references'] = additional
    return fingerprint(inputs)


def record_image_review(project, part, shot, verdict, notes, reviewer):
    project = Path(project).resolve()
    timeline = read_json(project / 'parts' / part / 'timeline.json')
    record = next(item for item in timeline['shots'] if item['id'] == shot)
    image = project / 'parts' / part / record['image']
    if verdict not in ('passed', 'failed') or not notes.strip() or not reviewer.strip():
        raise ValueError('An actual verdict, reviewer and inspection notes are required')
    path = project / 'production/image-reviews.json'
    reviews = read_json(path, {'reviews': {}})
    written = next(item for item in read_json(project / 'parts' / part / 'shots.json')['shots'] if item['id'] == shot)
    reviews['reviews'][part + '/' + shot] = {'sha256': sha256_file(image), 'verdict': verdict,
                                            'context': image_review_context(project, part, written),
                                            'notes': notes, 'reviewer': reviewer, 'at': utc_now()}
    atomic_json(path, reviews)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('timeline', type=Path)
    parser.add_argument('--video', type=Path)
    parser.add_argument('--sheet', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        report = check_part(args.timeline, args.video)
        if args.sheet:
            report['comparison_sheets'] = comparison_sheet(args.timeline, args.sheet)
        output = args.output or args.timeline.parent / 'technical-qa.json'
        atomic_json(output, report)
        print(f'{output}: {len(report["technical_errors"])} technical errors; {len(report["warnings"])} warnings; manual review pending')
        if report['technical_errors']:
            raise SystemExit(1)
    except (ValueError, OSError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
