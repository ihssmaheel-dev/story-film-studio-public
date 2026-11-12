#!/usr/bin/env python3
"""Record actual final playback review and export a checksummed, reproducible delivery."""
import argparse
from pathlib import Path
import shutil

from project_records import artifact_path, validate_continuity
from quality import check_part, image_review_context
from studio_common import atomic_json, atomic_text, fingerprint, read_json, sha256_file, utc_now


def release_inputs(project, part_id):
    project = Path(project).resolve()
    part = artifact_path(project, 'parts/' + part_id)
    timeline_path = part / 'timeline.json'
    data = read_json(timeline_path)
    render_log = read_json(part / 'final.render-log.json')
    if render_log.get('timeline_sha256') != sha256_file(timeline_path):
        raise ValueError('The master render belongs to an older timeline')
    if render_log.get('audio_sha256') != sha256_file(part / data['audio_file']):
        raise ValueError('The master render belongs to a different audio mix')
    for shot in data['shots']:
        source = (part / shot['image']).resolve()
        if render_log.get('source_image_hashes', {}).get(str(source)) != sha256_file(source):
            raise ValueError('The master render belongs to different source images')
    if render_log.get('subtitles_sha256') and render_log['subtitles_sha256'] != sha256_file(part / 'subtitles.srt'):
        raise ValueError('The master render contains older burned subtitles')
    mix_log = read_json((part / data['audio_file']).with_suffix('.mix-log.json'))
    if mix_log.get('output_sha256') != sha256_file(part / data['audio_file']):
        raise ValueError('Final mix bytes differ from its mix log')
    for name, digest in mix_log.get('source_input_hashes', {}).items():
        if sha256_file(name) != digest:
            raise ValueError('The mix contains older narration or sound assets')
    if data.get('audio_cues') and mix_log.get('audio_manifest_sha256') != sha256_file((part / data['audio_manifest']).resolve()):
        raise ValueError('The mix predates the current audio asset registry')
    # Explicit file membership and byte hashes make every release review invalid after a relevant edit.
    paths = [timeline_path, part / 'final.mp4', part / data['audio_file'], part / 'shots.json',
             project / 'continuity/entities.json', project / 'continuity/state-ledger.json',
             project / 'production/image-reviews.json', part / 'final.render-log.json',
             (part / data['audio_file']).with_suffix('.mix-log.json')]
    if data.get('narration_file'):
        narration = part / data['narration_file']
        paths.extend([narration, narration.with_suffix('.alignment.json'), project / 'audio/narrator.json'])
        if (part / 'speech.json').is_file():
            paths.append(part / 'speech.json')
        chunks_path = narration.with_suffix('.chunks.json')
        if chunks_path.is_file():
            paths.append(chunks_path)
            for chunk in read_json(chunks_path)['chunks']:
                paths.append(narration.parent / chunk['file'])
                receipt = (narration.parent / chunk['file']).with_suffix('.json')
                if receipt.is_file():
                    paths.append(receipt)
                if chunk.get('request_id'):
                    request = project / 'production/speech-jobs' / (chunk['request_id'] + '.json')
                    if request.is_file():
                        paths.append(request)
                        record = read_json(request)
                        if record.get('response_file'):
                            paths.append(artifact_path(project, record['response_file']))
        if narration.with_suffix('.alignment-review.json').exists():
            paths.append(narration.with_suffix('.alignment-review.json'))
    paths.extend(part / shot['image'] for shot in data['shots'])
    if data.get('audio_cues'):
        manifest = (part / data['audio_manifest']).resolve()
        paths.append(manifest)
        assets = read_json(manifest)['assets']
        paths.extend(manifest.parent / assets[cue['asset_id']]['file'] for cue in data['audio_cues'])
        listening = project / 'production/preview-listening.json'
        if listening.is_file():
            paths.append(listening)
    if read_json(project / 'creative/intake.json').get('subtitles') is not False:
        paths.append(part / 'subtitles.srt')
    for group in read_json(project / 'continuity/entities.json').values():
        if isinstance(group, dict):
            for entity in group.values():
                if isinstance(entity, dict) and entity.get('canonical_file'):
                    paths.append(artifact_path(project, entity['canonical_file']))
                    paths.extend(artifact_path(project, name) for name in entity.get('reference_paths', []))
                    paths.extend(artifact_path(project, name) for name in entity.get('previous_reference_paths', []))
    for name in ('world/cast.json', 'production/cast-reviews.json'):
        if (project / name).is_file():
            paths.append(project / name)
    from image_references import collect
    for shot in read_json(part / 'shots.json')['shots']:
        refs, _ = collect(project, {'kind': 'final', 'part_id': part_id, 'shot_id': shot['id']})
        paths.extend(Path(item['path']) for item in refs.bindings)
    style_manifest = project / 'references/style/manifest.json'
    if read_json(style_manifest, {}).get('references'):
        paths.append(style_manifest)
    result = {}
    for path in paths:
        path = path.resolve()
        if not path.is_relative_to(project):
            raise ValueError('Release assets must be snapshotted inside the story project: ' + str(path))
        result[path.relative_to(project).as_posix()] = sha256_file(path)
    if render_log.get('output_sha256') != result[(part / 'final.mp4').relative_to(project).as_posix()]:
        raise ValueError('Master bytes differ from the verified render log')
    return result


