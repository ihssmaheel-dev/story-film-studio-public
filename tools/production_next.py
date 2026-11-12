"""Compact resumable work packets. Execute local jobs; leave real decisions/inspection real."""
from collections import Counter
from pathlib import Path
import re

from part_continuity import handoff, problems as part_problems
from project_records import artifact_path, validate_continuity
from studio_common import fingerprint, hash_session, read_json, sha256_file


def command(project, action, *args):
    return ['python', 'tools/studio.py', action, str(project), *args]


def media_state(project, part):
    """Cheap, offline currency checks; do not start a provider for an existing film."""
    from speech import current_problems
    from workflow import preview_inputs, require_preview
    timeline = read_json(part / 'timeline.json', {})
    result = {'preview_current': False, 'preview_accepted': False, 'master_current': False, 'delivered': False}
    if timeline.get('narration_file') and current_problems(project, [part], require_runtime=False):
        return result
    try:
        mix = read_json((part / timeline['audio_file']).with_suffix('.mix-log.json'))
        if mix.get('output_sha256') != sha256_file(part / timeline['audio_file']):
            return result
        for name, digest in mix.get('source_input_hashes', {}).items():
            if sha256_file(name) != digest:
                return result
        preview_inputs(project, part.name)
        result['preview_current'] = True
        try:
            require_preview(project, part.name)
            result['preview_accepted'] = True
        except ValueError:
            pass
        preview = read_json(part / 'preview.render-log.json')
        master = read_json(part / 'final.render-log.json', {})
        result['master_current'] = (result['preview_accepted'] and (part / 'final.mp4').is_file()
                                    and master.get('output_sha256') == sha256_file(part / 'final.mp4')
                                    and all(master.get(k) == preview.get(k) for k in
                                            ('presentation_fingerprint', 'audio_sha256', 'source_image_hashes', 'subtitles_sha256')))
        if result['master_current']:
            from workflow import image_problems
            if image_problems(project, [part.name]):
                return result
            written = read_json(part / 'shots.json')['shots']
            visible = {identity for shot in written for identity in
                       [shot.get('style_id'), shot.get('location_id'), *shot.get('character_ids', []), *shot.get('prop_ids', [])] if identity}
            registry = read_json(project / 'continuity/entities.json')
            bindings = [part / 'shots.json']
            for group in ('styles', 'characters', 'locations', 'props'):
                for identity, record in registry.get(group, {}).items():
                    if identity in visible:
                        bindings.append(artifact_path(project, record['canonical_file']))
                        bindings.extend(artifact_path(project, name) for name in record.get('reference_paths', []))
            for path in (project / 'delivery').glob(part.name + '-*/manifest.json'):
                manifest = read_json(path)
                if (manifest.get('release_ready') is True and manifest.get('part_id') == part.name
                        and manifest.get('files', {}).get(f'parts/{part.name}/final.mp4') == master['output_sha256']
                        and all(manifest.get('files', {}).get(p.relative_to(project).as_posix()) == sha256_file(p) for p in bindings)):
                    result['delivered'] = True
                    result['delivery'] = str(path.parent)
                    break
    except (OSError, ValueError, KeyError):
        pass
    return result


def action(kind, actor, message, **fields):
    return {'kind': kind, 'actor': actor, 'message': message, **fields}


