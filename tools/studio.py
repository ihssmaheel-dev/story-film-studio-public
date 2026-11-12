#!/usr/bin/env python3
"""Small CLI coordinator for the existing approved, document-first studio workflow."""
import argparse
import json
from pathlib import Path
import shutil
import sys

from studio_common import (ROOT, JobStore, atomic_json, configuration, process, read_json,
                           hash_session, sha256_file)
from progress_records import observed_run, task
from production_session import coordinated


def invoke(script, *arguments):
    return process([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'tools' / script), *map(str, arguments)],
                   timeout=configuration()['jobs']['timeout_seconds'])


def prepare_sound(project, store):
    from audio_assets import generated_sound, register
    from setup_studio import download
    from project_records import artifact_path
    requirements = read_json(project / 'audio/requirements.json', {'requirements': []})['requirements']
    registry = read_json(project / 'audio/assets.json')
    for requirement in requirements:
        identity = requirement['asset_id']
        if identity in registry['assets']:
            continue
        route = requirement['route']
        if route == 'procedural':
            parameters = requirement['parameters']
            output = generated_sound(project / 'production/cache/generated-sounds', parameters)
            metadata = read_json(output.with_suffix('.wav.json'))
        elif route == 'provided':
            output = artifact_path(project, requirement['file'])
            metadata = requirement['source']
        elif route == 'sourced':
            from workflow import require_download
            output = artifact_path(project, 'production/cache/downloads/' + requirement['filename'])
            if output.parent != project / 'production/cache/downloads':
                raise ValueError('Download filename must be a plain filename')
            hosts = require_download(project, requirement['download_url'])
            download(requirement['download_url'], output, requirement.get('sha256'), allowed_hosts=hosts)
            metadata = requirement['source']
        else:
            raise ValueError(f'{identity}: unsupported acquisition route; execute the approved provider job and import its actual result')
        register(project, output, identity, requirement['kind'], metadata, requirement.get('tags', []))
        registry = read_json(project / 'audio/assets.json')


