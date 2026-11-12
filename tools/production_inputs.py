"""Content dependencies for media jobs; review-only changes do not re-encode media."""
from pathlib import Path

from studio_common import atomic_json, fingerprint, read_json, sha256_file, utc_now
from workflow import presentation


def mix_plan(timeline):
    return {key: timeline.get(key) for key in ('duration', 'narration_file', 'narration_start',
            'narration_gain_db', 'audio_file', 'audio_manifest', 'audio_cues')}


def asset_inputs(used):
    return {identity: {key: asset.get(key) for key in ('file', 'sha256')}
            for identity, asset in used.items()}


def refresh_receipt(path, timeline_path, manifest=None, rendered=False):
    """Called only after JobStore verifies all cached outputs and content inputs."""
    path, timeline_path = Path(path), Path(timeline_path)
    receipt, timeline = read_json(path), read_json(timeline_path)
    if rendered and receipt.get('presentation_fingerprint') != fingerprint(presentation(timeline)):
        raise ValueError('Cached render presentation differs; a new render is required')
    updates = {'timeline_sha256': sha256_file(timeline_path)}
    if manifest:
        updates['audio_manifest_sha256'] = sha256_file(manifest)
    changes = {key: {'before': receipt.get(key), 'after': value}
               for key, value in updates.items() if receipt.get(key) != value}
    if changes:
        receipt.update(updates)
        receipt.setdefault('metadata_refreshes', []).append({
            'at': utc_now(), 'changes': changes,
            'reason': 'Verified content inputs/output bytes unchanged; refreshed review metadata without media generation.'})
        atomic_json(path, receipt)
