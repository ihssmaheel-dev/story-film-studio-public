#!/usr/bin/env python3
"""Optional loopback Chatterbox bridge; run in its own environment with local weights."""
import argparse
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
import importlib.metadata
import io
import json
import math
import os
from pathlib import Path

from speech_providers import CHATTERBOX_TAGS
from studio_common import sha256_file


def load_model(directory, model, device):
    # Inference never triggers a model download. Prepare and review the weights first.
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    if model in ('turbo', 'nano'):
        from chatterbox.tts_turbo import ChatterboxTurboTTS
        return ChatterboxTurboTTS.from_local(directory, device=device, nano=model == 'nano')
    if model.startswith('multilingual-'):
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        return ChatterboxMultilingualTTS.from_local(directory, device=device, t3_model=model.rsplit('-', 1)[1])
    from chatterbox.tts import ChatterboxTTS
    return ChatterboxTTS.from_local(directory, device=device)


def model_info(directory, model, device):
    hashes = {path.relative_to(directory).as_posix(): sha256_file(path)
              for path in sorted(directory.rglob('*')) if path.is_file()}
    if not hashes:
        raise ValueError('The configured Chatterbox checkpoint folder is empty')
    digest = sha256(json.dumps(hashes, sort_keys=True).encode('utf-8')).hexdigest()
    return {'model': model, 'device': device, 'model_fingerprint': digest,
            'package_version': importlib.metadata.version('chatterbox-tts'),
            'checkpoint_files': hashes, 'verification': 'Actual local file hashes; source/usage review remains separate.'}


def synthesize(model, variant, voice_root, body):
    import soundfile as sf
    allowed = {'text', 'voice', 'model', 'language', 'speed', 'direction', 'reference_audio', 'temperature', 'exaggeration', 'cfg_weight'}
    if not isinstance(body, dict) or set(body) - allowed or body.get('model') != variant:
        raise ValueError('Unsupported request or wrong Chatterbox model')
    text = body.get('text')
    if not isinstance(text, str) or not text.strip() or len(text) > 500 or body.get('speed', 1) != 1:
        raise ValueError('Use a nonempty turn up to 500 characters at native speed 1.0')
    reference = Path(body.get('reference_audio', '')).resolve()
    if not reference.is_relative_to(voice_root) or not reference.is_file():
        raise ValueError('A reviewed reference clip inside the configured voice root is required for every turn')
    direction = body.get('direction', '')
    if direction:
        if variant not in ('turbo', 'nano') or direction not in CHATTERBOX_TAGS:
            raise ValueError('Unsupported Chatterbox acting direction')
        text = '[' + direction + '] ' + text
    language = body.get('language', 'en').replace('_', '-').split('-')[0]
    if not variant.startswith('multilingual-') and language != 'en':
        raise ValueError('This Chatterbox variant is English only')
    options = {'audio_prompt_path': str(reference)}
    for key, low, high in [('temperature', 0.1, 2), ('exaggeration', 0, 2), ('cfg_weight', 0, 1)]:
        if key in body:
            value = body[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError('Invalid Chatterbox generation control: ' + key)
            if variant in ('turbo', 'nano') and key in ('exaggeration', 'cfg_weight') and value != 0:
                raise ValueError('Turbo/Nano do not support exaggeration or CFG controls')
            options[key] = value
    if variant.startswith('multilingual-'):
        if language not in model.get_supported_languages():
            raise ValueError('Selected language is not supported by this Chatterbox checkpoint')
        options['language_id'] = language
    samples = model.generate(text, **options).detach().cpu().numpy().reshape(-1)
    if not samples.size:
        raise ValueError('Chatterbox returned empty audio')
    output = io.BytesIO()
    sf.write(output, samples, model.sr, format='WAV', subtype='PCM_16')
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoints', required=True, type=Path)
    parser.add_argument('--voice-root', required=True, type=Path)
    parser.add_argument('--model', choices=('original', 'turbo', 'nano', 'multilingual-v2', 'multilingual-v3'), default='turbo')
    parser.add_argument('--device', choices=('cpu', 'cuda', 'mps'), default='cpu')
    parser.add_argument('--port', type=int, default=8090)
    args = parser.parse_args()
    directory, voice_root = args.checkpoints.resolve(), args.voice_root.resolve()
    if not directory.is_dir() or not voice_root.is_dir():
        parser.error('Checkpoint and reviewed voice-reference directories must already exist')
    try:
        info = model_info(directory, args.model, args.device)
        model = load_model(directory, args.model, args.device)
    except (ImportError, OSError, ValueError) as error:
        parser.error(str(error))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Do not log submitted story text or reference paths.

        def send(self, status, body, content_type):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path != '/info':
                return self.send(404, b'Not found', 'text/plain')
            self.send(200, json.dumps(info).encode('utf-8'), 'application/json')

        def do_POST(self):
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if self.path != '/speech' or not 0 < size <= 1024 * 1024:
                    raise ValueError('Invalid speech request')
                body = json.loads(self.rfile.read(size))
                self.send(200, synthesize(model, args.model, voice_root, body), 'audio/wav')
            except Exception:
                self.send(400, b'Chatterbox generation failed; inspect the selected local configuration.', 'text/plain')

    print(json.dumps({'endpoint': f'http://127.0.0.1:{args.port}/speech', **info}), flush=True)
    HTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
