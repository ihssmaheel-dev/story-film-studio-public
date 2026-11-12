"""Speech provider contracts. Credentials are environment references, never project data."""
import base64
import ipaddress
import json
import math
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from studio_common import ROOT, configuration, fingerprint, sha256_file

PROVIDERS = {
    'kokoro': {'name': 'Kokoro ONNX', 'local': True, 'model': 'kokoro-82m', 'docs': 'https://github.com/thewh1teagle/kokoro-onnx'},
    'chatterbox': {'name': 'Chatterbox local server', 'local': True, 'model': 'turbo', 'endpoint': 'http://127.0.0.1:8090/speech', 'docs': 'https://github.com/resemble-ai/chatterbox'},
    'elevenlabs': {'name': 'ElevenLabs', 'local': False, 'model': 'eleven_v4', 'api_key_env': 'ELEVENLABS_API_KEY', 'docs': 'https://elevenlabs.io/docs/api-reference/text-to-dialogue/convert'},
    'inworld': {'name': 'Inworld', 'local': False, 'model': 'inworld-tts-2', 'api_key_env': 'INWORLD_API_KEY', 'docs': 'https://docs.inworld.ai/api-reference/ttsAPI/texttospeech/synthesize-speech'},
    'cartesia': {'name': 'Cartesia', 'local': False, 'model': 'sonic-3.6', 'api_version': '2026-08-14', 'api_key_env': 'CARTESIA_API_KEY', 'docs': 'https://docs.cartesia.ai/api-reference/tts/bytes'},
    'custom-http': {'name': 'Custom speech gateway', 'local': False, 'model': None, 'docs': 'docs/14-speech-providers.md'},
    'provided': {'name': 'Imported voice audio (any provider or actor)', 'local': True, 'model': 'provided-recording', 'docs': 'docs/14-speech-providers.md'},
}
VOICE_KEYS = {'provider', 'model', 'voice', 'language', 'speed', 'options'}
CHATTERBOX_TAGS = {'clear throat', 'sigh', 'shush', 'cough', 'groan', 'sniff', 'gasp', 'chuckle', 'laugh'}
OPTION_KEYS = {'model', 'endpoint', 'api_key_env', 'api_version', 'price_per_1000_characters', 'currency',
               'timeout_seconds', 'reference_audio', 'model_fingerprint', 'voice_settings', 'generation_config',
               'response_format', 'audio_json_key', 'auth_header', 'auth_prefix', 'request_extra',
               'temperature', 'exaggeration', 'cfg_weight', 'max_characters', 'local_only', 'dialogue_settings', 'delivery_mode'}


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def local_endpoint(url):
    parsed = urlparse(url)
    try:
        local = ipaddress.ip_address(parsed.hostname or '').is_loopback
    except ValueError:
        local = parsed.hostname == 'localhost'
    return local and parsed.scheme in ('http', 'https') and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment


def check_options(options):
    if not isinstance(options, dict) or set(options) - OPTION_KEYS:
        raise ValueError('Unsupported speech provider options; store credentials only in an environment variable')
    if 'api_key_env' in options and not re.fullmatch(r'[A-Z][A-Z0-9_]*', str(options['api_key_env'])):
        raise ValueError('api_key_env must name an environment variable, not contain a key')
    if options.get('price_per_1000_characters') is not None and (not number(options['price_per_1000_characters']) or options['price_per_1000_characters'] < 0):
        raise ValueError('Speech price must be a finite nonnegative per-1000-character estimate')
    if 'currency' in options and not re.fullmatch(r'[A-Z]{3}', str(options['currency'])):
        raise ValueError('Speech currency must be a three-letter uppercase code')
    if 'timeout_seconds' in options and (not number(options['timeout_seconds']) or not 1 <= options['timeout_seconds'] <= 900):
        raise ValueError('Speech timeout must be finite and between 1 and 900 seconds')
    if 'local_only' in options and not isinstance(options['local_only'], bool):
        raise ValueError('local_only must be a boolean')
    for key in ('voice_settings', 'dialogue_settings', 'generation_config', 'request_extra'):
        if key in options and not isinstance(options[key], dict):
            raise ValueError(f'{key} must be an object')
    # Arbitrary authentication in nested JSON would be persisted in request/cache receipts.
    def inspect(value):
        if isinstance(value, dict):
            if any(re.fullmatch(r'api[_-]?key|authorization|password|secret|token|(?:access|auth|api|bearer)[_-]?token|headers', str(key), re.I) for key in value):
                raise ValueError('Do not store credentials or authentication headers in speech configuration')
            for child in value.values():
                inspect(child)
        elif isinstance(value, list):
            for child in value:
                inspect(child)
    for key in ('voice_settings', 'dialogue_settings', 'generation_config', 'request_extra'):
        inspect(options.get(key, {}))


