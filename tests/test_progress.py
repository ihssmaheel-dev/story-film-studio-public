"""Actual progress, honest estimates, read-only cross-worktree APIs and telemetry failures."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from monitor import make_server
from progress_records import Task, advance, location, note
from progress_snapshot import Monitor, Reader, estimate, remaining_estimate
from studio_common import JobStore, atomic_json, atomic_text, executable, process, read_json, sha256_file, fingerprint
from workflow import presentation, preview_inputs


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='studio-monitor-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.project = self.root / 'stories/fixture'
        shutil.copytree(ROOT / 'templates/story', self.project)
        self.part = self.project / 'parts/part_001'
        intake = read_json(self.project / 'creative/intake.json')
        intake.update(title='Synthetic monitor fixture', performance='narration')
        atomic_json(self.project / 'creative/intake.json', intake)
        self.monitor = Monitor([self.root], discover=False)
        self.info = self.monitor.projects()[0]

    def snapshot(self):
        return self.monitor.get(self.info['id'])

    def test_snapshot_and_http_polling_do_not_modify_story_records(self):
        before = {str(path): (path.stat().st_mtime_ns, path.read_bytes()) for path in self.project.rglob('*') if path.is_file()}
        self.monitor.overview()
        self.snapshot()
        self.snapshot()
        after = {str(path): (path.stat().st_mtime_ns, path.read_bytes()) for path in self.project.rglob('*') if path.is_file()}
        self.assertEqual(before, after)
        self.assertTrue(self.snapshot()['read_only'])

    def test_heartbeat_and_real_counter_are_distinct_from_completion(self):
        with Task(self.project, 'narration:part_001', interval=.04):
            advance(2, 8, 'clips', 'Actual synthetic clip count')
            time.sleep(.1)
            current = self.snapshot()['current']
            self.assertEqual(current['state'], 'running')
            self.assertEqual(current['completed'], 2)
            self.assertEqual(current['percent'], 25)
            self.assertLess(current['heartbeat_age_seconds'], 2)
        final = self.snapshot()
        self.assertEqual(next(x for x in final['jobs'] if x['id'] == 'narration:part_001')['state'], 'complete')
        self.assertEqual(final['assets']['deliveries'], 0)

    def test_stale_heartbeat_is_not_shown_as_running(self):
        past = (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat()
        atomic_json(location(self.project, 'render:part_001:preview'), {'job': 'render:part_001:preview',
                    'status': 'running', 'started_at': past, 'heartbeat_at': past})
        snapshot = self.snapshot()
        self.assertNotEqual(snapshot['state'], 'running')
        self.assertEqual(snapshot['jobs'][0]['state'], 'stale')
        self.assertTrue(any(item['kind'] == 'stale' for item in snapshot['attention']))

    def test_legacy_running_record_is_explicitly_unverified(self):
        atomic_json(self.project / 'production/status.json', {'jobs': {'mix:part_001': {'status': 'running',
                    'started_at': datetime.now(timezone.utc).isoformat()}}})
        snapshot = self.snapshot()
        self.assertEqual(snapshot['current']['state'], 'reported')
        self.assertNotEqual(snapshot['state'], 'running')
        self.assertTrue(snapshot['warnings'])
        self.assertFalse(snapshot['current']['eta']['available'])

    def test_partial_json_keeps_last_good_record_with_visible_warning(self):
        path = self.project / 'production/status.json'
        atomic_json(path, {'jobs': {'mix:part_001': {'status': 'complete'}}})
        self.snapshot()
        atomic_text(path, '{"jobs":')
        snapshot = self.snapshot()
        self.assertEqual(snapshot['jobs'][0]['state'], 'complete')
        self.assertTrue(any('unreadable' in value for value in snapshot['warnings']))

    def test_eta_uses_measured_units_and_does_not_invent_first_run_duration(self):
        base = {'id': 'mix:part_001', 'state': 'running', 'elapsed_seconds': 20}
        self.assertFalse(estimate(base, [])['available'])
        current = estimate(dict(base, completed=2, total=8), [])
        self.assertTrue(current['available'])
        self.assertLess(current['low_seconds'], 60)
        self.assertGreater(current['high_seconds'], 60)
        self.assertEqual(current['scope'], 'current operation')
        self.assertFalse(estimate(dict(base, state='stale', completed=2, total=8), [])['available'])

    def test_eta_ignores_cached_failed_samples_and_overdue_range(self):
        samples = [{'job': 'mix:part_001', 'seconds': 0, 'cache_hit': True},
                   {'job': 'mix:part_001', 'seconds': 50, 'error': 'synthetic failure'}]
        base = {'id': 'mix:part_001', 'state': 'running', 'elapsed_seconds': 5}
        self.assertFalse(estimate(base, samples)['available'])
        samples += [{'job': 'mix:part_001', 'seconds': 20}, {'job': 'mix:part_001', 'seconds': 24}]
        self.assertTrue(estimate(base, samples)['available'])
        self.assertFalse(estimate(dict(base, elapsed_seconds=100), samples)['available'])

    def test_remaining_pass_estimate_requires_evidence_for_every_step(self):
        planned = ['mix:part_001', 'render:part_001:preview']
        jobs = {identity: {'id': identity, 'state': 'pending', 'eta': {'available': False}} for identity in planned}
        samples = [{'job': identity, 'seconds': seconds} for identity in planned for seconds in (20, 25)]
        self.assertTrue(remaining_estimate(planned, jobs, samples, 'running')['available'])
        self.assertFalse(remaining_estimate(planned, jobs, samples[:2], 'running')['available'])
        self.assertFalse(remaining_estimate(planned, jobs, samples, 'waiting')['available'])
        self.assertFalse(remaining_estimate(planned, jobs, samples, 'running', missing_images=True)['available'])

    def test_completed_legacy_steps_are_counted_without_inventing_full_plan(self):
        atomic_json(self.project / 'production/status.json', {'jobs': {'mix:part_001': {'status': 'complete'}}})
        snapshot = self.snapshot()
        self.assertEqual(snapshot['steps']['done'], 1)
        self.assertIsNone(snapshot['steps']['total'])

    def test_corrupt_telemetry_and_write_failures_do_not_fail_production(self):
        atomic_json(self.project / 'production/progress/run.json', ['invalid record'])
        output = self.project / 'production/synthetic.txt'
        with patch('progress_records.atomic_json', side_effect=PermissionError('Synthetic telemetry-only write failure')):
            result = JobStore(self.project).run('timeline:part_001', [], {}, [output], lambda: atomic_text(output, 'actual synthetic output'))
        self.assertFalse(result['cached'])
        self.assertEqual(output.read_text(), 'actual synthetic output')

    def test_interrupted_task_is_not_marked_complete(self):
        with self.assertRaises(KeyboardInterrupt):
            with Task(self.project, 'mix:part_001'):
                raise KeyboardInterrupt()
        self.assertEqual(read_json(location(self.project, 'mix:part_001'))['status'], 'interrupted')

    def test_provider_request_is_waiting_without_fabricated_eta_or_secret_leak(self):
        atomic_json(self.project / 'production/speech-jobs/request.json', {'status': 'requesting',
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'recipe': {'headers': {'Authorization': 'SECRET-MUST-NOT-APPEAR'}, 'body': {'text': 'PRIVATE-SPOKEN-TEXT'}}})
        snapshot = self.snapshot()
        self.assertEqual(snapshot['current']['state'], 'provider_wait')
        self.assertFalse(snapshot['current']['eta']['available'])
        encoded = json.dumps(snapshot)
        self.assertNotIn('SECRET-MUST-NOT-APPEAR', encoded)
        self.assertNotIn('PRIVATE-SPOKEN-TEXT', encoded)

    def test_unknown_result_is_visible_and_does_not_trigger_any_provider(self):
        atomic_json(self.project / 'production/image-jobs/request.json', {'status': 'needs_attention'})
        with patch('subprocess.run', side_effect=AssertionError('No external command is needed')):
            snapshot = self.snapshot()
        self.assertTrue(any('reconciliation' in item['message'] for item in snapshot['attention']))

    def test_next_action_preserves_whether_user_or_agent_is_needed(self):
        atomic_json(self.project / 'production/last-run.json', {'parts': [{'next_actions': [
            {'actor': 'user', 'message': 'Actual fixture preview decision is pending'},
            {'actor': 'agent', 'message': 'Actual fixture image review is pending'}]}]})
        actors = {value['actor'] for value in self.snapshot()['attention']}
        self.assertEqual(actors, {'agent', 'user'})

    def test_manual_stage_note_has_no_liveness_or_approval_claim(self):
        before = (self.project / 'approvals.json').read_bytes()
        note(self.project, 'world', 'running', 'Preparing the actual fixture cast', 1, 3, 'characters')
        snapshot = self.snapshot()
        self.assertEqual(snapshot['current']['state'], 'reported')
        self.assertEqual(snapshot['current']['completed'], 1)
        self.assertEqual(snapshot['current']['total'], 3)
        self.assertEqual(snapshot['current']['unit'], 'characters')
        self.assertEqual((self.project / 'approvals.json').read_bytes(), before)
        with self.assertRaises(ValueError):
            note(self.project, 'world', 'running', 'Invalid count', -1, 3)

    def test_empty_or_unknown_project_does_not_become_a_fake_production(self):
        empty = Monitor([self.root / 'empty'], discover=False)
        self.assertEqual(empty.overview()['projects'], [])
        with self.assertRaises(KeyError):
            self.monitor.get('../../secrets')

    def test_current_plan_does_not_count_earlier_run_as_finished(self):
        atomic_json(self.project / 'production/progress/run.json', {'run_id': 'new-run', 'planned_jobs': ['mix:part_001', 'render:part_001:preview']})
        atomic_json(location(self.project, 'mix:part_001'), {'job': 'mix:part_001', 'status': 'complete', 'run_id': 'old-run'})
        snapshot = self.snapshot()
        self.assertEqual(snapshot['steps']['done'], 0)
        self.assertEqual(snapshot['steps']['total'], 2)
        self.assertEqual(next(x for x in snapshot['jobs'] if x['id'] == 'mix:part_001')['state'], 'pending')

    def test_job_failure_missing_output_and_cache_have_actual_events(self):
        store, output = JobStore(self.project), self.project / 'production/result.txt'
        with self.assertRaisesRegex(ValueError, 'without declared outputs'):
            store.run('timeline:part_001', [], {}, [output], lambda: None, max_attempts=1)
        self.assertEqual(read_json(location(self.project, 'timeline:part_001'))['status'], 'failed')
        store.run('timeline:part_001', [], {}, [output], lambda: atomic_text(output, 'synthetic output'))
        store.run('timeline:part_001', [], {}, [output], lambda: self.fail('Verified cache should be reused'))
        self.assertEqual(read_json(location(self.project, 'timeline:part_001'))['status'], 'cached')
        kinds = [item['kind'] for item in Reader().lines(self.project / 'production/progress/events.jsonl')]
        self.assertIn('failed', kinds)
        self.assertIn('cached', kinds)

    def test_child_process_can_report_actual_progress_to_parent_job(self):
        code = "import sys;sys.path.insert(0,sys.argv[1]);from progress_records import advance;advance(3,8,'clips','Synthetic child counter')"
        with Task(self.project, 'narration:part_001'):
            process([sys.executable, '-B', '-c', code, str(ROOT / 'tools')])
            self.assertEqual(read_json(location(self.project, 'narration:part_001'))['completed'], 3)

    @unittest.skipUnless(executable('ffmpeg'), 'Actual local FFmpeg required')
    def test_actual_ffmpeg_time_progress_and_output_are_preserved(self):
        output = self.project / 'production/synthetic.mp4'
        with Task(self.project, 'render:part_001:preview'):
            process([executable('ffmpeg'), '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=red:s=64x96:r=24',
                     '-t', '2', '-c:v', 'libx264', '-preset', 'ultrafast', str(output)], progress_seconds=2)
            record = read_json(location(self.project, 'render:part_001:preview'))
            self.assertGreater(record['completed'], 1)
            self.assertGreater(record['details']['frame'], 0)
        self.assertTrue(output.is_file())

    def test_api_is_local_read_only_and_rejects_arbitrary_paths_and_hosts(self):
        server = make_server(self.monitor, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_port}'
        with urlopen(base + '/api/projects') as response:
            payload = json.load(response)
            self.assertEqual(len(payload['projects']), 1)
            self.assertIsNone(response.headers.get('Access-Control-Allow-Origin'))
        for request, code in [(Request(base + '/api/status?project=../../outside'), 404),
                              (Request(base + '/../../story.md'), 404),
                              (Request(base + '/api/projects', headers={'Host': 'evil.example'}), 403),
                              (Request(base + '/api/projects', data=b'{}', method='POST'), 405)]:
            with self.assertRaises(HTTPError) as caught:
                urlopen(request)
            self.assertEqual(caught.exception.code, code)

    def test_history_combines_measured_work_with_new_telemetry_and_deduplicates_completion(self):
        path = self.project / 'production/logs/timings.jsonl'
        atomic_text(path, json.dumps({'job': 'mix:part_001', 'at': '2026-01-01T12:00:05Z', 'seconds': 5.25}) + '\n')
        atomic_text(self.project / 'production/progress/events.jsonl', '\n'.join(json.dumps(item) for item in [
            {'job': 'mix:part_001', 'at': '2026-01-01T12:00:00Z', 'kind': 'started', 'message': 'Mix started'},
            {'job': 'mix:part_001', 'at': '2026-01-01T12:00:05Z', 'kind': 'complete', 'message': 'Mix finished'},
            {'job': 'render:part_001:preview', 'at': '2026-01-01T12:00:06Z', 'kind': 'started', 'message': 'Encoding'}]))
        events = self.snapshot()['events']
        self.assertEqual(len([event for event in events if event['kind'] == 'complete']), 1)
        self.assertEqual(next(event for event in events if event['kind'] == 'complete')['duration_seconds'], 5.25)
        self.assertEqual(events[0]['message'], 'Encoding')
        self.assertEqual([event['id'] for event in events], [event['id'] for event in self.snapshot()['events']])

    def test_completed_production_clock_stops_at_recorded_current_delivery(self):
        self.media_fixture()
        atomic_json(self.project / 'creative/source.json', {'copied_at_utc': '2026-01-01T12:00:00Z'})
        atomic_json(self.project / 'production/preview-decisions.json', {'decisions': {'part_001': {
            'part_id': 'part_001', 'status': 'accepted', 'decision_quote': 'Synthetic acceptance',
            'decision_reference': 'test fixture', 'at': '2026-01-01T12:01:00Z', 'inputs': preview_inputs(self.project, 'part_001')}}})
        atomic_text(self.part / 'final.mp4', 'synthetic master')
        log = read_json(self.part / 'preview.render-log.json')
        log['output_sha256'] = sha256_file(self.part / 'final.mp4')
        atomic_json(self.part / 'final.render-log.json', log)
        atomic_json(self.project / 'delivery/part_001-r1/manifest.json', {'release_ready': True, 'revision': 'r1',
            'part_id': 'part_001', 'exported_at': '2026-01-01T12:02:00Z', 'files': {'parts/part_001/final.mp4': log['output_sha256']}})
        value = self.snapshot()
        self.assertEqual(value['production_clock']['elapsed_seconds'], 120)
        self.assertEqual(value['production_clock']['finished_at'], '2026-01-01T12:02:00Z')
        self.assertTrue(any(event['kind'] == 'delivery' and event['at'] == '2026-01-01T12:02:00Z' for event in value['events']))
        self.assertTrue(any(event['kind'] == 'decision' for event in value['events']))
        profile = read_json(self.project / 'audio/narrator.json')
        profile['cast']['NARRATOR']['voice'] = 'changed'
        atomic_json(self.project / 'audio/narrator.json', profile)
        self.assertIsNone(self.snapshot()['production_clock']['finished_at'])

    def test_character_display_name_uses_contained_canonical_heading(self):
        from monitor_media import character_name
        atomic_text(self.project / 'world/characters/CHAR-002.md', '# CHAR-002 — Dad\nActual canonical record')
        self.assertEqual(character_name(self.project, 'CHAR-002', {'canonical_file': 'world/characters/CHAR-002.md'}), 'Dad')
        self.assertEqual(character_name(self.project, 'CHAR-002', {'canonical_file': '../../outside.md'}), 'CHAR-002')

    def test_table_uses_measured_subsecond_duration_without_taking_a_later_cache_time(self):
        atomic_json(self.project / 'production/status.json', {'jobs': {'timeline:part_001': {
            'status': 'complete', 'started_at': '2026-01-01T12:00:00Z', 'finished_at': '2026-01-01T12:00:00Z'}}})
        atomic_text(self.project / 'production/logs/timings.jsonl', '\n'.join(json.dumps(item) for item in [
            {'job': 'timeline:part_001', 'at': '2026-01-01T12:00:00Z', 'seconds': .125, 'cache_hit': False},
            {'job': 'timeline:part_001', 'at': '2026-01-01T12:10:00Z', 'seconds': 0, 'cache_hit': True}]))
        self.assertEqual(self.snapshot()['jobs'][0]['elapsed_seconds'], .125)

    def test_react_build_assets_are_contained_and_missing_build_is_explicit(self):
        ui = self.root / 'synthetic-ui'
        atomic_text(ui / 'index.html', '<!doctype html><div id="root"></div>')
        atomic_text(ui / 'assets/index-fixture.js', '/* synthetic static build */')
        server = make_server(self.monitor, 0, ui_root=ui)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_port}'
        with urlopen(base + '/') as response:
            self.assertIn(b'id="root"', response.read())
        with urlopen(base + '/assets/index-fixture.js') as response:
            self.assertIn(b'synthetic', response.read())
            self.assertIn("script-src 'self'", response.headers['Content-Security-Policy'])
        for path in ('/assets/../index.html', '/assets/%2e%2e/package.json', '/assets/missing.js'):
            with self.assertRaises(HTTPError) as caught:
                urlopen(base + path)
            self.assertEqual(caught.exception.code, 404)
        (ui / 'index.html').unlink()
        with self.assertRaises(HTTPError) as caught:
            urlopen(base + '/')
        self.assertEqual(caught.exception.code, 503)
        with urlopen(base + '/api/projects') as response:
            self.assertEqual(response.status, 200)

    def media_fixture(self):
        """Synthetic bytes test provenance and routing, not playback/artistic quality."""
        profile = {'provider': 'kokoro', 'voice': 'old', 'cast': {'NARRATOR': {'voice': 'new'}}, 'speed': 1, 'language': 'en-us'}
        atomic_json(self.project / 'audio/narrator.json', profile)
        audio = self.part / 'audio/narration.wav'
        atomic_text(audio, 'synthetic speech bytes')
        atomic_text(self.part / 'audio/final_mix.wav', 'synthetic mixed bytes')
        atomic_text(self.part / 'images/shot.png', 'synthetic image bytes')
        atomic_text(self.part / 'preview.mp4', '0123456789abcdef')
        atomic_text(self.part / 'subtitles.srt', '1\n00:00:00,000 --> 00:00:01,000\nSynthetic line\n')
        atomic_json(self.part / 'speech.json', {'utterances': [{'id': 'UTT-1', 'speaker': 'NARRATOR', 'text': 'Synthetic line'}]})
        atomic_json(audio.with_suffix('.chunks.json'), {'audio_sha256': sha256_file(audio), 'provider': 'kokoro', 'chunks': [
            {'id': 'UTT-1', 'speaker': 'NARRATOR', 'voice': 'new', 'start': 0, 'end': 1, 'text': 'Synthetic line'}]})
        timeline = {'duration': 2, 'narration_file': 'audio/narration.wav', 'narration_start': .25, 'audio_file': 'audio/final_mix.wav',
                    'shots': [{'id': 'SHOT-1', 'start': 0, 'end': 2, 'image': 'images/shot.png'}],
                    'subtitles': [{'start': .25, 'end': 1.25, 'text': 'Synthetic line'}], 'audio_cues': []}
        atomic_json(self.part / 'timeline.json', timeline)
        atomic_json(self.part / 'preview.render-log.json', {'presentation_fingerprint': fingerprint(presentation(timeline)),
                    'output_sha256': sha256_file(self.part / 'preview.mp4'), 'audio_sha256': sha256_file(self.part / 'audio/final_mix.wav'),
                    'source_image_hashes': {str((self.part / 'images/shot.png').resolve()): sha256_file(self.part / 'images/shot.png')},
                    'subtitles_sha256': sha256_file(self.part / 'subtitles.srt')})
        atomic_json(self.part / 'audio/final_mix.mix-log.json', {'source_input_hashes': {str(audio): sha256_file(audio)}})
        atomic_json(self.project / 'audio/voice-decisions.json', {'changes': [{'id': 'VOICE-1', 'speaker': 'NARRATOR',
                    'previous': {'voice': 'old'}, 'selected': {'provider': 'kokoro', 'voice': 'new'},
                    'decision_quote': 'Actual synthetic request', 'decision_reference': 'test fixture', 'at': '2026-10-30T01:00:00Z'}]})

    def test_current_preview_uses_cast_override_and_real_measured_anchors(self):
        self.media_fixture()
        value = self.snapshot()
        media = value['media'][0]
        self.assertTrue(media['preview']['current'])
        self.assertFalse(media['preview']['approved'])
        self.assertEqual(media['preview']['review_state'], 'decision_needed')
        self.assertEqual(media['voices'][0]['voice'], 'new')
        self.assertTrue(media['voices'][0]['current'])
        self.assertEqual(media['speech'][0]['start'], .25)
        self.assertEqual(media['speech'][0]['end'], 1.25)
        self.assertEqual(media['voice_changes'][0]['state'], 'review_ready')
        self.assertEqual(value['current']['label'], 'Your preview decision')
        self.assertFalse((self.project / 'production/preview-decisions.json').exists())

    def test_approval_requires_current_exact_record_and_voice_changes_invalidate_readiness(self):
        self.media_fixture()
        decisions = {'decisions': {'part_001': {'status': 'accepted', 'decision_quote': 'Synthetic acceptance',
                     'decision_reference': 'test fixture', 'inputs': preview_inputs(self.project, 'part_001')}}}
        atomic_json(self.project / 'production/preview-decisions.json', decisions)
        self.assertTrue(self.snapshot()['media'][0]['preview']['approved'])
        profile = read_json(self.project / 'audio/narrator.json')
        profile['cast']['NARRATOR']['voice'] = 'third'
        atomic_json(self.project / 'audio/narrator.json', profile)
        media = self.snapshot()['media'][0]
        self.assertFalse(media['voices'][0]['current'])
        self.assertFalse(media['preview']['current'])
        self.assertFalse(media['preview']['approved'])
        self.assertEqual(read_json(self.project / 'production/preview-decisions.json'), decisions)

    def test_new_speech_requires_mix_and_preview_rebuild(self):
        self.media_fixture()
        audio = self.part / 'audio/narration.wav'
        atomic_text(audio, 'updated synthetic audio')
        chunks = read_json(audio.with_suffix('.chunks.json'))
        chunks['audio_sha256'] = sha256_file(audio)
        atomic_json(audio.with_suffix('.chunks.json'), chunks)
        media = self.snapshot()['media'][0]
        self.assertTrue(media['voices'][0]['current'])
        self.assertFalse(media['preview']['current'])
        self.assertEqual(media['voice_changes'][0]['state'], 'preview_pending')
        self.assertTrue(any('latest voice' in reason for reason in media['preview']['reasons']))

    def test_old_performance_fingerprint_is_pending_even_with_same_voice_id(self):
        self.media_fixture()
        path = self.part / 'audio/narration.chunks.json'
        chunks = read_json(path)
        chunks['speech_input_fingerprint'] = 'older-performance-settings'
        atomic_json(path, chunks)
        media = self.snapshot()['media'][0]
        self.assertFalse(media['voices'][0]['current'])
        self.assertFalse(media['preview']['current'])

    def test_monitor_checks_cached_performance_without_observer_models(self):
        from speech import input_fingerprint, plan_speech
        self.media_fixture()
        atomic_text(self.part / 'narration.txt', 'Synthetic line')
        profile = read_json(self.project / 'audio/narrator.json')
        with patch('speech_providers.ROOT', self.root / 'observer-without-models'):
            with self.assertRaisesRegex(ValueError, 'file is missing'):
                plan_speech(self.project, profile, 'Synthetic line', self.part / 'speech.json')
            turns = plan_speech(self.project, profile, 'Synthetic line', self.part / 'speech.json', require_runtime=False)
            path = self.part / 'audio/narration.chunks.json'
            chunks = read_json(path)
            chunks['speech_input_fingerprint'] = input_fingerprint(turns)
            atomic_json(path, chunks)
            self.assertTrue(self.snapshot()['media'][0]['preview']['current'])
            profile['speed'] = 1.1
            atomic_json(self.project / 'audio/narrator.json', profile)
            self.assertFalse(self.snapshot()['media'][0]['preview']['current'])

    def test_real_preview_decision_resolves_older_preview_waiting_note(self):
        self.media_fixture()
        atomic_json(self.project / 'production/progress/agent.json', {'stage': 'review', 'status': 'waiting',
                    'actor': 'user', 'message': 'Synthetic prior preview waiting note'})
        atomic_json(self.project / 'production/preview-decisions.json', {'decisions': {'part_001': {
            'status': 'accepted', 'decision_quote': 'Synthetic acceptance', 'decision_reference': 'test fixture',
            'inputs': preview_inputs(self.project, 'part_001')}}})
        self.assertFalse(any(item['message'] == 'Synthetic prior preview waiting note' for item in self.snapshot()['attention']))

    def test_old_creative_note_does_not_replace_newer_completed_operation(self):
        atomic_json(self.project / 'production/progress/agent.json', {'stage': 'world', 'status': 'running',
                    'at': '2026-01-01T00:00:00Z', 'message': 'Synthetic older creative note'})
        atomic_json(self.project / 'production/status.json', {'jobs': {'render:part_001:preview': {
                    'status': 'complete', 'finished_at': '2026-10-30T00:00:00Z'}}})
        self.assertNotEqual(self.snapshot()['current']['origin'] if 'origin' in self.snapshot()['current'] else None, 'agent-note')

    def test_changed_media_and_missing_captions_do_not_inherit_approval(self):
        self.media_fixture()
        atomic_text(self.part / 'images/shot.png', 'changed synthetic image')
        (self.part / 'subtitles.srt').unlink()
        media = self.snapshot()['media'][0]
        self.assertFalse(media['preview']['current'])
        self.assertTrue(any('shot images' in reason for reason in media['preview']['reasons']))
        self.assertTrue(any('subtitle file is missing' in reason for reason in media['preview']['reasons']))

    def test_master_exists_is_distinct_from_current_after_voice_revision(self):
        self.media_fixture()
        atomic_text(self.part / 'final.mp4', 'synthetic master')
        log = read_json(self.part / 'preview.render-log.json')
        log['output_sha256'] = sha256_file(self.part / 'final.mp4')
        atomic_json(self.part / 'final.render-log.json', log)
        self.assertTrue(self.snapshot()['media'][0]['master_current'])
        profile = read_json(self.project / 'audio/narrator.json')
        profile['cast']['NARRATOR']['voice'] = 'third'
        atomic_json(self.project / 'audio/narrator.json', profile)
        media = self.snapshot()['media'][0]
        self.assertTrue(media['master_exists'])
        self.assertFalse(media['master_current'])

    def test_media_range_head_version_and_path_boundaries(self):
        self.media_fixture()
        server = make_server(self.monitor, 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_port}'
        url = base + self.snapshot()['media'][0]['preview']['url']
        with urlopen(Request(url, headers={'Range': 'bytes=2-5'})) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), b'2345')
            self.assertEqual(response.headers['Content-Range'], 'bytes 2-5/16')
        with urlopen(Request(url, headers={'Range': 'bytes=-4'}, method='HEAD')) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers['Content-Length'], '4')
            self.assertEqual(response.read(), b'')
        for target, headers, expected in [(url, {'Range': 'bytes=999-'}, 416),
                (url + '&unused=../../approvals.json', {'Range': 'bytes=2-1'}, 416),
                (base + f'/api/media?project={self.info["id"]}&part=../../outside&kind=preview', {}, 404),
                (base + f'/api/media?project={self.info["id"]}&part=part_001&kind=../../approvals.json', {}, 404)]:
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(target, headers=headers))
            self.assertEqual(caught.exception.code, expected)
        atomic_text(self.part / 'preview.mp4', 'different synthetic revision')
        with self.assertRaises(HTTPError) as caught:
            urlopen(url)
        self.assertEqual(caught.exception.code, 409)


if __name__ == '__main__':
    unittest.main()
