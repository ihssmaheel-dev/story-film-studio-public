"""Check selected runtime, speech and alignment readiness before production work."""
import argparse
import importlib.metadata
import ipaddress
import json
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, build_opener

from studio_common import ROOT, atomic_json, configuration, executable, fingerprint, read_json, sha256_file, utc_now


def inputs(project, part_selection='all'):
    from workflow import selected_parts
    project = Path(project).resolve()
    parts = selected_parts(project, None if part_selection == 'all' else [part_selection])
    profile = read_json(project / 'audio/narrator.json')
    from speech_providers import voice_config
    from project_records import artifact_path
    references = {}
    for speaker in ('NARRATOR', *profile.get('cast', {})):
        name = voice_config(profile, speaker)['options'].get('reference_audio')
        if name:
            path = artifact_path(project, name)
            references[name] = sha256_file(path) if path.is_file() else None
    runtime, files, packages = configuration(project)['runtime'], {}, {}
    for name in ('ffmpeg', 'ffprobe', 'model', 'voices'):
        binary = executable(name) if name in ('ffmpeg', 'ffprobe') else None
        path = Path(binary) if binary else ROOT / runtime.get(name, '')
        files[name] = [str(path), path.stat().st_size, path.stat().st_mtime_ns] if path.is_file() else None
    for name in ('soundfile', 'numpy', 'Pillow', 'pocketsphinx'):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return fingerprint({'profile': profile, 'reference_hashes': references, 'runtime': runtime,
                        'runtime_files': files, 'packages': packages,
                        'preflight_code': sha256_file(Path(__file__)),
                        'parts': {part.name: {'text': (part / 'narration.txt').read_text(encoding='utf-8-sig'),
                                              'speech': read_json(part / 'speech.json', {}),
                                              'timing_mode': read_json(part / 'shots.json').get('timing_mode')}
                                  for part in parts}})


def speech_cached(project, part):
    """Verify actual assembled and per-turn bytes before skipping model/server setup."""
    from speech import current_problems
    project, part = Path(project).resolve(), Path(part).resolve()
    timeline = read_json(part / 'timeline.json', {})
    if not timeline.get('narration_file'):
        return True
    audio = (part / timeline['narration_file']).resolve()
    manifest = read_json(audio.with_suffix('.chunks.json'), {})
    if not manifest.get('speech_input_fingerprint') or not manifest.get('chunks') or not audio.is_file():
        return False
    if manifest.get('audio_sha256') != sha256_file(audio) or current_problems(project, [part], require_runtime=False):
        return False
    for chunk in manifest['chunks']:
        clip = (audio.parent / chunk['file']).resolve()
        if not clip.is_relative_to(project) or not clip.is_file() or sha256_file(clip) != chunk.get('sha256'):
            return False
    return True


def local_info(config):
    """Read loopback metadata only. Never synthesize, download models or call cloud APIs."""
    from speech_providers import NoRedirect
    endpoint = urlsplit(config['options']['endpoint'])
    host = endpoint.hostname
    try:
        loopback = host == 'localhost' or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if not loopback or endpoint.username or endpoint.password:
        raise ValueError('Live preflight is limited to a credential-free loopback Chatterbox server')
    url = urlunsplit((endpoint.scheme, endpoint.netloc, '/info', '', ''))
    with build_opener(NoRedirect()).open(Request(url), timeout=3) as response:
        data = response.read(65537)
    if len(data) > 65536:
        raise ValueError('Local model-info response exceeds the metadata limit')
    info = json.loads(data)
    if not isinstance(info, dict):
        raise ValueError('Local model-info response must be an object')
    if info.get('model') != config['model']:
        raise ValueError('Local Chatterbox model differs from the selected model')
    expected = config['options'].get('model_fingerprint')
    if expected and info.get('model_fingerprint') != expected:
        raise ValueError('Local Chatterbox checkpoint fingerprint differs from the selected model')
    return {key: info.get(key) for key in ('model', 'device', 'model_fingerprint')}


def inspect(project, part_selection='all', live_local=False, reuse_verified=False):
    from align_audio import validate_alignment_text
    from speech import plan_speech
    from workflow import selected_parts
    project = Path(project).resolve()
    problems, parts, providers = [], [], []
    for binary in ('ffmpeg', 'ffprobe'):
        if not executable(binary):
            problems.append(binary + ' is not configured')
    for package in ('soundfile', 'numpy', 'Pillow', 'pocketsphinx'):
        try:
            importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            problems.append('Missing local package: ' + package)
    profile = read_json(project / 'audio/narrator.json')
    for part in selected_parts(project, None if part_selection == 'all' else [part_selection]):
        item = {'part': part.name, 'speech_turns': 0}
        try:
            text = (part / 'narration.txt').read_text(encoding='utf-8-sig')
            if reuse_verified and speech_cached(project, part):
                item.update(speech_reused=True, speech_turns=len(read_json(part / 'speech.json', {}).get('utterances', [])))
                parts.append(item)
                continue
            if text.strip():
                turns = plan_speech(project, profile, text, part / 'speech.json')
                item['speech_turns'] = len(turns)
                if read_json(part / 'shots.json').get('timing_mode') != 'manual':
                    validate_alignment_text(turns, profile)
                checked = set()
                for turn in turns:
                    config = turn['config']
                    identity = (config['provider'], config['model'], config['options'].get('endpoint'))
                    if identity in checked:
                        continue
                    checked.add(identity)
                    provider = {'provider': config['provider'], 'model': config['model'], 'live_synthesis_verified': False}
                    from speech_providers import ready_problems
                    problems.extend(part.name + ': ' + value for value in ready_problems(project, config, credentials=True))
                    if live_local and config['provider'] == 'chatterbox':
                        provider['local_model_info'] = local_info(config)
                    providers.append(provider)
        except (OSError, ValueError, RuntimeError, ImportError) as error:
            problems.append(part.name + ': ' + str(error))
        parts.append(item)
    result = {'checked_at': utc_now(), 'inputs': inputs(project, part_selection), 'ready': not problems, 'parts': parts, 'speech': providers,
              'problems': problems, 'next_actions': [{'actor': 'agent', 'message': value} for value in problems],
              'scope': 'Read-only local configuration/dictionary checks; optional loopback model-info GET. No synthesis, cloud calls, downloads or approvals.'}
    atomic_json(project / 'production/preflight.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--part', default='all')
    parser.add_argument('--live-local', action='store_true')
    args = parser.parse_args()
    result = inspect(args.project, args.part, args.live_local)
    print(json.dumps(result, indent=2))
    if not result['ready']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