def validate_profile(profile):
    allowed = {'schema_version', 'provider', 'model', 'providers', 'cast', 'voice', 'speed', 'language', 'pause',
               'model_sha256', 'voices_sha256', 'spoken_forms', 'pronunciations'}
    if not isinstance(profile, dict) or set(profile) - allowed:
        raise ValueError('Unsupported narrator fields; use provider options and environment credential names')
    provider = profile.get('provider', 'kokoro')
    if provider not in PROVIDERS:
        raise ValueError('Unknown speech provider; choose a listed provider, custom-http or provided')
    if not isinstance(profile.get('providers', {}), dict) or not isinstance(profile.get('cast', {}), dict):
        raise ValueError('Speech providers and cast must be objects keyed by provider/speaker ID')
    for name, options in profile.get('providers', {}).items():
        if name not in PROVIDERS:
            raise ValueError('Unknown configured speech provider: ' + name)
        check_options(options)
    for speaker, record in profile.get('cast', {}).items():
        if not re.fullmatch(r'[A-Za-z0-9_-]+', speaker) or not isinstance(record, dict) or set(record) - VOICE_KEYS:
            raise ValueError('Cast entries use stable speaker IDs and provider/model/voice/language/speed/options only')
        if record.get('provider', provider) not in PROVIDERS:
            raise ValueError('Unknown cast speech provider: ' + speaker)
        check_options(record.get('options', {}))
    for speaker in ['NARRATOR', *profile.get('cast', {})]:
        voice_config(profile, speaker)


def voice_config(profile, speaker='NARRATOR'):
    cast = profile.get('cast', {}).get(speaker, {})
    provider = cast.get('provider', profile.get('provider', 'kokoro'))
    if provider not in PROVIDERS:
        raise ValueError('Unknown speech provider: ' + str(provider))
    options = dict(profile.get('providers', {}).get(provider, {}), **cast.get('options', {}))
    check_options(options)
    inherited = provider == profile.get('provider', 'kokoro')
    model = cast.get('model') or (profile.get('model') if inherited else None) or options.get('model') or PROVIDERS[provider]['model']
    if model is not None and (not isinstance(model, str) or not model):
        raise ValueError('Speech model IDs must be strings')
    voice = cast.get('voice') or (profile.get('voice') if inherited and (speaker == 'NARRATOR' or not cast) else None)
    speed, language = cast.get('speed', profile.get('speed', 1.0)), cast.get('language', profile.get('language', 'en-us'))
    if not number(speed) or not 0.5 <= speed <= 1.5 or not isinstance(language, str) or not language:
        raise ValueError('Speech needs a valid language and finite speed between 0.5 and 1.5')
    if voice is not None and (not isinstance(voice, str) or not voice.strip()):
        raise ValueError('Voice IDs must be nonempty strings or unanswered')
    return {'provider': provider, 'model': model, 'voice': voice, 'speed': speed, 'language': language, 'options': options}


