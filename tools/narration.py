"""Persistent CPU narrator with content-addressed sentence caches and measured chunks."""
import importlib.metadata
from pathlib import Path
import re
import tempfile
import os

from studio_common import ROOT, atomic_json, configuration, fingerprint, read_json, sha256_file


class NarrationSession:
    def __init__(self, model=None, voices=None, cache=None):
        config = configuration()['runtime']
        self.model = Path(model or ROOT / config['model']).resolve()
        self.voices = Path(voices or ROOT / config['voices']).resolve()
        if not self.model.is_file() or not self.voices.is_file():
            raise ValueError('Kokoro model/voices missing; run studio setup/doctor')
        self.cache = Path(cache or ROOT / '.runtime/checks/tts-cache').resolve()
        self.cache.mkdir(parents=True, exist_ok=True)
        self.identity = {'model': sha256_file(self.model), 'voices': sha256_file(self.voices),
                         'engine': importlib.metadata.version('kokoro-onnx'),
                         'packages': sha256_file(ROOT / 'requirements.lock.txt')}
        self.engine = None
        self.cache_hits = 0
        self.generated_chunks = 0

    def sentence(self, text, voice, speed, language):
        import soundfile as sf
        identity = fingerprint(dict(self.identity, text=text, voice=voice, speed=speed, language=language))
        output, receipt = self.cache / (identity + '.wav'), self.cache / (identity + '.json')
        try:
            intact = output.is_file() and read_json(receipt, {}).get('sha256') == sha256_file(output)
        except (ValueError, OSError):
            intact = False
        if intact:
            self.cache_hits += 1
            return output
        if self.engine is None:
            from kokoro_onnx import Kokoro
            self.engine = Kokoro(str(self.model), str(self.voices))
        samples, rate = self.engine.create(text, voice=voice, speed=speed, lang=language)
        if not len(samples):
            raise ValueError('Narrator returned an empty sentence')
        sf.write(output, samples, rate, subtype='PCM_16')
        atomic_json(receipt, {'key': identity, 'sha256': sha256_file(output), 'rate': rate,
                              'frames': len(samples), 'identity': self.identity})
        self.generated_chunks += 1
        return output

    def render(self, text, output, voice='am_michael', speed=1.0, language='en-us', pause=0.15):
        import numpy as np
        import soundfile as sf
        output = Path(output).resolve()
        if output.suffix.lower() != '.wav' or output in (self.model, self.voices):
            raise ValueError('Narration output must be a separate .wav path')
        if not 0.7 <= speed <= 1.3 or not 0 <= pause <= 5:
            raise ValueError('Use an auditioned speed between 0.7 and 1.3, and a pause between 0 and 5 seconds')
        sentences = [value.strip() for value in re.split(r'(?<=[.!?])\s+|\n\s*\n', text.strip()) if value.strip()]
        if not sentences:
            raise ValueError('Narration text is empty')
        output.parent.mkdir(parents=True, exist_ok=True)
        chunks, cursor, rate = [], 0, None
        with tempfile.TemporaryDirectory(prefix='.tts-', dir=output.parent) as directory:
            temporary = Path(directory).resolve()
            if temporary.parent != output.parent:
                raise ValueError('Unexpected narration scratch directory')
            target, writer = temporary / 'speech.wav', None
            try:
                for index, sentence in enumerate(sentences):
                    cached = self.sentence(sentence, voice, speed, language)
                    samples, current_rate = sf.read(cached, dtype='float32')
                    if writer is None:
                        rate = current_rate
                        writer = sf.SoundFile(target, 'w', samplerate=rate, channels=1, subtype='PCM_16')
                    if current_rate != rate:
                        raise ValueError('Cached speech rates differ; rebuild affected chunks')
                    start = cursor / rate
                    writer.write(samples)
                    cursor += len(samples)
                    chunks.append({'text': sentence, 'file': Path(os.path.relpath(cached, output.parent)).as_posix(), 'sha256': sha256_file(cached),
                                   'start': start, 'end': cursor / rate})
                    if index < len(sentences) - 1:
                        frames = round(pause * rate)
                        writer.write(np.zeros(frames, dtype=np.float32))
                        cursor += frames
                    from progress_records import advance
                    advance(index + 1, len(sentences), 'clips', 'Assembling voice clips')
            finally:
                if writer is not None:
                    writer.close()
            target.replace(output)
        manifest = {'schema_version': 1, 'audio_sha256': sha256_file(output),
                    'duration': cursor / rate, 'sample_rate': rate, 'voice': voice, 'speed': speed,
                    'language': language, 'pause': pause, 'identity': self.identity,
                    'text_sha256': fingerprint(text), 'chunks': chunks,
                    'alignment_status': 'word_alignment_pending'}
        atomic_json(output.with_suffix('.chunks.json'), manifest)
        return manifest
