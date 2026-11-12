#!/usr/bin/env python3
"""Create a limited procedural wind/rain-like texture, hum or tone on CPU."""
import argparse
import hashlib
import json
import math
import wave
from datetime import datetime, timezone
from pathlib import Path
from studio_common import require_authorized_work, sha256_file


def raw_blocks(kind, duration, rate, seed, frequency):
    try:
        import numpy as np
    except ImportError as error:
        raise ValueError('Install requirements-audio.txt for procedural sound generation') from error
    frames = round(duration * rate)
    rng = np.random.default_rng(seed)
    width = max(2, round(rate / 180))
    history = np.zeros((width, 2))
    previous = np.zeros((1, 2))
    fade = min(round(0.1 * rate), frames // 2)
    for start in range(0, frames, rate):
        count = min(rate, frames - start)
        positions = np.arange(start, start + count, dtype=np.float64)
        time = positions / rate
        noise = rng.standard_normal((count, 2))
        if kind == 'wind':
            padded = np.concatenate((history, noise))
            cumulative = np.cumsum(padded, axis=0)
            signal = (cumulative[width:] - cumulative[:-width]) / width
            history = padded[-width:].copy()
            signal *= (0.65 + 0.25 * np.sin(2 * np.pi * time / 7))[:, None]
        elif kind == 'rain':
            shifted = np.concatenate((previous, noise[:-1]))
            signal = 0.7 * noise + 0.3 * shifted
            previous = noise[-1:].copy()
            signal *= (0.8 + 0.08 * np.sin(2 * np.pi * time / 3))[:, None]
        else:
            signal = np.sin(2 * np.pi * frequency * time)
            if kind == 'hum':
                signal += 0.3 * np.sin(2 * np.pi * frequency * 2 * time)
                signal += 0.15 * np.sin(2 * np.pi * frequency * 3 * time)
            signal = np.column_stack((signal, signal))
            if kind == 'hum':
                signal += noise * 0.01
        if fade > 1:
            envelope = np.clip(np.minimum(positions, frames - 1 - positions) / (fade - 1), 0, 1)
            signal *= envelope[:, None]
        yield signal


def pcm_blocks(kind, duration, rate, seed, frequency, peak_db):
    import numpy as np
    peak = max(float(np.max(np.abs(block))) for block in raw_blocks(kind, duration, rate, seed, frequency))
    scale = 10 ** (peak_db / 20) / max(peak, 1e-12)
    for block in raw_blocks(kind, duration, rate, seed, frequency):
        yield np.rint(block * scale * 32767).astype('<i2').tobytes()


def synthesize(kind, duration, rate, seed, frequency, peak_db):
    import numpy as np
    return b''.join(pcm_blocks(kind, duration, rate, seed, frequency, peak_db)), np.__version__


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', required=True, choices=('wind', 'rain', 'hum', 'tone'))
    parser.add_argument('--duration', required=True, type=float, help='0.1–600 seconds; use explicit timeline loops for longer ambience')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--frequency', type=float, help='Hum/tone fundamental in Hz')
    parser.add_argument('--sample-rate', type=int, default=48000, choices=(44100, 48000))
    parser.add_argument('--peak-db', type=float, default=-18.0, help='Peak target, not integrated loudness')
    parser.add_argument('--purpose', choices=('final', 'audition'), default='final')
    args = parser.parse_args()
    if not math.isfinite(args.duration) or not 0.1 <= args.duration <= 600:
        parser.error('duration must be between 0.1 and 600 seconds')
    if not math.isfinite(args.peak_db) or not -60 <= args.peak_db <= -1:
        parser.error('peak-db must be between -60 and -1')
    if args.seed < 0:
        parser.error('seed must be nonnegative')
    frequency = args.frequency if args.frequency is not None else (60 if args.kind == 'hum' else 220)
    if not math.isfinite(frequency) or not 20 <= frequency <= args.sample_rate / 8:
        parser.error('frequency must be finite and between 20 Hz and sample-rate / 8')
    output = args.output.resolve()
    sidecar = output.with_suffix(output.suffix + '.json')
    if output.suffix.lower() != '.wav':
        parser.error('output must use a .wav extension')
    if output.exists() or sidecar.exists():
        parser.error('Output or sidecar exists; use a new revision filename')
    try:
        require_authorized_work(output, args.purpose, 'procedural-audio')
        import numpy as np
        numpy_version = np.__version__
    except ValueError as error:
        parser.error(str(error))
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), 'wb') as wav:
        wav.setnchannels(2)
        wav.setsampwidth(2)
        wav.setframerate(args.sample_rate)
        for audio in pcm_blocks(args.kind, args.duration, args.sample_rate, args.seed, frequency, args.peak_db):
            wav.writeframes(audio)
    sidecar.write_text(json.dumps({
        'method': 'procedural',
        'tool': 'tools/generate_sound.py',
        'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'numpy_version': numpy_version,
        'kind': args.kind,
        'parameters': {
            'duration': args.duration, 'sample_rate': args.sample_rate,
            'seed': args.seed, 'frequency': frequency, 'peak_db': args.peak_db,
        },
        'generated_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'file_sha256': sha256_file(output),
        'algorithm_revision': 2,
        'working_block_seconds': 1,
        'description': 'Synthesized approximation; no external audio sample used.',
        'rights_status': 'review_required',
        'qa_status': 'pending',
    }, indent=2) + '\n', encoding='utf-8')
    print(output)
    print(f'Provenance: {sidecar}; listening and usage review remain pending.')


if __name__ == '__main__':
    main()
