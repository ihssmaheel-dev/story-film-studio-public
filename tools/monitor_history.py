"""Chronological, read-only production history from actual recorded evidence."""
from progress_records import label
from studio_common import fingerprint


def production_history(reader, project, timings, media, source, requests):
    # Import here to keep the snapshot/history modules independent at import time.
    from progress_snapshot import finite, public_text, timestamp

    events = []

    def append(at, kind, job, message, *, duration=None, detail=None, origin='telemetry', part=None):
        if timestamp(at) is None:
            return
        event = {'at': at, 'kind': kind, 'job': job, 'label': label(job),
                 'message': public_text(message), 'detail': public_text(detail),
                 'part': part or next((item for item in job.split(':') if item.startswith('part_')), None),
                 'duration_seconds': duration if finite(duration) and duration >= 0 else None,
                 'source': origin}
        event['id'] = fingerprint([at, kind, job, message, origin])[:20]
        events.append(event)

    append(source.get('copied_at_utc'), 'intake', 'story', 'Story source received', origin='source-record')
    for item in timings:
        job = str(item.get('job', ''))
        kind = 'cached' if item.get('cache_hit') else 'failed' if item.get('error') else 'complete'
        suffix = ' reused from cache' if kind == 'cached' else ' failed' if kind == 'failed' else ' completed'
        append(item.get('at'), kind, job, label(job) + suffix,
               duration=item.get('seconds'), origin='measured-timing')

    terminal = events[:]
    for item in reader.lines(project / 'production/progress/events.jsonl', 160):
        job, kind, at = str(item.get('job', '')), str(item.get('kind', 'note')), item.get('at')
        when = timestamp(at)
        # Job timings are the measured completion record; don't show its telemetry twin twice.
        if when is not None and kind in ('complete', 'cached', 'failed') and any(
                other['job'] == job and other['kind'] == kind and abs(timestamp(other['at']) - when) < 3
                for other in terminal):
            continue
        append(at, kind, job, item.get('message'), duration=item.get('elapsed_seconds'),
               detail=item.get('status'), part=item.get('part'))

    seen_changes = set()
    for part in media:
        for change in part['voice_changes']:
            if change['id'] in seen_changes:
                continue
            seen_changes.add(change['id'])
            append(change['at'], 'voice_change', 'narration:' + part['part'],
                   ('Narrator' if change['speaker'] == 'NARRATOR' else change['speaker']) + ' voice changed to ' + str(change['to_voice']),
                   detail=change['request'] or change['reason'], origin='voice-decision', part=part['part'])

    decisions = reader.json(project / 'production/preview-decisions.json')
    for decision in [*decisions.get('history', []), *decisions.get('decisions', {}).values()]:
        if decision.get('status') == 'accepted':
            part = str(decision.get('part_id') or '')
            append(decision.get('at'), 'decision', 'review:' + part, 'Preview decision recorded',
                   detail=decision.get('decision_quote'), origin='preview-decision', part=part)

    for kind, records in requests:
        for record in records:
            part = str(record.get('part_id') or '')
            identity = record.get('shot_id') or record.get('asset_id') or record.get('entity_id')
            title = 'Cast sheet' if kind == 'cast' else 'Image' if kind == 'images' else 'Speech'
            detail = public_text(identity)
            for field, state, message in (
                ('started_at', 'requested', title + ' request submitted'),
                ('imported_at', 'received', title + ' result imported'),
                ('received_at', 'received', title + ' result received'),
                ('failed_at', 'failed', title + ' request needs attention'),
            ):
                append(record.get(field), state, kind + ':' + part, message, detail=detail, origin='provider-record', part=part)

    for path in sorted((project / 'delivery').glob('*/manifest.json'))[-30:]:
        record = reader.json(path)
        if record.get('release_ready') is True:
            part = str(record.get('part_id') or '')
            append(record.get('exported_at'), 'delivery', 'delivery:' + part, 'Delivery package exported',
                   detail='Revision ' + public_text(record.get('revision')), origin='delivery-manifest', part=part)

    unique = {event['id']: event for event in events}
    return sorted(unique.values(), key=lambda event: timestamp(event['at']), reverse=True)[:200]