def ready_problems(project, config, credentials=False, *, require_runtime=True):
    provider, options = config['provider'], config['options']
    errors = []
    common = {'model', 'timeout_seconds', 'max_characters', 'price_per_1000_characters', 'currency'}
    specific = {
        'kokoro': set(), 'provided': set(),
        'chatterbox': {'endpoint', 'reference_audio', 'model_fingerprint', 'temperature', 'exaggeration', 'cfg_weight'},
        'elevenlabs': {'api_key_env', 'voice_settings', 'dialogue_settings'},
        'inworld': {'api_key_env', 'delivery_mode'},
        'cartesia': {'api_key_env', 'api_version', 'generation_config'},
        'custom-http': {'endpoint', 'api_key_env', 'response_format', 'audio_json_key', 'auth_header', 'auth_prefix', 'request_extra', 'local_only'},
    }
    unused = set(options) - common - specific[provider]
    if unused:
        errors.append('Unsupported options for ' + provider + ': ' + ', '.join(sorted(unused)))
    if provider != 'chatterbox' and options.get('reference_audio'):
        errors.append('This adapter uses provider voice IDs or imported recordings; reference_audio is for local Chatterbox')
    if provider not in ('provided', 'chatterbox') and not config.get('voice'):
        errors.append('Choose a voice for ' + provider)
    if provider == 'kokoro':
        if not 0.7 <= config['speed'] <= 1.3:
            errors.append('Kokoro uses an auditioned speed between 0.7 and 1.3')
        if require_runtime:
            for name in ('model', 'voices'):
                path = ROOT / configuration(project)['runtime'][name]
                if not path.is_file():
                    errors.append('Kokoro ' + name + ' file is missing')
    elif provider == 'chatterbox':
        if not local_endpoint(options.get('endpoint', PROVIDERS[provider]['endpoint'])):
            errors.append('Chatterbox uses a loopback server; use custom-http for a remote gateway')
        if config['speed'] != 1:
            errors.append('The local Chatterbox adapter uses native speed 1.0; audition its actual generation controls')
        if not options.get('reference_audio'):
            errors.append('Choose a Chatterbox voice with a snapshotted reference_audio file')
        if options.get('reference_audio'):
            from project_records import artifact_path
            try:
                if not artifact_path(project, options['reference_audio']).is_file():
                    errors.append('Chatterbox reference_audio is missing')
            except ValueError as error:
                errors.append(str(error))
    elif provider == 'provided':
        if config['speed'] != 1:
            errors.append('Imported speech is used at its recorded speed 1.0')
    else:
        if provider != 'custom-http' and options.get('endpoint'):
            errors.append('Native provider URLs are fixed; use custom-http for a separately configured gateway')
        if not config['model']:
            errors.append('Choose an explicit model for ' + provider)
        if provider == 'cartesia' and options.get('api_version', PROVIDERS['cartesia']['api_version']) != PROVIDERS['cartesia']['api_version']:
            errors.append('This Cartesia adapter targets API 2026-08-14; update the adapter or use a custom gateway for another contract')
        if provider == 'custom-http':
            parsed = urlparse(options.get('endpoint', ''))
            if not local_endpoint(options.get('endpoint', '')) and (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment):
                errors.append('A custom speech endpoint must use HTTPS or loopback, with credentials in environment headers')
            if options.get('local_only') and not local_endpoint(options.get('endpoint', '')):
                errors.append('A local-only speech gateway must use a loopback address')
        if credentials:
            name = options.get('api_key_env', PROVIDERS[provider].get('api_key_env'))
            if (name and not os.environ.get(name)) or (not name and not local_endpoint(options.get('endpoint', ''))):
                errors.append('Set the selected speech credential environment variable: ' + str(name or 'api_key_env'))
    return errors


def remote(config):
    if config['provider'] == 'custom-http':
        return not (config['options'].get('local_only') is True and local_endpoint(config['options'].get('endpoint', '')))
    return not PROVIDERS[config['provider']]['local']


