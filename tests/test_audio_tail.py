"""Real FFmpeg regression for a quiet sound cue after the main performance."""
import array
import math
from pathlib import Path
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from mix_audio import normalize_mix, probe_duration
from studio_common import executable


@unittest.skipUnless(executable('ffmpeg'), 'Actual FFmpeg normalization required')
class NormalizationTail(unittest.TestCase):
    def test_dynamic_normalization_preserves_quiet_final_cue_at_original_time(self):
        rate, duration = 48000, 94.31
        samples = array.array('h')
        for index in range(round(rate * duration)):
            instant = index / rate
            amplitude = 0.04 if instant < 90.88 else 0.012 if instant > 91.7 else 0
            # A real short high crest forces the dynamic mode instead of the
            # linear shortcut that would miss the buffered-tail failure.
            if 2 < instant < 2.02:
                amplitude = 0.95
            value = round(32767 * amplitude * math.sin(2 * math.pi * 330 * instant))
            samples.extend((value, value))
        if sys.byteorder != 'little':
            samples.byteswap()
        with tempfile.TemporaryDirectory(prefix='studio-normalization-tail-') as directory:
            source, output = Path(directory) / 'source.wav', Path(directory) / 'normalized.wav'
            with wave.open(str(source), 'wb') as stream:
                stream.setparams((2, 2, rate, 0, 'NONE', 'not compressed'))
                stream.writeframes(samples.tobytes())
            result = normalize_mix(executable('ffmpeg'), source, output, duration, {})
            self.assertEqual(result['measurements']['normalization_type'], 'dynamic')
            self.assertAlmostEqual(probe_duration(output), duration, places=5)
            with wave.open(str(output), 'rb') as stream:
                stream.setpos(round(93.1 * rate))
                tail = array.array('h', stream.readframes(round(0.4 * rate)))
            if sys.byteorder != 'little':
                tail.byteswap()
            self.assertGreater(max(map(abs, tail)), 100,
                               'The actual quiet ending was lost or shifted during normalization')


if __name__ == '__main__':
    unittest.main()
