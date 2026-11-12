#!/usr/bin/env python3
"""Run an inspectable, neutral local media check; creates no story decisions or approvals."""
from pathlib import Path
import shutil
import sys
import time

from align_audio import align_file
from audio_assets import generated_sound, make_loop
from narration import NarrationSession
from quality import check_part, comparison_sheet
from studio_common import ROOT, JobStore, atomic_json, atomic_text, process, read_json, sha256_file


def run():
    base = (ROOT / '.runtime/checks/technical-demo').resolve()
    base.mkdir(parents=True, exist_ok=True)
    assert base.is_relative_to(ROOT / '.runtime/checks')
    audio = base / 'audio/narration.wav'
    text = 'This is a technical studio check. The narration should remain clear while the background stays soft.'
    atomic_text(base / 'narration.txt', text + '\n')
    session = NarrationSession(cache=base / 'production/cache/tts')
    timings = []
    for label in ('first_tts_pass', 'cached_tts_pass'):
        started = time.monotonic()
        hits, generated = session.cache_hits, session.generated_chunks
        manifest = session.render(text, audio)
        timings.append({'stage': label, 'seconds': round(time.monotonic() - started, 4),
                        'cache_hits': session.cache_hits - hits, 'generated_sentences': session.generated_chunks - generated})
    benchmark = read_json(base / 'benchmark.json', {})
    if benchmark.get('identity') == session.identity and not timings[0]['generated_sentences']:
        timings[0] = benchmark['tts_timings'][0]
    atomic_json(base / 'benchmark.json', {'identity': session.identity, 'tts_timings': timings,
                                        'note': 'First actual generation retained across warm re-runs; measurements are machine-specific.'})
    store = JobStore(base)
    alignment_path = audio.with_suffix('.alignment.json')
    for _ in range(2):
        store.run('alignment', [audio, audio.with_suffix('.chunks.json'), ROOT / 'tools/align_audio.py'], {},
                  [alignment_path], lambda: atomic_json(alignment_path, align_file(audio)))
    alignment = read_json(alignment_path)
    wind = generated_sound(base / 'production/cache/sound', {'kind': 'wind', 'duration': 2.0, 'seed': 7, 'peak_db': -18})
    loop = base / 'audio/wind-loop.wav'
    if not loop.exists():
        make_loop(wind, loop, 0.2)
    cue = generated_sound(base / 'production/cache/sound', {'kind': 'tone', 'duration': 0.4, 'frequency': 440, 'peak_db': -24})
    fixture_images = (
        ROOT / 'references/style/visual-preferences/images/realistic-cinema.png',
        ROOT / 'references/style/visual-preferences/images/cel-shaded-anime.png',
    )
    for index, source in enumerate(fixture_images, 1):
        target = base / f'images/shot_{index:03d}.png'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    duration = round(manifest['duration'] + 0.4, 6)
    cut = manifest['chunks'][1]['start']
    timeline = {'schema_version': 2, 'part_id': 'part_001', 'width': 1280, 'height': 720, 'fps': 30,
                'duration': duration, 'narration_file': 'audio/narration.wav', 'narration_start': 0.0,
                'audio_file': 'audio/final_mix.wav', 'audio_manifest': 'audio/assets.json',
                'alignment': {key: value for key, value in alignment.items() if key not in ('words', 'subtitles')},
                'subtitles': alignment['subtitles'], 'shots': [
                    {'id': 'SHOT-001', 'image': 'images/shot_001.png', 'start': 0.0, 'end': cut,
                     'style_id': 'STYLE-001', 'style_revision': 'technical-fixture'},
                    {'id': 'SHOT-002', 'image': 'images/shot_002.png', 'start': cut, 'end': duration,
                     'style_id': 'STYLE-001', 'style_revision': 'technical-fixture'}],
                'audio_cues': [
                    {'id': 'CUE-001', 'asset_id': 'AUD-001', 'role': 'ambience', 'start': 0.0, 'end': duration,
                     'gain_db': -12, 'fade_in': 0.3, 'fade_out': 0.3, 'loop': True, 'duck_under_narration': True},
                    {'id': 'CUE-002', 'asset_id': 'AUD-002', 'role': 'sfx', 'start': cut, 'end': cut + 0.4,
                     'gain_db': -6, 'fade_in': 0.02, 'fade_out': 0.04, 'loop': False, 'duck_under_narration': True}]}
    assets = {}
    import os
    for identity, source in [('AUD-001', loop), ('AUD-002', cue)]:
        assets[identity] = {'file': Path(os.path.relpath(source, base / 'audio')).as_posix(), 'sha256': sha256_file(source),
                            'source': {'method': 'procedural technical fixture'}, 'rights_status': 'unverified', 'qa_status': 'pending'}
    atomic_json(base / 'audio/assets.json', {'schema_version': 1, 'assets': assets})
    timeline_path = base / 'timeline.json'
    atomic_json(timeline_path, timeline)

    def invoke(script, *args):
        return process([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools' / script), *map(str, args)])

    mix = base / 'audio/final_mix.wav'
    for _ in range(2):
        store.run('mix', [timeline_path, loop, cue, audio, ROOT / 'tools/mix_audio.py', ROOT / 'studio.json'], {},
                  [mix, mix.with_suffix('.mix-log.json')], lambda: invoke('mix_audio.py', timeline_path, '--technical-check'))
    invoke('make_srt.py', timeline_path)
    for profile in ('preview', 'final'):
        output = base / (profile + '.mp4')
        for _ in range(2):
            store.run('render:' + profile, [timeline_path, mix, ROOT / 'tools/render_part.py', ROOT / 'studio.json',
                                           base / 'subtitles.srt', *sorted((base / 'images').glob('*.png'))], {'profile': profile},
                      [output, output.with_suffix('.render-log.json')],
                      lambda: invoke('render_part.py', timeline_path, '--profile', profile, '--output', output,
                                     '--srt', base / 'subtitles.srt'))
    report = check_part(timeline_path, base / 'final.mp4')
    report.update(technical_fixture=True, new_ai_images_generated=False,
                  comparison_sheets=comparison_sheet(timeline_path, base / 'contact-sheet.jpg'), tts_timings=timings,
                  notice='Technical check using existing example images. Flagged alignment, subjective playback and rights remain unapproved; this is not a story release.')
    atomic_json(base / 'qa-report.json', report)
    atomic_json(base / 'manifest.json', {'technical_fixture': True, 'files': {
        path.relative_to(base).as_posix(): sha256_file(path) for path in base.rglob('*')
        if path.is_file() and path.name != 'manifest.json' and 'production' not in path.relative_to(base).parts
        and '.alignment-cache' not in path.parts}})
    atomic_text(base / 'README.md', '# Local technical sample\n\n'
                'Actual CPU Kokoro speech, PocketSphinx word alignment, generated wind/tone, a crossfaded loop, '
                'speech ducking, two-pass loudness normalization, SRT, subtitle burn-in, preview and master encodes.\n\n'
                'Existing example images are technical fixtures. No story approvals, new AI images, listening or rights approval are claimed. '
                'Review qa-report.json for actual warnings and measured timings.\n')
    if report['technical_errors']:
        raise ValueError('; '.join(report['technical_errors']))
    print(base)
    print(f'{duration:.3f}s; {len(alignment["words"])} aligned words; '
          f'{len(alignment["uncertain_ranges"])} ranges await listening review; no technical errors')
    return report


if __name__ == '__main__':
    run()