@hash_session()
def next_work(project, part_selection='auto'):
    from workflow import (policy, questions, delegation_status, audit_problems, written_problems,
                          master_problems, delivery_outputs)
    project = Path(project).resolve()
    if part_selection != 'auto' and not re.fullmatch(r'part_[0-9]{3}', part_selection):
        raise ValueError('Choose auto or a canonical part_### ID')
    packet = {'schema_version': 1, 'project': str(project), 'part': None, 'actions': [], 'advisories': [],
              'scope': 'Current source/canonical records only. No invented progress, approvals or provider results.'}
    def finish(*items):
        packet['actions'] = list(items)
        return packet
    value = policy(project)
    missing = questions(project, include_authorization=False)
    if missing:
        return finish(action('configuration', 'user', 'Bundle only the material missing choices', questions=missing))
    if value['mode'] == 'fast':
        status, _ = delegation_status(project)
        if status != 'authorized':
            return finish(action('authorization', 'user', 'Record the actual configuration decision for this scope', status=status))
    else:
        from project_records import approval_status
        from project_records import GATES
        log, stale = approval_status(project)
        pending = [key for key in GATES if log.get('gates', {}).get(key, {}).get('status') != 'approved' or key in stale]
        if pending:
            return finish(action('strict_workflow', 'agent', 'Follow the existing Strict sequence: finish each current report before presenting its exact gate/revision decision',
                                 gates=pending, context=['docs/01-workflow-and-approvals.md']))
    audit = audit_problems(project)
    if audit:
        return finish(action('story_review', 'agent', 'Finish the source review/permitted revision once', problems=audit,
                             context=['creative/original.md', 'creative/audit-issues.json', 'continuity/story-ledger.json']))
    if value['task'] != 'film':
        return finish(action('written_delivery', 'agent', 'Complete the configured written deliverable; no film production is configured'))
    boundaries = part_problems(project)
    if boundaries:
        return finish(action('part_plan', 'agent', 'Repair the actual part boundary/handoff records', problems=boundaries))
    if read_json(project / 'creative/intake.json').get('mode') == 'parts' and not (project / 'creative/part-plan.json').is_file():
        return finish(action('part_plan', 'agent', 'Write the complete structured part boundaries, hooks, endings and inherited state first',
                             template='templates/part-plan.example.json'))
    parts = sorted(p for p in (project / 'parts').glob('part_*') if p.is_dir())
    if not parts:
        return finish(action('part_plan', 'agent', 'Create the actual planned part folders'))
    states = {part.name: media_state(project, part) for part in parts}
    if part_selection == 'auto':
        part = next((p for p in parts if not states[p.name]['delivered']), None)
        if part is None:
            if 'one continuous full-length video' in delivery_outputs(project):
                return finish(action('continuous_edition', 'agent', 'Assemble and inspect the included continuous full-film cut using the measured edit plan',
                                     context=['creative/continuous-edit.md'], parts=[states[p.name]['delivery'] for p in parts]))
            return finish(action('complete', 'none', 'All configured part deliveries are present and current',
                                 deliveries=[states[p.name]['delivery'] for p in parts]))
    else:
        part = next((p for p in parts if p.name == part_selection), None)
        if part is None:
            raise ValueError('The selected planned part does not exist')
    packet.update(part=part.name, media=states[part.name], handoff=handoff(project, part.name))
    from shot_planning import GUIDE as shot_guide, summary as image_plan_summary
    packet['image_plan'] = image_plan_summary(project, part)
    from image_jobs import unresolved_outcome
    outstanding = [str(path) for folder in ('image-jobs', 'speech-jobs')
                   for path in (project / 'production' / folder).glob('*.json')
                   if unresolved_outcome(read_json(path))]
    if outstanding:
        return finish(action('reconcile_provider', 'agent', 'Reconcile actual pending/unknown provider outcomes before another request or design revision', requests=outstanding))
    from cast import plan_problems as cast_plan_problems, pending_requests, sheet_problems, visible_cast
    changes = pending_requests(project)
    if changes:
        return finish(action('cast_change', 'agent', 'Apply the actual requested character revision, preserving earlier designs and checking affected shots',
                             requests=changes, context=['docs/18-cast-sheets.md', 'world/cast.json']))
    inventory = read_json(project / 'continuity/dependencies.json', {})
    if inventory.get('review_status') != 'complete':
        return finish(action('inventory', 'agent', 'Finish the whole-story entity and dependency inventory before images'))
    written = written_problems(project, [part.name])
    if written:
        return finish(action('shot_plan', 'agent', 'Analyse story beats and batch the selected part’s purposeful shots, image-count rationale and spoken turns',
                             problems=written, context=[shot_guide, 'templates/image-planning.example.json', 'docs/18-cast-sheets.md']))
    continuity = validate_continuity(project, [part.name])
    if continuity:
        return finish(action('continuity', 'agent', 'Resolve actual canonical/state contradictions', problems=continuity))
    cast_plan = cast_plan_problems(project)
    if cast_plan:
        return finish(action('cast_plan', 'agent', 'Author complete role-specific cast profiles, useful views, expressions and poses',
                             problems=cast_plan, context=['docs/18-cast-sheets.md', 'templates/cast-profile.example.json']))
    from preflight import inputs as preflight_inputs
    readiness = read_json(project / 'production/preflight.json', {})
    if readiness.get('inputs') != preflight_inputs(project, part.name) or not readiness.get('ready'):
        return finish(action('preflight', 'agent', 'Check runtime/dictionary readiness before reference or final-image work',
                             command=command(project, 'continue', '--part', part.name)))
    if read_json(project / 'creative/intake.json').get('performance') != 'none':
        from speech_providers import voice_config
        profile = read_json(project / 'audio/narrator.json')
        roles = read_json(project / 'audio/voice-plan.json', {}).get('roles', {})
        speakers = list(dict.fromkeys(item.get('speaker', 'NARRATOR') for item in
                                     read_json(part / 'speech.json', {}).get('utterances', []))) or ['NARRATOR']
        pending = []
        for speaker in speakers:
            config, role = voice_config(profile, speaker), roles.get(speaker, {})
            selected = role.get('selected', {})
            matches = all(selected.get(key) == config[key] for key in ('provider', 'model', 'voice'))
            samples = [role['sample']] if isinstance(role.get('sample'), dict) else role.get('candidates', [])
            sample_exists = any(isinstance(item, dict) and item.get('file') and item.get('sha256')
                                and all(item.get(key) == config[key] for key in ('provider', 'model', 'voice'))
                                and artifact_path(project, item['file']).is_file()
                                and sha256_file(artifact_path(project, item['file'])) == item['sha256'] for item in samples)
            if not role.get('performance_brief') or not matches or not sample_exists:
                pending.append({'speaker': speaker, 'selected': config,
                                'needs': ['story-specific performance brief', 'matching current selection', 'real hashed role sample; reuse a suitable existing audition']})
        if pending:
            return finish(action('casting', 'agent', 'Prepare/check representative role samples before full speech or final images; keep listening provisional when unavailable',
                                 roles=pending, context=['audio/voice-plan.json', 'instructions/voice-casting.md']))
    registry = read_json(project / 'continuity/entities.json')
    appearances = Counter()
    for folder in parts:
        for shot in read_json(folder / 'shots.json', {}).get('shots', []):
            appearances.update(set(shot.get('character_ids', [])))
    selected = read_json(part / 'shots.json')['shots']
    ids = list(dict.fromkeys([s.get('style_id') for s in selected] +
                            [identity for s in selected for identity in s.get('character_ids', []) if appearances[identity] > 1]))
    records = {key: item for group in ('styles', 'characters') for key, item in registry.get(group, {}).items()}
    for identity in filter(None, ids):
        record = records[identity]
        if not record.get('reference_paths'):
            from image_jobs import builtin_scope
            from studio_common import configuration
            if configuration(project)['image_provider'].get('estimated_cost_per_image') is None and not builtin_scope(project):
                return finish(action('image_cost_scope', 'user', 'Choose a known reference-image price inside the budget, or explicitly accept unreported charges with a finite built-in call cap'))
            return finish(action('reference', 'agent', 'Establish the shared style/recurring cast reference before final shots', entity=identity,
                                 command=command(project, 'images', 'reference', '--entity', identity)))
    for identity in visible_cast(project, [part.name]):
        record = records[identity]
        if not record.get('reference_paths'):
            return finish(action('reference', 'agent', 'Create the requested identity, expression and pose sheet for this character', entity=identity,
                                 command=command(project, 'images', 'reference', '--entity', identity), context=['docs/18-cast-sheets.md']))
        problems = sheet_problems(project, identity)
        if problems:
            return finish(action('cast_review', 'agent', 'Inspect the actual cast-sheet pixels and record coverage before story images',
                                 character=identity, problems=problems, context=['docs/18-cast-sheets.md']))
    timeline = read_json(part / 'timeline.json')
    missing_images = [shot for shot in timeline.get('shots', []) if not artifact_path(project, f'parts/{part.name}/' + shot['image']).is_file()]
    # Do the measured local preparation once. Repeated image imports don't restart speech/mixing.
    audio = part / timeline.get('audio_file', 'audio/final_mix.wav')
    speech_stale = False
    if timeline.get('narration_file'):
        from preflight import speech_cached
        speech_stale = not speech_cached(project, part)
    if not audio.is_file() or speech_stale or not timeline.get('shots'):
        return finish(action('run_preview', 'agent', 'Preflight and execute the reusable local stages together',
                             command=command(project, 'continue', '--part', part.name)))
    if missing_images:
        from image_jobs import builtin_scope
        from studio_common import configuration
        if configuration(project)['image_provider'].get('estimated_cost_per_image') is None and not builtin_scope(project):
            return finish(action('image_cost_scope', 'user', 'Choose a known image price inside the budget, or explicitly accept unreported charges with a finite built-in call cap'))
        shot = missing_images[0]
        return finish(action('image', 'agent', 'Execute the next actual image request, inspect and resume', shot=shot['id'],
                             command=command(project, 'continue', '--part', part.name)))
    if not states[part.name]['preview_current']:
        return finish(action('run_preview', 'agent', 'Build/check the complete current preview, reusing verified local jobs',
                             command=command(project, 'continue', '--part', part.name)))
    report = read_json(part / 'preview-technical-qa.json', {})
    if report.get('technical_errors') or not report:
        return finish(action('run_preview', 'agent', 'Complete technical checks before presenting the preview',
                             command=command(project, 'continue', '--part', part.name)))
    if not states[part.name]['preview_accepted']:
        from workflow import image_problems
        checks = image_problems(project, [part.name])
        if checks:
            return finish(action('image_inspection', 'agent', 'Inspect current images/references before presenting the preview', problems=checks))
        from align_audio import reviewed_alignment
        alignment = reviewed_alignment(part / timeline['narration_file']) if timeline.get('narration_file') else timeline.get('alignment', {})
        return finish(action('preview_decision', 'user', 'Watch/listen to the complete current preview and give its actual decision once',
                             preview=str(part / 'preview.mp4'), listening_and_captions=True,
                             alignment_checks=[item for item in alignment.get('uncertain_ranges', []) if not item.get('reviewed')]))
    checks = master_problems(project, [part.name])
    if checks:
        return finish(action('inspection', 'agent', 'Finish current image, sound and flagged alignment inspection', problems=checks))
    if not states[part.name]['master_current']:
        return finish(action('run_master', 'agent', 'Render/check the approved master using verified cached inputs',
                             command=command(project, 'continue', '--part', part.name)))
    from delivery import release_inputs
    try:
        inputs = release_inputs(project, part.name)
    except (ValueError, OSError) as error:
        return finish(action('run_master', 'agent', 'Refresh current verified receipts or rebuild affected master inputs',
                             problems=[str(error)], command=command(project, 'continue', '--part', part.name)))
    review = read_json(part / 'playback-review.json', {})
    if review.get('status') != 'passed' or review.get('fingerprint') != fingerprint(inputs):
        return finish(action('playback', 'agent', 'Play the actual current master through its ending and record genuine QA',
                             video=str(part / 'final.mp4')))
    if not states[part.name]['delivered']:
        return finish(action('export', 'agent', 'Export the verified film into a new immutable delivery revision',
                             command=command(project, 'continue', '--part', part.name)))
    return finish(action('part_complete', 'none', 'This part has a current delivery', delivery=states[part.name].get('delivery')))


