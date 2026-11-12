#!/usr/bin/env python3
"""Synthesize CPU narration with approved settings and cached sentence audio."""
import argparse
from pathlib import Path
from narration import NarrationSession
from studio_common import hash_session, read_json, require_authorized_work


@hash_session()
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--text')
    source.add_argument('--text-file', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--voice')
    parser.add_argument('--speed', type=float)
    parser.add_argument('--lang')
    parser.add_argument('--model', type=Path)
    parser.add_argument('--voices', type=Path)
    parser.add_argument('--pause', type=float)
    parser.add_argument('--purpose', choices=('final', 'audition'), default='final')
    args = parser.parse_args()
    try:
        project = require_authorized_work(args.output, args.purpose, 'kokoro')
        profile = read_json(project / 'audio/narrator.json') if project else {}
        if project and args.purpose == 'final' and (profile.get('provider', 'kokoro') != 'kokoro' or profile.get('cast')):
            raise ValueError('tts_kokoro cannot replace the selected provider/cast; use studio speech')
        requested = {'voice': args.voice, 'speed': args.speed, 'language': args.lang, 'pause': args.pause}
        if project and args.purpose == 'final':
            for key, value in requested.items():
                if value is not None and profile.get(key) != value:
                    raise ValueError(f'{key} conflicts with G5 narrator settings; revise and approve first')
        profile = dict({'voice': 'am_michael', 'speed': 1.0, 'language': 'en-us', 'pause': 0.15}, **profile)
        profile.update({key: value for key, value in requested.items() if value is not None})
        cache = project / 'production/cache/tts' if project else args.output.parent / '.tts-cache'
        session = NarrationSession(args.model, args.voices, cache)
        text = args.text if args.text is not None else args.text_file.read_text(encoding='utf-8-sig')
        if project and args.purpose == 'final':
            if profile.get('model_sha256') != session.identity['model'] or profile.get('voices_sha256') != session.identity['voices']:
                raise ValueError('Actual model/voice files conflict with the G5-approved checksums')
            part = next((parent for parent in args.output.resolve().parents if parent.parent == project / 'parts'), None)
            if part is None or text.split() != (part / 'narration.txt').read_text(encoding='utf-8-sig').split():
                raise ValueError('Final speech must match the approved narration.txt of its planned part')
            if read_json(part / 'speech.json', {}).get('utterances'):
                raise ValueError('Use studio speech to honor the written speaker turns and performance controls')
            timeline = read_json(part / 'timeline.json')
            if not timeline.get('narration_file') or args.output.resolve() != (part / timeline['narration_file']).resolve():
                raise ValueError('Final speech output must be the narration path declared in the part timeline')
        if not profile.get('voice'):
            raise ValueError('Choose an audition voice or approve the final narrator voice before synthesis')
        result = session.render(text, args.output, profile['voice'], profile['speed'], profile['language'], profile['pause'])
        print(f'{args.output}: {result["duration"]:.3f}s; {session.cache_hits} cached, {session.generated_chunks} generated chunks')
    except (ValueError, OSError, ImportError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
