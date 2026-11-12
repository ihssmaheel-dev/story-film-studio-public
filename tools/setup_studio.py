#!/usr/bin/env python3
"""Install the pinned local CPU runtime and verify public binary/model checksums."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

from studio_common import ROOT, atomic_json, process, sha256_file, utc_now

FFMPEG_URL = 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip'
FFMPEG_SHA = '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'
MODELS = {
    'kokoro-v1.0.onnx': 'beb0d1848dee9a49da392cc3df26958d46cfa35d321edf434f52949153f0df3a',
    'voices-v1.0.bin': 'bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d',
}


def download(url, output, checksum=None, allowed_hosts=None):
    output = Path(output).resolve()
    if not url.startswith('https://'):
        raise ValueError('Downloads require HTTPS')
    def check_host(value):
        from urllib.parse import urlparse
        parsed = urlparse(value)
        if parsed.scheme != 'https' or parsed.hostname not in allowed_hosts or parsed.username or parsed.password:
            raise ValueError('Download or redirect host is outside the authorized source scope')
    if allowed_hosts is not None:
        check_host(url)
    if output.is_file() and (checksum is None or sha256_file(output) == checksum):
        return output
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + '.partial')
    curl = shutil.which('curl.exe') if sys.platform == 'win32' else shutil.which('curl')
    if allowed_hosts is not None:
        class ScopedRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, fp, code, msg, headers, newurl):
                check_host(newurl)
                return super().redirect_request(request, fp, code, msg, headers, newurl)
        opener = urllib.request.build_opener(ScopedRedirect())
        with opener.open(url, timeout=60) as source, temporary.open('wb') as target:
            shutil.copyfileobj(source, target, 1024 * 1024)
    elif curl:
        process([curl, '--fail', '--location', '--retry', '2', '--connect-timeout', '20',
                 '--max-time', '300', '--output', str(temporary), url], timeout=330)
    else:
        with urllib.request.urlopen(url, timeout=60) as source, temporary.open('wb') as target:
            shutil.copyfileobj(source, target, 1024 * 1024)
    if checksum is not None and sha256_file(temporary) != checksum:
        raise ValueError(f'Download checksum mismatch: {output.name}; unverified bytes remain quarantined as .partial')
    temporary.replace(output)
    return output


def verify_runtime():
    from studio_common import executable
    assets = {}
    for name in ('ffmpeg', 'ffprobe'):
        path = executable(name)
        if not path:
            raise ValueError(f'{name} is not configured')
        version = process([path, '-version']).stdout.splitlines()[0]
        assets[name] = {'file': str(Path(path).relative_to(ROOT)), 'sha256': sha256_file(path),
                        'version': version, 'source': FFMPEG_URL, 'archive_sha256': FFMPEG_SHA}
    for name, expected in MODELS.items():
        path = ROOT / 'models/kokoro' / name
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f'Missing/unverified model file: {name}')
        assets[name] = {'file': path.relative_to(ROOT).as_posix(), 'sha256': expected,
                        'source': 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/' + name}
    filters = process([assets_path(assets['ffmpeg']), '-hide_banner', '-filters']).stdout
    required = ('amix', 'afade', 'adelay', 'sidechaincompress', 'alimiter', 'loudnorm', 'subtitles', 'blackdetect', 'silencedetect')
    missing = [name for name in required if name not in filters]
    if missing:
        raise ValueError(f'FFmpeg required filters missing: {missing}')
    packages = {name: importlib.metadata.version(name) for name in
                ('kokoro-onnx', 'soundfile', 'numpy', 'Pillow', 'pocketsphinx', 'onnxruntime')}
    distribution = importlib.metadata.distribution('kokoro-onnx')
    license_file = next(entry for entry in distribution.files if str(entry).endswith('licenses/LICENSE'))
    shutil.copy2(distribution.locate_file(license_file), ROOT / 'models/kokoro/kokoro-onnx-LICENSE.txt')
    manifest = {'schema_version': 1, 'verified_at': utc_now(), 'python': sys.version.split()[0],
                'assets': assets, 'packages': packages, 'ffmpeg_filters': list(required),
                'image_provider': 'codex-imagegen agent bridge; final story approvals required',
                'licenses': {'kokoro_wrapper': 'models/kokoro/kokoro-onnx-LICENSE.txt',
                             'model_terms': 'models/kokoro/model-LICENSE.txt',
                             'model_card': 'models/kokoro/model-card.md'},
                'media_rights': 'Runtime verification does not establish rights for arbitrary sourced/generated media.'}
    atomic_json(ROOT / '.runtime/manifest.json', manifest)
    atomic_json(ROOT / 'models/kokoro/manifest.json', {name: assets[name] for name in MODELS})
    return manifest


def assets_path(record):
    return str(ROOT / record['file'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    try:
        if not args.verify_only:
            python = ROOT / ('.venv/Scripts/python.exe' if sys.platform == 'win32' else '.venv/bin/python')
            if not python.is_file():
                print('Creating isolated local Python environment...', flush=True)
                process([sys.executable, '-m', 'venv', str(ROOT / '.venv')])
            print('Installing exact tested packages...', flush=True)
            process([str(python), '-m', 'pip', 'install', '--only-binary=:all:', '-r', str(ROOT / 'requirements.lock.txt')])
            archive = download(FFMPEG_URL, ROOT / '.runtime/downloads/ffmpeg-9.0.2-essentials_build.zip', FFMPEG_SHA)
            destination = (ROOT / '.runtime/ffmpeg').resolve()
            with zipfile.ZipFile(archive) as package:
                for member in package.infolist():
                    if not (destination / member.filename).resolve().is_relative_to(destination):
                        raise ValueError('Archive contains a path outside the runtime directory')
                package.extractall(destination)
            for name, checksum in MODELS.items():
                print(f'Checking/downloading {name}...', flush=True)
                download('https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/' + name,
                         ROOT / 'models/kokoro' / name, checksum)
            for name, url in {
                'model-card.md': 'https://huggingface.co/hexgrad/Kokoro-82M/raw/main/README.md',
                'model-LICENSE.txt': 'https://www.apache.org/licenses/LICENSE-2.0.txt',
            }.items():
                download(url, ROOT / 'models/kokoro' / name)
            if Path(sys.executable).resolve() != python.resolve():
                result = process([str(python), str(Path(__file__)), '--verify-only'])
                print(result.stdout)
                return
        manifest = verify_runtime()
        print(json.dumps({'runtime': 'verified', 'packages': manifest['packages']}, indent=2))
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