def http_request(config, text, direction='', previous='', following=''):
    """Public request recipe only. Authentication is attached at execution time."""
    provider, options = config['provider'], config['options']
    language = config['language'].replace('_', '-').split('-')[0]
    headers, field = {'Content-Type': 'application/json'}, None
    if provider == 'elevenlabs':
        if direction and not config['model'].startswith(('eleven_v3', 'eleven_v4')):
            raise ValueError('This ElevenLabs model does not support inline acting directions')
        spoken = ('[' + direction.strip('[]') + '] ' if direction else '') + text
        if config['model'].startswith('eleven_v4'):
            if len(spoken.encode('utf-16-le')) // 2 > 2000:
                raise ValueError('Eleven v4 dialogue turns must fit 2,000 characters including acting tags')
            url = 'https://api.elevenlabs.io/v1/text-to-dialogue?output_format=mp3_44100_128'
            body = {'inputs': [{'text': spoken, 'voice_id': config['voice']}], 'model_id': config['model']}
            if options.get('voice_settings'):
                raise ValueError('Eleven v4 dialogue uses dialogue_settings instead of single-speaker voice_settings')
            if options.get('dialogue_settings'):
                body['settings'] = options['dialogue_settings']
            if previous:
                body['previous_text'] = previous[-100:]
            if following:
                body['future_text'] = following[:100]
            if config['speed'] != 1:
                raise ValueError('Eleven v4 dialogue speed is directed through the performance; use speed 1.0')
        else:
            if options.get('dialogue_settings'):
                raise ValueError('This ElevenLabs speech endpoint uses voice_settings, not dialogue_settings')
            url = 'https://api.elevenlabs.io/v1/text-to-speech/' + quote(config['voice'], safe='') + '?output_format=mp3_44100_128'
            settings = dict(options.get('voice_settings', {}))
            if config['model'] != 'eleven_v3':
                settings['speed'] = config['speed']
            elif config['speed'] != 1:
                raise ValueError('Eleven v3 performance uses speed 1.0')
            body = {'text': spoken, 'model_id': config['model'], 'voice_settings': settings}
            if previous:
                body['previous_text'] = previous
            if following:
                body['next_text'] = following
        auth = ('xi-api-key', '')
        if config['model'] != 'eleven_multilingual_v2':
            body['language_code'] = language
    elif provider == 'inworld':
        url = 'https://api.inworld.ai/tts/v1/voice'
        if direction and config['model'] != 'inworld-tts-2':
            raise ValueError('This Inworld adapter uses TTS-2 steering; choose a supported model/control')
        instruction = direction.strip('[]')
        spoken = ('[' + (instruction if instruction.startswith('say ') else 'say ' + instruction) + '] ' if direction else '') + text
        if len(spoken.encode('utf-16-le')) // 2 > 2000:
            raise ValueError('Inworld synchronous turns must fit 2,000 UTF-16 code units; split at a meaningful boundary')
        body = {'text': spoken, 'voiceId': config['voice'], 'modelId': config['model'], 'language': config['language'],
                'audioConfig': {'audioEncoding': 'LINEAR16', 'speakingRate': config['speed']}}
        if options.get('delivery_mode'):
            if config['model'] != 'inworld-tts-2' or options['delivery_mode'] not in ('STABLE', 'BALANCED', 'CREATIVE'):
                raise ValueError('Inworld delivery_mode needs TTS-2 and STABLE, BALANCED or CREATIVE')
            body['deliveryMode'] = options['delivery_mode']
        auth, field = ('Authorization', 'Basic '), 'audioContent'
    elif provider == 'cartesia':
        url = 'https://api.cartesia.ai/tts/bytes'
        generation = dict(options.get('generation_config', {}), speed=config['speed'])
        if direction:
            if language != 'en':
                raise ValueError('Cartesia emotion controls in this adapter require English; audition other language controls separately')
            generation['emotion'] = direction
        body = {'model_id': config['model'], 'transcript': text, 'voice': config['voice'], 'language': language,
                'output_format': {'container': 'wav', 'encoding': 'pcm_s16le', 'sample_rate': 44100}, 'generation_config': generation}
        headers['Cartesia-Version'] = options.get('api_version', PROVIDERS['cartesia']['api_version'])
        auth = ('Authorization', 'Bearer ')
    else:
        url = options.get('endpoint', PROVIDERS[provider].get('endpoint', ''))
        body = dict(options.get('request_extra', {}))
        body.update(text=text, voice=config['voice'], model=config['model'], language=config['language'], speed=config['speed'], direction=direction)
        if provider == 'chatterbox':
            if direction and (config['model'] not in ('turbo', 'nano') or direction not in CHATTERBOX_TAGS):
                raise ValueError('Chatterbox directions support Turbo/Nano paralinguistic tags only; use native generation controls for emotion')
            body.update({key: options[key] for key in ('temperature', 'exaggeration', 'cfg_weight', 'reference_audio') if key in options})
        field = options.get('audio_json_key', 'audioContent') if options.get('response_format') == 'base64-json' else None
        auth = (options.get('auth_header', 'Authorization'), options.get('auth_prefix', 'Bearer '))
    return {'url': url, 'headers': headers, 'body': body, 'base64_field': field, 'auth': auth,
            'api_key_env': options.get('api_key_env', PROVIDERS[provider].get('api_key_env'))}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_audio(recipe, timeout=120):
    headers = dict(recipe['headers'])
    key_name = recipe['api_key_env']
    if key_name:
        key = os.environ.get(key_name)
        if not key:
            raise ValueError('Set the selected speech credential environment variable: ' + key_name)
        headers[recipe['auth'][0]] = recipe['auth'][1] + key
    try:
        request = Request(recipe['url'], data=json.dumps(recipe['body']).encode('utf-8'), headers=headers, method='POST')
        with build_opener(NoRedirect).open(request, timeout=timeout) as response:
            payload = response.read(64 * 1024 * 1024 + 1)
            if len(payload) > 64 * 1024 * 1024:
                raise ValueError('Speech response exceeds the supported request size')
            if key_name and os.environ[key_name].encode('utf-8') in payload:
                raise RuntimeError('The provider returned credential material; its response was not retained')
            request_id = response.headers.get('request-id') or response.headers.get('x-request-id')
    except HTTPError as error:
        raise RuntimeError(f'Speech provider returned HTTP {error.code}; no automatic request retry') from None
    except (URLError, TimeoutError, OSError):
        raise RuntimeError('Speech request failed or timed out; reconcile its provider outcome before retry') from None
    return payload, {'provider_request_id': request_id}


def decode_audio(recipe, payload):
    if recipe['base64_field']:
        try:
            value = json.loads(payload)
            for key in recipe['base64_field'].split('.'):
                value = value[key]
            payload = base64.b64decode(value, validate=True)
        except (ValueError, KeyError, TypeError):
            raise ValueError('The speech response did not contain valid encoded audio') from None
    return payload


def catalog():
    return [{'id': identity, **record, 'credential_required': bool(record.get('api_key_env')),
             'credential_present': bool(os.environ.get(record.get('api_key_env', ''))),
             'readiness': 'requires selected voice/model and configured runtime or account; not a live synthesis test'}
            for identity, record in PROVIDERS.items()]
