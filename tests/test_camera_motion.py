"""Camera motion validation, zoompan compilation, dry-run and QA checks."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

from camera_motion import active_motion, camera_filter, normalize_motion, source_motion_issues
from quality import check_part
from studio_common import atomic_json, executable, read_json
from test_studio import write_tone


class CameraMotionTests(unittest.TestCase):
    def test_normalize_motion_validates_bounds_and_protected_regions(self):
        self.assertEqual(normalize_motion(None)['type'], 'static')
        move = normalize_motion({
            'type': 'zoom_in',
            'reason': 'Close on the watch face as it stops.',
            'start': {'zoom': 1.0, 'center': [0.5, 0.5]},
            'end': {'zoom': 1.15, 'center': [0.5, 0.5]},
            'protected_regions': [{'id': 'watch', 'box': [0.3, 0.3, 0.7, 0.7]}],
        })
        self.assertEqual(move['type'], 'zoom_in')
        self.assertTrue(active_motion({'motion': move}))

        for bad in (
            {'type': 'zoom_in', 'protected_regions': [{'id': 'a', 'box': [0.4, 0.4, 0.6, 0.6]}]},
            {'type': 'zoom_in', 'reason': 'x', 'end': {'zoom': 1.5, 'center': [0.5, 0.5]},
             'protected_regions': [{'id': 'a', 'box': [0.4, 0.4, 0.6, 0.6]}]},
            {'type': 'pan', 'reason': 'x', 'start': {'zoom': 1.1, 'center': [0.5, 0.5]},
             'end': {'zoom': 1.1, 'center': [0.5, 0.5]},
             'protected_regions': [{'id': 'a', 'box': [0.4, 0.4, 0.6, 0.6]}]},
            {'type': 'zoom_in', 'reason': 'x', 'end': {'zoom': 1.2, 'center': [0.5, 0.5]},
             'protected_regions': [{'id': 'edge', 'box': [0.01, 0.4, 0.6, 0.6]}]},
            {'type': 'zoom_out', 'reason': 'x', 'start': {'zoom': 1.0, 'center': [0.5, 0.5]},
             'end': {'zoom': 1.1, 'center': [0.5, 0.5]},
             'protected_regions': [{'id': 'a', 'box': [0.4, 0.4, 0.6, 0.6]}]},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize_motion(bad)

    def test_source_motion_issues_and_camera_filter_compilation(self):
        move = normalize_motion({
            'type': 'pan',
            'reason': 'Follow the envelope across the desk.',
            'start': {'zoom': 1.1, 'center': [0.46, 0.5]},
            'end': {'zoom': 1.1, 'center': [0.54, 0.5]},
            'easing': 'linear',
            'start_at': 0.1,
            'end_at': 0.9,
            'protected_regions': [{'id': 'envelope', 'box': [0.4, 0.4, 0.6, 0.6]}],
        })
        errors, warnings = source_motion_issues((1080, 1920), 1920, 1080, move)
        self.assertTrue(errors)
        errors, warnings = source_motion_issues((1920, 1080), 1920, 1080, move)
        self.assertEqual(errors, [])
        self.assertTrue(warnings)
        errors, warnings = source_motion_issues((2560, 1440), 1920, 1080, move)
        self.assertEqual((errors, warnings), ([], []))

        compiled = camera_filter({
            'fps': 24,
            'shots': [
                {'id': 'SHOT-001', 'start': 0.0, 'end': 1.5, 'motion': move},
                {'id': 'SHOT-002', 'start': 1.5, 'end': 3.0, 'motion': None},
            ],
        }, 1280, 720)
        self.assertIn('zoompan=', compiled)
        self.assertIn('if(lt(on,36),', compiled)
        self.assertIn(':s=1280x720:fps=24', compiled)

    def test_moving_render_dry_run_and_optional_ffmpeg_qa(self):
        from PIL import Image
        with tempfile.TemporaryDirectory(prefix='studio-motion-') as temporary:
            part = Path(temporary).resolve()
            (part / 'images').mkdir()
            Image.new('RGB', (1920, 1080), 'navy').save(part / 'images/shot_001.png')
            Image.new('RGB', (1920, 1080), 'teal').save(part / 'images/shot_002.png')
            write_tone(part / 'audio/final_mix.wav', 2.4)
            move = {
                'type': 'zoom_in',
                'reason': 'Approach the station clock.',
                'start': {'zoom': 1.0, 'center': [0.5, 0.5]},
                'end': {'zoom': 1.12, 'center': [0.5, 0.5]},
                'protected_regions': [{'id': 'clock', 'box': [0.35, 0.35, 0.65, 0.65]}],
            }
            timeline = {
                'schema_version': 2, 'part_id': 'part_001', 'width': 640, 'height': 360, 'fps': 24,
                'duration': 2.4, 'narration_file': None, 'audio_file': 'audio/final_mix.wav',
                'shots': [
                    {'id': 'SHOT-001', 'image': 'images/shot_001.png', 'start': 0.0, 'end': 1.2,
                     'style_id': 'STYLE-001', 'style_revision': 'r1', 'motion': move},
                    {'id': 'SHOT-002', 'image': 'images/shot_002.png', 'start': 1.2, 'end': 2.4,
                     'style_id': 'STYLE-001', 'style_revision': 'r1'},
                ],
                'subtitles': [], 'audio_cues': [],
            }
            atomic_json(part / 'timeline.json', timeline)
            dry = subprocess.run(
                [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools/render_part.py'),
                 str(part / 'timeline.json'), '--output', str(part / 'preview.mp4'), '--dry-run'],
                capture_output=True, text=True, check=True,
            )
            plan = json.loads(dry.stdout)
            self.assertEqual(plan['working_dimensions'], [1280, 720])
            self.assertIn('-/filter:v', plan['command'])
            self.assertEqual(plan['camera_motion']['SHOT-001']['type'], 'zoom_in')
            self.assertEqual(plan['camera_motion']['SHOT-002']['type'], 'static')

            if executable('ffmpeg'):
                subprocess.run(
                    [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools/render_part.py'),
                     str(part / 'timeline.json'), '--output', str(part / 'preview.mp4'), '--profile', 'preview'],
                    capture_output=True, text=True, check=True,
                )
                report = check_part(part / 'timeline.json', part / 'preview.mp4')
                self.assertEqual(report['technical_errors'], [])
                self.assertTrue(any('Camera movement requires playback inspection' in w for w in report['warnings']))
                render_log = read_json(part / 'preview.render-log.json')
                self.assertEqual(list(render_log['source_image_hashes']), ['images/shot_001.png', 'images/shot_002.png'])


if __name__ == '__main__':
    unittest.main()
