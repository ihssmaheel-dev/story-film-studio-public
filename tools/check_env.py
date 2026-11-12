#!/usr/bin/env python3
"""Report actual configured runtime readiness and remaining agent/provider decisions."""
import argparse
import importlib.metadata
import json
import sys
from pathlib import Path
from studio_common import ROOT, configuration, executable, process, read_json, sha256_file

IMAGE_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp'}


def report(project=None):
    from speech_providers import catalog, ready_problems, validate_profile, voice_config
    selected = []
    if project:
        profile = read_json(Path(project) / 'audio/narrator.json')
        validate_profile(profile)
        selected = [voice_config(profile, speaker) for speaker in ['NARRATOR', *profile.get('cast', {})]]
    needs_kokoro = any(item['provider'] == 'kokoro' for item in selected)
    packages, problems, binaries, models = {}, [], {}, {}
    for name in ('kokoro-onnx', 'soundfile', 'numpy', 'Pillow', 'pocketsphinx', 'onnxruntime'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
            if name not in ('kokoro-onnx', 'onnxruntime') or needs_kokoro:
                problems.append(f'Missing package in this interpreter: {name}')
    for name in ('ffmpeg', 'ffprobe'):
        path = executable(name)
        if not path:
            problems.append(f'{name} not configured')
            continue
        try:
            binaries[name] = {'path': path, 'version': process([path, '-version']).stdout.splitlines()[0]}
        except (OSError, RuntimeError) as error:
            problems.append(str(error))
    manifest = read_json(ROOT / 'models/kokoro/manifest.json', {})
    for name in ('kokoro-v1.0.onnx', 'voices-v1.0.bin'):
        path = ROOT / 'models/kokoro' / name
        # Do not stream an unrelated large Kokoro model while inspecting a
        # selected Chatterbox/cloud/imported provider.
        checked = not project or needs_kokoro
        verified = path.is_file() and manifest.get(name, {}).get('sha256') == sha256_file(path) if checked else None
        models[name] = {'present': path.is_file(), 'checksum_checked': checked, 'upstream_checksum_verified': verified}
        if not verified and needs_kokoro:
            problems.append(f'Missing or unverified model/voice file: {name}')
    speech = []
    for item in selected:
        errors = ready_problems(project, item, credentials=True)
        speech.append({'provider': item['provider'], 'model': item['model'], 'problems': errors,
                       'live_synthesis_verified': False})
    inspiration = sorted(
        path for path in (ROOT / 'references/style').rglob('*')
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    )
    return {'python': sys.version.split()[0], 'interpreter': sys.executable, 'platform': sys.platform,
            'local_media_ready': not problems, 'problems': problems, 'packages': packages,
            'binaries': binaries, 'models': models, 'optional_inspiration_count': len(inspiration),
            'speech_providers': catalog(), 'selected_speech': speech,
            'image_bridge': {'mode': configuration()['image_provider']['mode'], 'request_and_import': 'available',
                             'execution': 'agent uses the approved available image tool; no automatic paid calls',
                             'live_story_generation': 'requires real story, references, provider cost/privacy decisions and approvals'},
            'alignment': {'engine': 'PocketSphinx CPU', 'tested_language': 'English',
                          'uncertain_ranges': 'must be manually inspected'},
            'sound': 'Procedural textures plus registered provided/sourced assets; general music generation requires an approved provider'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--project', type=Path, help='Inspect the selected speech provider instead of requiring Kokoro')
    args = parser.parse_args()
    status = report(args.project)
    if args.json:
        print(json.dumps(status, indent=2))
    else:
        print('Local media runtime:', 'READY' if status['local_media_ready'] else 'NEEDS SETUP')
        print('Python:', status['interpreter'])
        for name, item in status['binaries'].items():
            print(f'{name}: {item["version"]}')
        for name, version in status['packages'].items():
            print(f'{name}: {version or "MISSING"}')
        for problem in status['problems']:
            print('ACTION:', problem)
        print('Images: agent request/import bridge; real production still uses explicit story approvals.')
        print('Alignment: CPU English model; inspect flagged words. Other languages need a compatible aligner.')
        print('Speech: choose with studio providers; cloud credentials and optional local servers are not live synthesis checks.')
        for item in status['selected_speech']:
            print(item['provider'] + ': ' + ('configuration present; audition remains required' if not item['problems'] else '; '.join(item['problems'])))
    if not status['local_media_ready']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