def check_release(project, part_id):
    project = Path(project).resolve()
    from workflow import require_stage
    require_stage(project, 'release', [part_id])
    problems = validate_continuity(project, [part_id])
    part = artifact_path(project, 'parts/' + part_id)
    timeline = read_json(part / 'timeline.json')
    from align_audio import reviewed_alignment
    if timeline.get('narration_file'):
        current = reviewed_alignment(part / timeline['narration_file'])
        if current.get('review_warning') or any(not item.get('reviewed') for item in current['uncertain_ranges']):
            problems.append('Speech alignment has outstanding or stale manual checks')
    reviews = read_json(project / 'production/image-reviews.json', {'reviews': {}})['reviews']
    for shot in read_json(part / 'shots.json')['shots']:
        image = next(item for item in timeline['shots'] if item['id'] == shot['id'])['image']
        review = reviews.get(part_id + '/' + shot['id'], {})
        if (review.get('verdict') != 'passed' or review.get('sha256') != sha256_file(part / image)
                or review.get('context') != image_review_context(project, part_id, shot)):
            problems.append(shot['id'] + ': current visual/reference review is required')
    if timeline.get('audio_cues'):
        from listening import problems as listening_problems
        problems.extend(listening_problems(project, part_id))
    inputs = release_inputs(project, part_id)
    report = check_part(part / 'timeline.json', part / 'final.mp4')
    problems.extend(report['technical_errors'])
    if problems:
        raise ValueError('; '.join(problems))
    return inputs, report


def record_playback(project, part_id, reviewer, notes, accept_warnings=False):
    if not reviewer.strip() or not notes.strip():
        raise ValueError('Actual end-to-end playback reviewer and inspection notes are required')
    inputs, report = check_release(project, part_id)
    if report['warnings'] and not accept_warnings:
        raise ValueError('Inspect and explicitly accept or fix these warnings: ' + '; '.join(report['warnings']))
    record = {'reviewer': reviewer, 'notes': notes, 'at': utc_now(), 'inputs': inputs,
              'fingerprint': fingerprint(inputs), 'accepted_warnings': report['warnings'], 'status': 'passed'}
    path = Path(project) / 'parts' / part_id / 'playback-review.json'
    atomic_json(path, record)
    report.update(manual_visual_and_listening_status='passed', release_ready=True)
    atomic_json(path.parent / 'final-technical-qa.json', report)
    return path


def export_part(project, part_id, revision):
    import re
    project = Path(project).resolve()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,59}', revision):
        raise ValueError('Use a short safe delivery revision such as r1')
    inputs, report = check_release(project, part_id)
    part = project / 'parts' / part_id
    review = read_json(part / 'playback-review.json')
    if review.get('status') != 'passed' or review.get('fingerprint') != fingerprint(inputs):
        raise ValueError('End-to-end playback review is absent or stale')
    destination = project / 'delivery' / (part_id + '-' + revision)
    if destination.exists():
        raise ValueError('Delivery revision already exists; select a new explicit revision')
    extras = [part / 'playback-review.json', part / 'storyboard.md', part / 'narration.txt', project / 'approvals.json',
              project / 'approvals.md', project / 'creative/source.json', project / 'creative/intake.json',
              project / 'creative/audit-issues.json', project / 'audio/narrator.json', project / 'audio/sound-plan.md',
              project / 'audio/voice-plan.json', project / 'audio/voice-decisions.json',
              project / 'creative/revision.json',
              project / 'creative/part-plan.json',
              project / 'production/settings.json', project / 'production/authorizations.json',
              project / 'production/workflow.json', project / 'production/delegation.json',
              project / 'production/git.json',
              project / 'production/preview-decisions.json',
              project / 'continuity/story-ledger.json', project / 'continuity/dependencies.json']
    extras += list((project / 'creative').glob('*.md'))
    extras += list((project / 'audio/voice-revisions').glob('*.json'))
    extras += [project / 'production/cast-change-requests.json']
    extras += list((project / 'production/cast-revisions').glob('*/receipt.json'))
    extras += [path for path in (project / 'production/image-jobs').glob('*.json')
               if read_json(path).get('part_id') == part_id]
    for extra in extras:
        if extra.is_file():
            inputs[extra.relative_to(project).as_posix()] = sha256_file(extra)
    # Copy only exact recorded artifacts, retaining relative paths so the delivered timeline stays portable.
    for relative, digest in inputs.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(project / relative, target)
        if sha256_file(target) != digest:
            raise ValueError('Delivery copy checksum mismatch: ' + relative)
    from studio_common import ROOT
    for source, relative in [(ROOT / '.runtime/manifest.json', 'runtime/manifest.json'),
                              (ROOT / 'requirements.lock.txt', 'runtime/requirements.lock.txt'),
                              (ROOT / 'studio.json', 'runtime/studio.json')]:
        if source.is_file():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            inputs[relative] = sha256_file(target)
    report.update(manual_visual_and_listening_status='passed', release_ready=True)
    atomic_json(destination / 'qa-report.json', report)
    atomic_json(destination / 'manifest.json', {'part_id': part_id, 'revision': revision, 'exported_at': utc_now(),
                                             'files': inputs, 'playback_review': review, 'release_ready': True})
    atomic_text(destination / 'README.md', '# Delivery ' + part_id + ' ' + revision + '\n\n'
                + 'Master: `' + 'parts/' + part_id + '/final.mp4`\n\n'
                + 'The manifest records the reviewed file hashes. QA warnings and their acceptance are preserved.\n')
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--part', required=True)
    sub = parser.add_subparsers(dest='action', required=True)
    review = sub.add_parser('review')
    review.add_argument('--reviewer', required=True)
    review.add_argument('--notes', required=True)
    review.add_argument('--accept-warnings', action='store_true')
    export = sub.add_parser('export')
    export.add_argument('--revision', required=True)
    args = parser.parse_args()
    try:
        print(record_playback(args.project, args.part, args.reviewer, args.notes, args.accept_warnings)
              if args.action == 'review' else export_part(args.project, args.part, args.revision))
    except (ValueError, OSError, RuntimeError, KeyError, StopIteration) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
