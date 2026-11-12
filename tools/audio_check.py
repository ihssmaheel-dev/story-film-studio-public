"""Cheap signal-coverage checks before encoding; these do not establish listening QA."""
from pathlib import Path

from studio_common import read_json


def mix_coverage_errors(timeline_path, mixed_file=None, warnings=None):
    """Catch non-silent cue tails lost after narration (e.g. a filter flush bug).

    Only near-total signal loss is rejected. This does not score acting, prove
    that an individual sound is audible in a busy mix, or replace listening.
    """
    import numpy as np
    import soundfile as sf
    timeline_path = Path(timeline_path).resolve()
    data = read_json(timeline_path)
    cues = data.get('audio_cues', [])
    if not cues:
        return []
    mixed_file = Path(mixed_file) if mixed_file else timeline_path.parent / data['audio_file']
    manifest = (timeline_path.parent / data['audio_manifest']).resolve()
    assets = read_json(manifest)['assets']
    speech_end = 0
    if data.get('narration_file'):
        from mix_audio import probe_duration
        speech_end = probe_duration(timeline_path.parent / data['narration_file']) + data.get('narration_start', 0)
    errors = []
    with sf.SoundFile(mixed_file) as mix:
        for cue in cues:
            begin, end = max(cue['start'], speech_end), cue['end']
            if end <= begin:
                continue
            source_path = manifest.parent / assets[cue['asset_id']]['file']
            try:
                opened = sf.SoundFile(source_path)
            except sf.LibsndfileError:
                if warnings is not None:
                    warnings.append(cue['id'] + ': compressed source needs actual listening; signal coverage could not decode this format')
                continue
            with opened as source:
                instant = begin
                while instant < end - 0.01:
                    length = min(0.25, end - instant)
                    source_time = cue.get('source_offset', 0) + instant - cue['start']
                    if cue.get('loop'):
                        source_time %= source.frames / source.samplerate
                    source.seek(min(source.frames, round(source_time * source.samplerate)))
                    samples = source.read(max(1, round(length * source.samplerate)), always_2d=True)
                    expected = float(np.max(np.abs(samples))) if samples.size else 0
                    expected *= 10 ** (cue.get('gain_db', 0) / 20)
                    midpoint = instant + length / 2
                    if cue.get('fade_in'):
                        expected *= min(1, max(0, (midpoint - cue['start']) / cue['fade_in']))
                    if cue.get('fade_out'):
                        expected *= min(1, max(0, (end - midpoint) / cue['fade_out']))
                    if expected > 0.001:
                        mix.seek(min(mix.frames, round(instant * mix.samplerate)))
                        actual = mix.read(max(1, round(length * mix.samplerate)), always_2d=True)
                        peak = float(np.max(np.abs(actual))) if actual.size else 0
                        if peak < 0.00001:
                            errors.append(f'{cue["id"]}: non-silent sound is missing from the mix at {instant:.2f}s; inspect filter tails before preview')
                            break
                    instant += length
    return errors