@hash_session()
@coordinated
@observed_run
def run_project(project, part_selection='all', profile='preview', stages=None, force=False):
    from align_audio import align_file
    from build_timeline import build
    from image_jobs import compile_request, queue_request
    from speech import SpeechSession
    from project_records import validate_continuity
    from workflow import policy, require_preview, require_stage
    from quality import check_part, comparison_sheet, image_review_context
    from production_inputs import mix_plan, asset_inputs, refresh_receipt
    from studio_common import executable
    from workflow import presentation
    project = Path(project).resolve()
    stages = set(stages or ('narration', 'alignment', 'timeline', 'sound', 'mix', 'subtitles', 'images', 'render', 'qa'))
    unknown = stages - {'narration', 'alignment', 'timeline', 'sound', 'mix', 'subtitles', 'images', 'render', 'qa'}
    if unknown:
        raise ValueError('Unknown stages: ' + ', '.join(sorted(unknown)))
    parts = sorted((project / 'parts').glob('part_*'))
    if part_selection != 'all':
        parts = [part for part in parts if part.name == part_selection]
    if not parts:
        raise ValueError('No matching planned part exists')
    for stage in sorted(stages):
        require_stage(project, stage, [part.name for part in parts])
    problems = validate_continuity(project, [part.name for part in parts])
    if problems:
        raise ValueError('; '.join(problems))
    store, session, results = JobStore(project), None, []
    narrator = read_json(project / 'audio/narrator.json')
    if 'sound' in stages:
        with task(project, 'sound'):
            prepare_sound(project, store)
    for part in parts:
        print(f'Checking {part.name}...', flush=True)
        timeline_path = part / 'timeline.json'
        timeline = read_json(timeline_path)
        narration_path = (part / timeline['narration_file']) if timeline.get('narration_file') else None
        manual_timing = read_json(part / 'shots.json').get('timing_mode') == 'manual'
        if narration_path and 'narration' in stages:
            if session is None:
                session = SpeechSession(project, narrator)
            text_path = part / 'narration.txt'
            speech_path = part / 'speech.json'
            text = text_path.read_text(encoding='utf-8-sig')
            from speech import plan_speech, input_fingerprint
            turns = plan_speech(project, narrator, text, speech_path)
            speech_inputs = [text_path, project / 'audio/narrator.json', ROOT / 'tools/narration.py',
                             ROOT / 'tools/speech.py', ROOT / 'tools/speech_providers.py', ROOT / 'tools/provider_budget.py']
            if speech_path.is_file():
                speech_inputs.append(speech_path)
            speech_inputs.extend(project / name for turn in turns for name in turn['source_hashes'])
            previous_chunks = read_json(narration_path.with_suffix('.chunks.json'), {}).get('chunks', [])
            clips_intact = all((narration_path.parent / item['file']).is_file() and
                               sha256_file(narration_path.parent / item['file']) == item.get('sha256')
                               for item in previous_chunks)
            outputs = [narration_path, narration_path.with_suffix('.chunks.json')]
            reused = None
            if not force and clips_intact:
                reused = store.reuse('narration:' + part.name, speech_inputs, outputs,
                                     lambda value: value.get('turns') == turns and
                                     value.get('input_fingerprint') == input_fingerprint(turns))
            if reused is None:
                if 'alignment' in stages and not manual_timing:
                    from align_audio import validate_alignment_text
                    validate_alignment_text(turns, narrator)
                with task(project, 'voice_setup:' + part.name):
                    prepared = session.prepare(text, speech_path)
                store.run('narration:' + part.name, speech_inputs, prepared, outputs,
                          lambda: session.render(text, narration_path, prepared=prepared, script=speech_path, part_id=part.name),
                          force=force or not clips_intact)
        if narration_path and 'alignment' in stages and not manual_timing:
            alignment_path = narration_path.with_suffix('.alignment.json')
            store.run('alignment:' + part.name,
                      [narration_path, narration_path.with_suffix('.chunks.json'), project / 'audio/narrator.json', ROOT / 'tools/align_audio.py'],
                      {}, [alignment_path], lambda: atomic_json(alignment_path, align_file(narration_path, profile=narrator)), force=force)
        if narration_path and 'timeline' in stages and not manual_timing:
            timeline_inputs = [part / 'shots.json', narration_path.with_suffix('.alignment.json'),
                               project / 'creative/intake.json', ROOT / 'tools/build_timeline.py']
            if narration_path.with_suffix('.alignment-review.json').is_file():
                timeline_inputs.append(narration_path.with_suffix('.alignment-review.json'))
            store.run('timeline:' + part.name,
                      timeline_inputs,
                      {}, [timeline_path], lambda: build(project, part.name), force=force)
            timeline = read_json(timeline_path)
        waiting, missing_images = [], []
        if 'images' in stages:
            missing_images = [shot for shot in timeline['shots'] if not (part / shot['image']).is_file()]
            if missing_images:
                price = configuration(project)['image_provider'].get('estimated_cost_per_image')
                from image_jobs import builtin_scope
                if price is None and not builtin_scope(project):
                    waiting.append('Set/review the actual image price estimate in production/settings.json before queueing calls')
                else:
                    # Preserve one-image-at-a-time production and immediate visual review.
                    first = missing_images[0]
                    request = compile_request(project, part.name, first['id'], price,
                                              configuration(project)['image_provider'].get('currency', 'USD'))
                    path, _ = queue_request(project, request)
                    waiting.append('Execute and inspect the approved image request: ' + str(path))
        registry_path = (part / timeline.get('audio_manifest', '../../audio/assets.json')).resolve()
        assets = read_json(registry_path)['assets']
        used = {cue['asset_id']: assets.get(cue['asset_id']) for cue in timeline.get('audio_cues', [])}
        from listening import problems as listening_problems
        draft_preview = profile == 'preview' and policy(project)['mode'] == 'fast'
        unavailable = listening_problems(project, part.name, allow_pending=draft_preview)
        if unavailable:
            waiting.append('Acquire/verify/listen to audio assets: ' + '; '.join(unavailable))
        elif 'mix' in stages:
            inputs = [ROOT / 'tools/mix_audio.py', ROOT / 'tools/audio_check.py', ROOT / 'tools/studio_common.py']
            inputs.extend(path for name in ('ffmpeg', 'ffprobe') if (path := executable(name)))
            if narration_path:
                inputs.append(narration_path)
            inputs.extend(registry_path.parent / asset['file'] for asset in used.values())
            mix = part / timeline['audio_file']
            store.run('mix:' + part.name, inputs, {'profile': 'final', 'assets': asset_inputs(used),
                      'plan': mix_plan(timeline), 'settings': configuration(project)['mix']},
                      [mix, mix.with_suffix('.mix-log.json')],
                      lambda: invoke('mix_audio.py', timeline_path, '--profile', 'final',
                                     *(['--draft-preview'] if draft_preview else [])), force=force,
                      refresh_cached=lambda: refresh_receipt(mix.with_suffix('.mix-log.json'), timeline_path,
                                                            registry_path if used else None))
        if 'subtitles' in stages and read_json(project / 'creative/intake.json').get('subtitles') is not False:
            store.run('subtitles:' + part.name, [ROOT / 'tools/make_srt.py'],
                      {'subtitles': timeline.get('subtitles', [])}, [part / 'subtitles.srt'],
                      lambda: invoke('make_srt.py', timeline_path), force=force)
        reviews = read_json(project / 'production/image-reviews.json', {'reviews': {}})['reviews']
        if profile == 'final':
            if policy(project)['mode'] == 'fast':
                try:
                    require_preview(project, part.name)
                except (ValueError, OSError) as error:
                    waiting.append(str(error))
            from align_audio import reviewed_alignment
            actual_alignment = reviewed_alignment(narration_path) if narration_path else timeline.get('alignment', {})
            unresolved = [item for item in actual_alignment.get('uncertain_ranges', []) if not item.get('reviewed')]
            if actual_alignment.get('review_warning'):
                waiting.append(actual_alignment['review_warning'])
            if unresolved:
                waiting.append('Inspect the flagged alignment ranges and record the manual review before the master render')
            for shot in timeline['shots']:
                image = part / shot['image']
                review = reviews.get(part.name + '/' + shot['id'], {})
                written = next(item for item in read_json(part / 'shots.json')['shots'] if item['id'] == shot['id'])
                if image.is_file() and (review.get('verdict') != 'passed' or review.get('sha256') != sha256_file(image)
                                      or review.get('context') != image_review_context(project, part.name, written)):
                    waiting.append(f'{shot["id"]}: visual/reference comparison review is required before the master render')
        if missing_images:
            comparison_sheet(timeline_path, project / 'production/review' / (part.name + '-contact-sheet.jpg'))
        output = part / ('preview.mp4' if profile == 'preview' else 'final.mp4')
        if not waiting and 'render' in stages:
            inputs = [part / timeline['audio_file'], ROOT / 'tools/render_part.py', ROOT / 'tools/audio_check.py',
                      ROOT / 'tools/camera_motion.py', ROOT / 'tools/validate_timeline.py',
                      ROOT / 'tools/studio_common.py']
            inputs.extend(path for name in ('ffmpeg', 'ffprobe') if (path := executable(name)))
            inputs.extend(part / shot['image'] for shot in timeline['shots'])
            subtitle_options = []
            if read_json(project / 'creative/intake.json').get('subtitles') == 'burn-in':
                inputs.append(part / 'subtitles.srt')
                subtitle_options = ['--srt', part / 'subtitles.srt']
            store.run('render:' + part.name + ':' + profile, inputs, {'profile': profile,
                      'presentation': presentation(timeline), 'settings': configuration(project)['render_profiles'][profile],
                      'burn_subtitles': bool(subtitle_options)},
                      [output, output.with_suffix('.render-log.json')],
                      lambda: invoke('render_part.py', timeline_path, '--output', output, '--profile', profile, *subtitle_options), force=force,
                      refresh_cached=lambda: refresh_receipt(output.with_suffix('.render-log.json'), timeline_path, rendered=True))
        render_log = read_json(output.with_suffix('.render-log.json'), {})
        current_video = (output.is_file() and render_log.get('timeline_sha256') == sha256_file(timeline_path)
                         and render_log.get('output_sha256') == sha256_file(output))
        if 'qa' in stages and not missing_images and (part / timeline['audio_file']).is_file():
            report_path = part / (profile + '-technical-qa.json')
            with task(project, 'qa:' + part.name):
                report = check_part(timeline_path, output if current_video else None)
                report['comparison_sheets'] = comparison_sheet(timeline_path, project / 'production/review' / (part.name + '-contact-sheet.jpg'))
                atomic_json(report_path, report)
            waiting.extend(report['technical_errors'])
        results.append({'part': part.name, 'profile': profile, 'output': str(output) if current_video else None,
                        'waiting_for': waiting,
                        'next_actions': [{'actor': 'user' if ('preview decision' in message or 'present the preview' in message) else 'agent',
                                          'message': message} for message in waiting],
                        'release_ready': False})
        print(f'{part.name}: ' + ('review/action required' if waiting else 'local stages complete; final playback review pending'), flush=True)
    atomic_json(project / 'production/last-run.json', {'parts': results})
    return results


