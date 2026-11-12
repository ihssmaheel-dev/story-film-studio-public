#!/usr/bin/env python3
"""Mix a part's registered audio cues and speech from its authoritative timeline."""
import argparse
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
import re

from validate_timeline import load_audio_assets, read_json, validate
from studio_common import (ROOT, configuration, executable, find_project, process,
                           require_production, sha256_file)


def probe_duration(path, ffprobe=None):
    ffprobe = ffprobe or executable('ffprobe')
    try:
        with wave.open(str(path), 'rb') as wav:
            duration = wav.getnframes() / wav.getframerate()
    except (wave.Error, EOFError):
        if not ffprobe:
            raise ValueError(f'FFprobe required to measure non-PCM-WAV input: {path}')
        result = subprocess.run([
            ffprobe, '-v', 'error', '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1', str(path),
        ], check=True, capture_output=True, text=True)
        try:
            duration = float(result.stdout.strip())
        except ValueError as error:
            raise ValueError(f'Cannot measure duration: {path}') from error
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f'Input has invalid/empty duration: {path}')
    return duration


def build_mix(timeline, ffmpeg='ffmpeg', ffprobe=None, allow_unknown=False, technical=False, draft_preview=False):
    """Build a command after input checks; this does not establish listening/rights evidence."""
    timeline = Path(timeline).resolve()
    errors = validate(timeline)
    if errors:
        raise ValueError('; '.join(errors))
    data = read_json(timeline)
    settings = configuration(find_project(timeline)).get('mix', {})
    technical = technical and timeline.is_relative_to(ROOT / '.runtime/checks') and find_project(timeline) is None
    project, reviewed_mix = find_project(timeline), False
    if project:
        from listening import current
        from workflow import part_for_path, policy
        parts = part_for_path(project, timeline)
        reviewed_mix = bool(parts and current(project, parts[0]))
        if draft_preview and policy(project)['mode'] != 'fast':
            raise ValueError('Pending listening is allowed only in a Fast draft preview')
    elif draft_preview and not technical:
        raise ValueError('Draft preview needs an authorized Fast project')
    duration = data['duration']
    output = (timeline.parent / data['audio_file']).resolve()
    if output.suffix.lower() != '.wav':
        raise ValueError('audio_file must be a .wav output for the PCM final mix')
    warnings, input_paths, graph = [], [], []
    command = [ffmpeg, '-hide_banner', '-y', '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
    graph.append(f'[0:a]atrim=duration={duration:.9f},asetpts=PTS-STARTPTS[base]')
    sources, input_index = ['[base]'], 1
    duration_cache, hash_cache, source_groups = {}, {}, {}
    narration = data.get('narration_file')
    cues = data.get('audio_cues', [])
    duck_count = sum(bool(cue.get('duck_under_narration')) for cue in cues)

    def measure(path):
        if path in duration_cache:
            return duration_cache[path]
        try:
            duration_cache[path] = probe_duration(path, ffprobe)
            return duration_cache[path]
        except ValueError as error:
            if not allow_unknown:
                raise
            warnings.append(str(error) + '; duration remains unverified in dry run')
            return None

    if narration:
        path = (timeline.parent / narration).resolve()
        if not path.is_file():
            raise ValueError(f'Narration file missing: {path}')
        input_paths.append(path)
        speech_duration = measure(path)
        start = data.get('narration_start', 0.0)
        if speech_duration is not None and start + speech_duration > duration + 0.005:
            raise ValueError('Narration extends past the presentation; revise the timeline instead of truncating speech')
        command.extend(['-i', str(path)])
        gain = data.get('narration_gain_db', 0.0)
        graph.append(
            f'[{input_index}:a]asetpts=PTS-STARTPTS,aresample=48000,'
            f'aformat=sample_fmts=fltp:channel_layouts=stereo,volume={gain:.6f}dB,'
            f'adelay={start * 1000:.6f}:all=1,apad=whole_dur={duration:.9f},'
            f'atrim=duration={duration:.9f}[narration]'
        )
        input_index += 1
        if duck_count:
            labels = '[narr_mix]' + ''.join(f'[side{index}]' for index in range(duck_count))
            graph.append(f'[narration]asplit={duck_count + 1}{labels}')
            sources.append('[narr_mix]')
        else:
            sources.append('[narration]')

    manifest_path, assets = load_audio_assets(timeline, data) if cues else (None, {})
    duck_index = 0
    for index, cue in enumerate(cues):
        asset_id = cue['asset_id']
        asset = assets.get(asset_id)
        if not isinstance(asset, dict) or not isinstance(asset.get('file'), str) or not asset['file'].strip():
            raise ValueError(f'Audio asset {asset_id} missing/invalid in registry')
        path = (manifest_path.parent / asset['file']).resolve()
        if not path.is_file():
            raise ValueError(f'Audio asset file missing: {path}')
        if not asset.get('sha256') or sha256_file(path, hash_cache) != asset['sha256']:
            raise ValueError(f'{asset_id}: missing/mismatched SHA-256')
        if not technical and (asset.get('rights_status') != 'verified' or not asset.get('rights_evidence')):
            raise ValueError(f'{asset_id}: actual usage review and rights_evidence required')
        if not technical and asset.get('qa_status') == 'failed':
            raise ValueError(f'{asset_id}: failed sound QA needs repair')
        if not technical and not (draft_preview or reviewed_mix) and (asset.get('qa_status') != 'passed' or not asset.get('qa_notes')):
            raise ValueError(f'{asset_id}: listening QA and qa_notes required')
        if not isinstance(asset.get('source'), dict) or not asset['source'].get('method'):
            raise ValueError(f'{asset_id}: source/generation provenance required')
        input_paths.append(path)
        length = cue['end'] - cue['start']
        offset = cue.get('source_offset', 0.0)
        source_duration = measure(path)
        if source_duration is not None:
            if offset >= source_duration:
                raise ValueError(f'{cue["id"]}: source_offset is outside the audio asset')
            if not cue.get('loop') and offset + length > source_duration + 0.005:
                raise ValueError(f'{cue["id"]}: source is too short; trim the cue, use a longer asset or explicitly loop it')
        key = (str(path), bool(cue.get('loop')))
        if key not in source_groups:
            source_groups[key] = {'input': input_index, 'labels': []}
            if cue.get('loop'):
                command.extend(['-stream_loop', '-1'])
            command.extend(['-i', str(path)])
            input_index += 1
        source_groups[key]['labels'].append(f'[source{index}]')
        chain = (
            f'[source{index}]atrim=start={offset:.9f}:duration={length:.9f},'
            'asetpts=PTS-STARTPTS,aresample=48000,'
            'aformat=sample_fmts=fltp:channel_layouts=stereo,'
            f'volume={cue.get("gain_db", 0.0):.6f}dB'
        )
        if cue.get('fade_in', 0.0):
            chain += f',afade=t=in:st=0:d={cue["fade_in"]:.9f}'
        if cue.get('fade_out', 0.0):
            chain += f',afade=t=out:st={length - cue["fade_out"]:.9f}:d={cue["fade_out"]:.9f}'
        chain += (
            f',adelay={cue["start"] * 1000:.6f}:all=1,'
            f'apad=whole_dur={duration:.9f},atrim=duration={duration:.9f}[cue{index}]'
        )
        graph.append(chain)
        if cue.get('duck_under_narration'):
            threshold = float(settings.get('duck_threshold', 0.03))
            ratio = float(settings.get('duck_ratio', 6))
            attack = float(settings.get('duck_attack_ms', 15))
            release = float(settings.get('duck_release_ms', 300))
            if not (0 < threshold <= 1 and 1 <= ratio <= 20 and 0.01 <= attack <= 2000 and 0.01 <= release <= 9000):
                raise ValueError('Invalid approved ducking settings')
            graph.append(
                f'[cue{index}][side{duck_index}]sidechaincompress='
                f'threshold={threshold}:ratio={ratio}:attack={attack}:release={release}[duck{index}]'
            )
            sources.append(f'[duck{index}]')
            duck_index += 1
        else:
            sources.append(f'[cue{index}]')
    for source in source_groups.values():
        count = len(source['labels'])
        splitter = f'asplit={count}' if count > 1 else 'anull'
        graph.append(f'[{source["input"]}:a]{splitter}' + ''.join(source['labels']))
    if output in input_paths:
        raise ValueError('Final mix would overwrite an input asset/narration; choose a separate audio_file')
    graph.append(
        ''.join(sources) + f'amix=inputs={len(sources)}:duration=longest:normalize=0,'
        f'alimiter=limit=0.95:level=0:latency=1,atrim=duration={duration:.9f},'
        'asetpts=PTS-STARTPTS[mix]'
    )
    filter_graph = ';\n'.join(graph)
    command.extend([
        '-filter_complex', filter_graph, '-map', '[mix]', '-t', f'{duration:.9f}',
        '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', str(output),
    ])
    return command, warnings


def normalize_mix(ffmpeg, source, output, duration, settings):
    target = float(settings.get('integrated_lufs', -16))
    peak = float(settings.get('true_peak_db', -1.5))
    loudness_range = float(settings.get('loudness_range', 11))
    if not (-70 <= target <= -5 and -9 <= peak <= 0 and 1 <= loudness_range <= 50):
        raise ValueError('Loudness targets are outside supported measurement ranges')
    base = f'loudnorm=I={target}:TP={peak}:LRA={loudness_range}'
    # Feed more than the dynamic filter's three-second analysis buffer before
    # trimming. A 0.2-second flush lost quiet final effects in an actual long mix
    # on the configured runtime. Trim at the final sample clock after resampling.
    measurement = process([ffmpeg, '-hide_banner', '-i', str(source), '-af',
                           'apad=pad_dur=4,' + base + ':print_format=json', '-f', 'null', '-'])
    blocks = re.findall(r'\{[^{}]*"input_i"[^{}]*\}', measurement.stderr, re.S)
    if not blocks:
        raise ValueError('FFmpeg did not provide loudness measurements')
    measured = json.loads(blocks[-1])
    if measured['input_i'] == '-inf':
        shutil.copy2(source, output)
        return {'applied': False, 'reason': 'deliberately silent signal', 'measurements': measured}
    options = ':'.join([base,
        f'measured_I={measured["input_i"]}', f'measured_TP={measured["input_tp"]}',
        f'measured_LRA={measured["input_lra"]}', f'measured_thresh={measured["input_thresh"]}',
        f'offset={measured["target_offset"]}', 'linear=true', 'print_format=json'])
    rendered = process([ffmpeg, '-hide_banner', '-y', '-i', str(source), '-af',
                        'apad=pad_dur=4,' + options + f',aresample=48000,apad=whole_len={round(duration*48000)},'
                        f'atrim=end_sample={round(duration*48000)},asetpts=PTS-STARTPTS',
                        '-ar', '48000', '-ac', '2', '-c:a', 'pcm_s16le', str(output)])
    final = re.findall(r'\{[^{}]*"input_i"[^{}]*\}', rendered.stderr, re.S)
    return {'applied': True, 'flush_padding_seconds': 4,
            'targets': {'integrated_lufs': target, 'true_peak_db': peak, 'lra': loudness_range},
            'measurements': json.loads(final[-1]) if final else measured}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('timeline', type=Path)
    parser.add_argument('--dry-run', action='store_true', help='Check inputs and print plan without creating a mix')
    parser.add_argument('--ffmpeg', help='Explicit FFmpeg executable if not on PATH')
    parser.add_argument('--ffprobe', help='Explicit FFprobe executable if not on PATH')
    parser.add_argument('--profile', choices=('preview', 'final'), default='final')
    parser.add_argument('--draft-preview', action='store_true', help='Fast only: pending listening in a complete draft; rights still required')
    parser.add_argument('--technical-check', action='store_true', help='Unreviewed synthetic fixture only under .runtime/checks; never a release')
    args = parser.parse_args()
    ffmpeg = executable('ffmpeg', args.ffmpeg)
    ffprobe = executable('ffprobe', args.ffprobe)
    if not args.dry_run:
        require_production(args.timeline, stage='mix')
    if args.technical_check and not args.timeline.resolve().is_relative_to(ROOT / '.runtime/checks'):
        parser.error('Technical-fixture exceptions are restricted to .runtime/checks')
    if not args.dry_run and not ffmpeg:
        parser.error('FFmpeg missing; install/configure it or pass --ffmpeg')
    try:
        command, warnings = build_mix(args.timeline, ffmpeg or 'ffmpeg', ffprobe, args.dry_run, args.technical_check, args.draft_preview)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.error(str(error))
    if args.dry_run:
        if not ffmpeg:
            warnings.append('FFmpeg is not configured; no mixing has been performed')
        print(json.dumps({'command': command, 'warnings': warnings, 'rendered': False}, indent=2))
        return
    output = Path(command[-1])
    output.parent.mkdir(parents=True, exist_ok=True)
    # Filter scripts avoid putting a potentially long graph on the Windows command line.
    with tempfile.TemporaryDirectory(prefix='.audio-mix-', dir=output.parent) as directory:
        temporary = Path(directory).resolve()
        if temporary.parent != output.parent.resolve():
            raise RuntimeError('Unexpected temporary directory outside the output folder')
        graph_index = command.index('-filter_complex')
        graph = command[graph_index + 1]
        script = temporary / 'mix.ffscript'
        script.write_text(graph, encoding='utf-8')
        actual = command[:]
        actual[graph_index:graph_index + 2] = ['-/filter_complex', str(script)]
        actual[-1] = str(temporary / 'mixed.wav')
        process(actual, timeout=configuration().get('jobs', {}).get('timeout_seconds', 900))
        expected_duration = read_json(args.timeline)['duration']
        normalization = {'applied': False, 'reason': 'preview profile'}
        if args.profile == 'final':
            normalized = temporary / 'normalized.wav'
            normalization = normalize_mix(ffmpeg, Path(actual[-1]), normalized, expected_duration,
                                           configuration(find_project(args.timeline)).get('mix', {}))
            actual[-1] = str(normalized)
        if abs(probe_duration(Path(actual[-1]), ffprobe) - expected_duration) > 1 / 48000 + 0.000001:
            raise ValueError('Mixed WAV duration differs from the timeline; previous output preserved')
        from audio_check import mix_coverage_errors
        coverage_warnings = []
        coverage = mix_coverage_errors(args.timeline, Path(actual[-1]), coverage_warnings)
        if coverage:
            raise ValueError('; '.join(coverage) + '; previous mix preserved')
        Path(actual[-1]).replace(output)
    output.with_suffix('.mix-log.json').write_text(json.dumps({
        'timeline': str(args.timeline.resolve()),
        'timeline_sha256': hashlib.sha256(args.timeline.read_bytes()).hexdigest(),
        'reproducible_command': command,
        'output_sha256': sha256_file(output),
        'source_input_hashes': {str(Path(command[index + 1]).resolve()): sha256_file(command[index + 1])
                                for index, value in enumerate(command[:-1])
                                if value == '-i' and Path(command[index + 1]).is_file()},
        'audio_manifest_sha256': sha256_file(args.timeline.parent / read_json(args.timeline)['audio_manifest'])
                                 if read_json(args.timeline).get('audio_cues') else None,
        'measured_duration': probe_duration(output, ffprobe),
        'normalization': normalization,
        'technical_fixture': args.technical_check,
        'draft_preview_pending_listening': args.draft_preview,
        'coverage_warnings': coverage_warnings,
        'qa_status': 'listening_and_loudness_review_pending',
    }, indent=2) + '\n', encoding='utf-8')
    print(output)


if __name__ == '__main__':
    main()
