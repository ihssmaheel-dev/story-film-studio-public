#!/usr/bin/env python3
"""Generate authorized speech with the selected provider and cast; never switch providers."""
import argparse
from pathlib import Path

from speech import SpeechSession
from speech_providers import PROVIDERS
from voice_cast import audition_profile
from studio_common import find_project, hash_session, read_json, require_authorized_work


@hash_session()
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path)
    parser.add_argument('--part', default='part_001')
    parser.add_argument('--purpose', choices=('final', 'audition'), default='final')
    parser.add_argument('--text-file', type=Path, help='Audition text; final speech uses the declared part script')
    parser.add_argument('--output', type=Path, help='Audition WAV inside the project; final uses the timeline path')
    parser.add_argument('--provider', choices=tuple(PROVIDERS), help='Audition override only; configure final choices once')
    parser.add_argument('--voice', help='Audition override only')
    parser.add_argument('--model', help='Audition model override only')
    parser.add_argument('--speaker', help='Audition the selected NARRATOR or CHAR-### voice')
    args = parser.parse_args()
    project = args.project.resolve()
    from workflow import selected_parts
    try:
        part = selected_parts(project, [args.part])[0]
        profile = read_json(project / 'audio/narrator.json')
        if args.purpose == 'final':
            if args.text_file or args.provider or args.voice or args.model or args.speaker or args.output:
                raise ValueError('Configure final provider/voice in narrator.json; use the exact part text and timeline output')
            timeline = read_json(part / 'timeline.json')
            if not timeline.get('narration_file'):
                raise ValueError('This part has no speech scope')
            output, text_file, script = part / timeline['narration_file'], part / 'narration.txt', part / 'speech.json'
        else:
            if not args.output or not args.text_file:
                raise ValueError('Auditions require actual --text-file and --output paths')
            output, text_file, script = args.output.resolve(), args.text_file, None
            profile = audition_profile(profile, args.speaker or 'NARRATOR', args.provider, args.voice, args.model)
        if not output.resolve().is_relative_to(project) or find_project(output) != project:
            raise ValueError('Speech output must belong to this actual story project')
        session = SpeechSession(project, profile, purpose=args.purpose)
        text = text_file.read_text(encoding='utf-8-sig')
        from progress_records import task
        identity = ('narration:' if args.purpose == 'final' else 'audition:') + part.name
        with task(project, identity):
            result = session.render(text, output, script=script, part_id=part.name)
        print(f'{output}: {result["duration"]:.3f}s; {session.cache_hits} cached, {session.generated_chunks} generated clips')
    except (ValueError, OSError, RuntimeError, ImportError, KeyError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