def add_part(project, identity):
    import re
    project = Path(project).resolve()
    from story_git import require_story_branch
    require_story_branch(project)
    if not re.fullmatch(r'part_\d{3,}', identity):
        raise ValueError('Use part_### naming')
    if read_json(project / 'creative/intake.json', {}).get('mode') == 'single':
        raise ValueError('A single video uses only part_001; configure parts delivery before adding another part')
    target = project / 'parts' / identity
    if target.exists():
        raise ValueError('Part already exists; no files were overwritten')
    shutil.copytree(ROOT / 'templates/story/parts/part_001', target)
    for name in ('part.json', 'shots.json', 'timeline.json'):
        data = read_json(target / name)
        data['part_id'] = identity
        atomic_json(target / name, data)
    from project_records import approval_status
    approval_status(project, refresh=True)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    doctor = sub.add_parser('doctor')
    doctor.add_argument('--project', type=Path)
    sub.add_parser('setup')
    sub.add_parser('sample')
    sub.add_parser('providers', help='List speech providers and credential presence without making API calls')
    prepare = sub.add_parser('prepare', help='Apply authored production records in one validated batch')
    prepare.add_argument('project', type=Path)
    source = prepare.add_mutually_exclusive_group(required=True)
    source.add_argument('--snapshot', action='store_true', help='Print a source-bound base for an authored bundle')
    source.add_argument('--file', type=Path)
    prepare.add_argument('--check', action='store_true', help='Check source/base/paths/text without applying the batch')
    for name in ('next', 'continue'):
        step = sub.add_parser(name, help='Inspect the next work packet' if name == 'next' else 'Resume local production until actual inspection/decision')
        step.add_argument('project', type=Path)
        step.add_argument('--part', default='auto')
    for action in ('status', 'progress'):
        command = sub.add_parser(action, add_help=False)
        command.add_argument('-h', '--help', action='store_true', dest='monitor_help')
        command.add_argument('arguments', nargs=argparse.REMAINDER)
    monitor_command = sub.add_parser('monitor', help='Open a read-only local production monitor')
    monitor_command.add_argument('--workspace', type=Path, action='append', default=[])
    monitor_command.add_argument('--port', type=int, default=8765)
    monitor_command.add_argument('--no-discover', action='store_true')
    speech_command = sub.add_parser('speech', add_help=False)
    speech_command.add_argument('-h', '--help', action='store_true', dest='speech_help')
    speech_command.add_argument('arguments', nargs=argparse.REMAINDER)
    images_command = sub.add_parser('images', add_help=False)
    images_command.add_argument('-h', '--help', action='store_true', dest='images_help')
    images_command.add_argument('arguments', nargs=argparse.REMAINDER)
    voices = sub.add_parser('voice', add_help=False)
    voices.add_argument('-h', '--help', action='store_true', dest='voice_help')
    voices.add_argument('arguments', nargs=argparse.REMAINDER)
    cast_command = sub.add_parser('cast', add_help=False)
    cast_command.add_argument('-h', '--help', action='store_true', dest='cast_help')
    cast_command.add_argument('arguments', nargs=argparse.REMAINDER)
    resolution = sub.add_parser('speech-resolve', help='Reconcile a known provider result without making a generation request')
    resolution.add_argument('project', type=Path)
    resolution.add_argument('--request-id', required=True)
    resolution.add_argument('--outcome', choices=('failed', 'received'), required=True)
    resolution.add_argument('--actual-cost', required=True, type=float)
    resolution.add_argument('--evidence', required=True)
    resolution.add_argument('--audio', type=Path)
    init = sub.add_parser('init', add_help=False)
    init.add_argument('-h', '--help', action='store_true', dest='init_help')
    init.add_argument('arguments', nargs=argparse.REMAINDER)
    resume = sub.add_parser('resume', help='Switch to an existing story branch without creating another project')
    resume.add_argument('project', type=Path)
    for action in ('configure', 'authorize', 'approve-preview', 'record-revision', 'preset'):
        command = sub.add_parser(action, add_help=False)
        command.add_argument('arguments', nargs=argparse.REMAINDER)
    run = sub.add_parser('run')
    run.add_argument('project', type=Path)
    run.add_argument('--part', default='all')
    run.add_argument('--profile', choices=('preview', 'final'), default='preview')
    run.add_argument('--stages', help='Comma-separated local stages; omitted means all')
    run.add_argument('--force', action='store_true')
    preflight = sub.add_parser('preflight', help='Check runtime/provider/dictionary readiness without generating media')
    preflight.add_argument('project', type=Path)
    preflight.add_argument('--part', default='all')
    preflight.add_argument('--live-local', action='store_true', help='Read actual loopback Chatterbox model metadata; no synthesis')
    review = sub.add_parser('review')
    review.add_argument('project', type=Path)
    add = sub.add_parser('add-part')
    add.add_argument('project', type=Path)
    add.add_argument('identity')
    images = sub.add_parser('image-review')
    images.add_argument('project', type=Path)
    images.add_argument('--part', required=True)
    images.add_argument('--shot', required=True)
    images.add_argument('--verdict', choices=('passed', 'failed'), required=True)
    images.add_argument('--reviewer', required=True)
    images.add_argument('--notes', required=True)
    playback = sub.add_parser('playback-review')
    playback.add_argument('project', type=Path)
    playback.add_argument('--part', required=True)
    playback.add_argument('--reviewer', required=True)
    playback.add_argument('--notes', required=True)
    playback.add_argument('--accept-warnings', action='store_true')
    export = sub.add_parser('export')
    export.add_argument('project', type=Path)
    export.add_argument('--part', required=True)
    export.add_argument('--revision', required=True)
    args = parser.parse_args()
    try:
        if getattr(args, 'project', None) and args.action not in ('doctor', 'resume', 'next'):
            from story_git import require_story_branch
            require_story_branch(args.project)
        if args.action == 'providers':
            from speech_providers import catalog
            print(json.dumps(catalog(), indent=2))
        elif args.action == 'prepare':
            from production_plan import snapshot, apply
            print(json.dumps(snapshot(args.project) if args.snapshot else apply(args.project, read_json(args.file), args.check), indent=2))
        elif args.action in ('next', 'continue'):
            from production_next import next_work, continue_project
            print(json.dumps((next_work if args.action == 'next' else continue_project)(args.project, args.part), indent=2))
        elif args.action in ('monitor', 'status', 'progress'):
            from monitor import main as monitor_main
            previous = sys.argv
            forwarded = getattr(args, 'arguments', [])
            if args.action == 'monitor':
                forwarded = ['--port', str(args.port)]
                for workspace in args.workspace:
                    forwarded.extend(['--workspace', str(workspace)])
                if args.no_discover:
                    forwarded.append('--no-discover')
            sys.argv = ['monitor.py', 'serve' if args.action == 'monitor' else args.action,
                        *(['--help'] if getattr(args, 'monitor_help', False) else forwarded)]
            try:
                monitor_main()
            finally:
                sys.argv = previous
        elif args.action == 'voice':
            print(invoke('voice_cast.py', *(['--help'] if args.voice_help else args.arguments)).stdout)
        elif args.action == 'cast':
            print(invoke('cast.py', *(['--help'] if args.cast_help else args.arguments)).stdout)
        elif args.action == 'resume':
            from story_git import resume_story
            print(resume_story(ROOT, args.project))
        elif args.action == 'speech':
            print(invoke('tts.py', *(['--help'] if args.speech_help else args.arguments)).stdout)
        elif args.action == 'images':
            print(invoke('image_jobs.py', *(['--help'] if args.images_help else args.arguments)).stdout)
        elif args.action == 'speech-resolve':
            from provider_budget import reconcile_speech
            print(reconcile_speech(args.project, args.request_id, args.outcome, args.actual_cost, args.evidence, args.audio))
        elif args.action in ('configure', 'authorize', 'approve-preview', 'record-revision', 'preset'):
            print(invoke('workflow.py', args.action, *args.arguments).stdout)
        elif args.action in ('doctor', 'setup', 'init'):
            script = {'doctor': 'check_env.py', 'setup': 'setup_studio.py', 'init': 'init_story.py'}[args.action]
            arguments = (['--help'] if args.action == 'init' and args.init_help else
                         ['--project', args.project] if args.action == 'doctor' and args.project else getattr(args, 'arguments', []))
            print(invoke(script, *arguments).stdout)
        elif args.action == 'run':
            print(json.dumps(run_project(args.project, args.part, args.profile,
                                         args.stages.split(',') if args.stages else None, args.force), indent=2))
        elif args.action == 'preflight':
            from preflight import inspect
            status = inspect(args.project, args.part, args.live_local)
            print(json.dumps(status, indent=2))
            if not status['ready']:
                raise SystemExit(1)
        elif args.action == 'review':
            print(invoke('review_pack.py', args.project).stdout)
        elif args.action == 'sample':
            from technical_sample import run
            run()
        elif args.action == 'image-review':
            from quality import record_image_review
            record_image_review(args.project, args.part, args.shot, args.verdict, args.notes, args.reviewer)
            print('Recorded inspection against the current image and canonical inputs')
        elif args.action == 'playback-review':
            from delivery import record_playback
            print(record_playback(args.project, args.part, args.reviewer, args.notes, args.accept_warnings))
        elif args.action == 'export':
            from delivery import export_part
            print(export_part(args.project, args.part, args.revision))
        else:
            print(add_part(args.project, args.identity))
    except (ValueError, OSError, RuntimeError, KeyError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