@hash_session()
def continue_project(project, part_selection='auto'):
    from story_git import require_story_branch
    project = Path(project).resolve()
    require_story_branch(project)
    # Long-lived coordinator lock: OS file locking releases automatically after a crash.
    from production_session import session_lock
    with session_lock(project):
        packet = next_work(project, part_selection)
        work = packet['actions'][0]
        kind, part = work['kind'], packet.get('part')
        if kind == 'preflight':
            from preflight import inspect
            from progress_records import task
            with task(project, 'preflight:' + part):
                readiness = inspect(project, part, live_local=True, reuse_verified=True)
            if not readiness['ready']:
                packet['actions'] = [action('runtime', 'agent', 'Resolve the bundled readiness problems before media work',
                                             problems=readiness['problems'])]
                return remember(project, packet)
            packet = next_work(project, part_selection)
            work = packet['actions'][0]
            kind, part = work['kind'], packet.get('part')
        if kind in ('run_preview', 'run_master'):
            from studio import run_project
            run_project(project, part, 'final' if kind == 'run_master' else 'preview')
            # Return a ready image tool packet in the same invocation, without another local pass.
            packet = next_work(project, part_selection)
            if packet['actions'][0]['kind'] in ('image', 'reference'):
                work = packet['actions'][0]
                kind, part = work['kind'], packet.get('part')
            else:
                return remember(project, packet)
        if kind in ('image', 'reference'):
            from image_jobs import compile_request, compile_reference, queue_request
            from studio_common import configuration
            config = configuration(project)['image_provider']
            request = (compile_reference(project, work['entity'], config.get('estimated_cost_per_image'), config.get('currency', 'USD'))
                       if kind == 'reference' else compile_request(project, part, work['shot'], config.get('estimated_cost_per_image'), config.get('currency', 'USD')))
            path, record = queue_request(project, request)
            if record.get('status') == 'generated':
                packet['actions'] = [action('inspect_image', 'agent',
                    'Reuse/restore the recorded actual pixels, inspect them and register their canonical reference or shot path; do not call the provider again',
                    request=str(path), image=record.get('image'), sha256=record.get('image_sha256'),
                    entity=record.get('entity_id'), shot=record.get('shot_id'),
                    resume=command(project, 'continue', '--part', part or 'auto'))]
                return remember(project, packet)
            packet['actions'] = [action('execute_image', 'agent', 'Inspect references; start immediately before the actual tool call, import its real output and inspect it',
                                       request=str(path), tool_request=record['tool_request'], entity=record.get('entity_id'),
                                       start=command(project, 'images', 'start', '--request', str(path)),
                                       resume=command(project, 'continue', '--part', part or 'auto'))]
            return remember(project, packet)
        elif kind == 'export':
            from delivery import export_part
            revision = 1
            while (project / 'delivery' / f'{part}-r{revision}').exists():
                revision += 1
            export_part(project, part, f'r{revision}')
        else:
            return remember(project, packet)
        return remember(project, next_work(project, part_selection))


def remember(project, packet):
    from progress_records import note, optional_write
    item = packet['actions'][0]
    stage = ('review' if item['actor'] == 'user' else
             'cast' if str(item.get('entity') or '').startswith('CHAR-') else
             'images' if item['kind'] in ('reference', 'image', 'execute_image', 'inspect_image', 'reconcile_provider', 'image_inspection') else
             'cast' if item['kind'] in ('cast_plan', 'cast_change', 'cast_review') else
             'qa' if item['kind'] in ('inspection', 'playback') else
             'delivery' if item['kind'] in ('export', 'complete', 'part_complete', 'continuous_edition') else 'shots')
    state = 'complete' if item['actor'] == 'none' else 'waiting'
    note(project, stage, state, item['message'], actor='user' if item['actor'] == 'user' else 'agent')
    optional_write(Path(project) / 'production/progress/next.json', packet)
    return packet
