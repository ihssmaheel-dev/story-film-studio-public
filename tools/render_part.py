#!/usr/bin/env python3
"""Render stills with optional authored camera movement and the declared final mix."""
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from mix_audio import probe_duration
from camera_motion import active_motion, camera_filter, normalize_motion
from validate_timeline import validate
from studio_common import atomic_json, configuration, executable, find_project, fingerprint, process, read_json, require_production, sha256_file
from workflow import presentation


def ffconcat_quote(path):
    return "'" + Path(path).as_posix().replace("'", "'\\''") + "'"


def prepare_still(source, cache, width, height, scale_filter):
    """Normalize dimensions before concat so decoder/filter resets cannot discard earlier holds."""
    from PIL import Image, ImageOps, __version__
    from studio_common import read_json as read_record
    key = fingerprint({'source': sha256_file(source), 'width': width, 'height': height,
                       'filter': scale_filter, 'pillow': __version__, 'revision': 1})
    target = Path(cache) / (key + '.png')
    receipt = target.with_suffix('.json')
    try:
        intact = target.is_file() and read_record(receipt, {}).get('sha256') == sha256_file(target)
    except (ValueError, OSError):
        intact = False
    if not intact:
        target.parent.mkdir(parents=True, exist_ok=True)
        method = {'lanczos': Image.Resampling.LANCZOS, 'bicubic': Image.Resampling.BICUBIC,
                  'neighbor': Image.Resampling.NEAREST}[scale_filter]
        with Image.open(source) as original:
            corrected = ImageOps.exif_transpose(original).convert('RGB')
            scaled = ImageOps.contain(corrected, (width, height), method=method)
            frame = Image.new('RGB', (width, height), 'black')
            frame.paste(scaled, ((width - scaled.width) // 2, (height - scaled.height) // 2))
            candidate = target.with_suffix('.partial.png')
            frame.save(candidate)
            candidate.replace(target)
        atomic_json(receipt, {'sha256': sha256_file(target), 'source_sha256': sha256_file(source), 'key': key})
    return target


def encoded_metadata(ffprobe, path, width, height, duration, fps):
    if not ffprobe:
        return None
    result = json.loads(process([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]).stdout)
    video = next(stream for stream in result['streams'] if stream['codec_type'] == 'video')
    if video['width'] != width or video['height'] != height:
        raise ValueError('Encoded dimensions do not match the selected profile')
    if abs(float(video.get('start_time', 0))) > 1 / fps or abs(float(video['duration']) - duration) > 2 / fps:
        raise ValueError('Encoded video lost part of the presentation; start/duration verification failed')
    if abs(int(video.get('nb_frames', 0)) - round(duration * fps)) > 1:
        raise ValueError('Encoded frame count does not cover the presentation')
    if not any(stream['codec_type'] == 'audio' for stream in result['streams']):
        raise ValueError('Encoded file has no audio stream')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('timeline', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--srt', type=Path, help='Burn subtitles if FFmpeg has libass')
    parser.add_argument('--ffmpeg', help='Explicit FFmpeg executable if not on PATH')
    parser.add_argument('--ffprobe', help='Explicit FFprobe executable if not on PATH')
    parser.add_argument('--dry-run', action='store_true', help='Validate and print the render plan without encoding')
    parser.add_argument('--profile', choices=('preview', 'final'), default='final')
    parser.add_argument('--preset', choices=('ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow'))
    parser.add_argument('--crf', type=int)
    args = parser.parse_args()
    timeline, output = args.timeline.resolve(), args.output.resolve()
    errors = validate(timeline, check_assets=True)
    if errors:
        parser.error('; '.join(errors))
    if output.suffix.lower() != '.mp4':
        parser.error('output must be an MP4 path')
    ffmpeg = executable('ffmpeg', args.ffmpeg)
    ffprobe = executable('ffprobe', args.ffprobe)
    if not args.dry_run:
        project = require_production(timeline, stage='master' if args.profile == 'final' else 'render')
        if project:
            from project_records import validate_continuity
            from workflow import part_for_path
            problems = validate_continuity(project, part_for_path(project, timeline))
            if problems:
                parser.error('; '.join(problems))
    profile = configuration(find_project(timeline))['render_profiles'][args.profile]
    preset = args.preset or profile['preset']
    crf = args.crf if args.crf is not None else profile['crf']
    if not isinstance(crf, int) or not 0 <= crf <= 51:
        parser.error('CRF must be an integer from 0 through 51')
    if args.profile == 'preview' and output.name == 'final.mp4':
        parser.error('A preview must use a preview filename, preserving the final master')
    if not ffmpeg and not args.dry_run:
        parser.error('FFmpeg is missing; configure it or pass --ffmpeg')
    if args.srt and not args.srt.is_file():
        parser.error('SRT file does not exist')
    data = read_json(timeline)
    audio = (timeline.parent / data['audio_file']).resolve()
    try:
        measured = probe_duration(audio, ffprobe)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    if abs(measured - data['duration']) > max(0.005, 1 / data['fps']):
        parser.error('Final mix duration does not cover the declared presentation; rebuild/check the mix')
    from audio_check import mix_coverage_errors
    coverage = mix_coverage_errors(timeline, audio)
    if coverage:
        parser.error('; '.join(coverage))
    width, height, fps = data['width'], data['height'], data['fps']
    if profile.get('max_dimension') and max(width, height) > profile['max_dimension']:
        ratio = profile['max_dimension'] / max(width, height)
        width, height = max(2, round(width * ratio / 2) * 2), max(2, round(height * ratio / 2) * 2)
    scale_filter = data.get('scale_filter', 'lanczos')
    if scale_filter not in ('lanczos', 'neighbor', 'bicubic'):
        parser.error('scale_filter must be lanczos, neighbor or bicubic')
    moving = any(active_motion(shot) for shot in data['shots'])
    image_hashes = {str((timeline.parent / shot['image']).resolve()): sha256_file(timeline.parent / shot['image'])
                    for shot in data['shots']}
    picture_key = fingerprint({'images': image_hashes, 'duration': data['duration'], 'width': width, 'height': height,
        'fps': fps, 'scale_filter': scale_filter, 'preset': preset, 'crf': crf,
        'shots': [{key: shot.get(key) for key in ('image', 'start', 'end', 'motion')} for shot in data['shots']],
        'subtitles': sha256_file(args.srt) if args.srt else None,
        'compiler': sha256_file(__file__), 'camera_compiler': sha256_file(Path(__file__).with_name('camera_motion.py')),
        'ffmpeg': sha256_file(ffmpeg) if ffmpeg else None})
    try:
        old = read_json(output.with_suffix('.render-log.json'), {})
    except (OSError, ValueError):
        old = {}
    if not args.dry_run and old.get('picture_fingerprint') == picture_key and output.is_file() and old.get('output_sha256') == sha256_file(output):
        previous = sha256_file(output)
        mode = 'unchanged_media'
        if old.get('audio_sha256') != sha256_file(audio):
            with tempfile.TemporaryDirectory(prefix='.part-render-', dir=timeline.parent) as directory:
                candidate = Path(directory) / 'remuxed.mp4'
                command = [ffmpeg, '-hide_banner', '-y', '-i', str(output), '-i', str(audio),
                           '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                           '-t', str(data['duration']), '-movflags', '+faststart', str(candidate)]
                process(command, timeout=configuration()['jobs']['timeout_seconds'], progress_seconds=data['duration'])
                old['stream_metadata'] = encoded_metadata(ffprobe, candidate, width, height, data['duration'], fps)
                candidate.replace(output)
            old['command'] = command
            mode = 'audio_remux'
        old.update(timeline_sha256=sha256_file(timeline), presentation_fingerprint=fingerprint(presentation(data)),
                   audio_sha256=sha256_file(audio), output_sha256=sha256_file(output), mode=mode,
                   reused_picture_from_sha256=previous, qa_status='full_playback_and_sync_review_pending')
        atomic_json(output.with_suffix('.render-log.json'), old)
        print(output)
        return
    # One common source size keeps the continuous filter state across image changes.
    # Double-size cached frames reduce integer crop stepping without making video intermediates.
    working_width, working_height = (width * 2, height * 2) if moving else (width, height)
    with tempfile.TemporaryDirectory(prefix='.part-render-', dir=timeline.parent) as directory:
        temporary = Path(directory).resolve()
        if temporary.parent != timeline.parent:
            raise RuntimeError('Unexpected temporary directory outside the part folder')
        concat = temporary / 'shots.ffconcat'
        lines = ['ffconcat version 1.0']
        prepared = {}
        cache = (find_project(timeline) or timeline.parent) / 'production/cache/frames'
        for shot in data['shots']:
            image = (timeline.parent / shot['image']).resolve()
            if image not in prepared:
                prepared[image] = image if args.dry_run else prepare_still(image, cache, working_width, working_height, scale_filter)
            lines.extend([
                f'file {ffconcat_quote(prepared[image])}', f'option framerate {fps}',
                f'duration {shot["end"] - shot["start"]:.9f}',
            ])
        lines.extend([
            f'file {ffconcat_quote(prepared[(timeline.parent / data["shots"][-1]["image"]).resolve()])}',
            f'option framerate {fps}',
        ])
        content = '\n'.join(lines) + '\n'
        concat.write_text(content, encoding='utf-8')
        video_filter = (
            f'fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease:flags={scale_filter},'
            f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p'
        )
        if moving:
            try:
                video_filter = camera_filter(data, width, height)
            except ValueError as error:
                parser.error(str(error))
        if args.srt:
            shutil.copyfile(args.srt, temporary / 'captions.srt')
            video_filter += ',subtitles=captions.srt'
        filter_options = ['-vf', video_filter]
        if moving:
            # Read long per-shot expressions from a file instead of the Windows command line.
            filter_file = temporary / 'camera-filter.txt'
            filter_file.write_text(video_filter, encoding='utf-8')
            filter_options = ['-/filter:v', str(filter_file)]
        command = [
            ffmpeg or 'ffmpeg', '-hide_banner', '-y', '-safe', '0', '-f', 'concat',
            '-i', str(concat), '-i', str(audio), '-map', '0:v:0', '-map', '1:a:0',
            *filter_options, '-t', str(data['duration']), '-r', str(fps),
            '-c:v', 'libx264', '-preset', preset, '-crf', str(crf), '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', str(output),
        ]
        if args.dry_run:
            print(json.dumps({'command': command, 'concat': content, 'video_filter': video_filter,
                              'working_dimensions': [working_width, working_height],
                              'camera_motion': {shot['id']: normalize_motion(shot.get('motion')) for shot in data['shots']},
                              'encoded': False}, indent=2))
            return
        output.parent.mkdir(parents=True, exist_ok=True)
        actual = command[:]
        actual[-1] = str(temporary / 'rendered.mp4')
        process(actual, timeout=configuration().get('jobs', {}).get('timeout_seconds', 900), cwd=temporary,
                progress_seconds=data['duration'])
        stream_metadata = encoded_metadata(ffprobe, actual[-1], width, height, data['duration'], fps)
        Path(actual[-1]).replace(output)
        output.with_suffix('.render-log.json').write_text(json.dumps({
            'timeline_sha256': hashlib.sha256(timeline.read_bytes()).hexdigest(),
            'presentation_fingerprint': fingerprint(presentation(data)),
            'picture_fingerprint': picture_key, 'mode': 'full_encode',
            'command': command, 'concat': content,
            'video_filter': video_filter, 'working_dimensions': [working_width, working_height],
            'camera_motion': {shot['id']: normalize_motion(shot.get('motion')) for shot in data['shots']},
            'output_sha256': sha256_file(output), 'profile': args.profile,
            'source_image_hashes': {str(source): sha256_file(source) for source in prepared},
            'audio_sha256': sha256_file(audio),
            'subtitles_sha256': sha256_file(args.srt) if args.srt else None,
            'width': width, 'height': height, 'fps': fps, 'stream_metadata': stream_metadata,
            'qa_status': 'full_playback_and_sync_review_pending',
        }, indent=2) + '\n', encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
