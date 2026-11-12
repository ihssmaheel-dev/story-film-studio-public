#!/usr/bin/env python3
"""CPU word alignment with independent recognition evidence and explicit uncertainty."""
import argparse
import difflib
import importlib.metadata
import math
from pathlib import Path
import re
import tempfile
import textwrap
import wave

from studio_common import atomic_json, executable, fingerprint, process, read_json, sha256_file, utc_now


def normalize(text, spoken_forms=None):
    text = text.replace('\u2019', "'")
    matches = list(re.finditer(r"[A-Za-z]+(?:'[A-Za-z]+)?|[0-9]+", text))
    records, normalized = [], []
    for index, match in enumerate(matches):
        token = match.group().lower()
        spoken = (spoken_forms or {}).get(token, token).lower().split()
        if any(re.search(r'\d', word) for word in spoken):
            raise ValueError(f'Provide the actual spoken form for numeral {token}; do not guess its pronunciation')
        records.append({'display': text[match.start():matches[index + 1].start() if index + 1 < len(matches) else len(text)],
                        'spoken': spoken, 'first': len(normalized), 'count': len(spoken)})
        normalized.extend(spoken)
    if not normalized:
        raise ValueError('No English transcript words found; configure a compatible aligner for the selected language')
    return normalized, records


def align_chunk(audio, text, offset=0.0, spoken_forms=None, pronunciations=None, ffmpeg=None):
    from pocketsphinx import Decoder
    words, tokens = normalize(text, spoken_forms)
    ffmpeg = ffmpeg or executable('ffmpeg')
    if not ffmpeg:
        raise ValueError('FFmpeg is required for alignment audio conversion')
    audio = Path(audio).resolve()
    with tempfile.TemporaryDirectory(prefix='.alignment-', dir=audio.parent) as directory:
        temporary = Path(directory).resolve()
        if temporary.parent != audio.parent:
            raise ValueError('Alignment scratch directory escaped its audio folder')
        pcm = temporary / 'speech.wav'
        process([ffmpeg, '-v', 'error', '-y', '-i', str(audio), '-ar', '16000', '-ac', '1',
                 '-c:a', 'pcm_s16le', str(pcm)])
        with wave.open(str(pcm), 'rb') as wav:
            samples = wav.readframes(wav.getnframes())
        independent = Decoder(samprate=16000, loglevel='ERROR')
        independent.start_utt()
        independent.process_raw(samples, full_utt=True)
        independent.end_utt()
        hypothesis = independent.hyp()
        recognized = hypothesis.hypstr.lower().split() if hypothesis else []
        matcher = difflib.SequenceMatcher(a=words, b=recognized, autojunk=False)
        corroborated = set()
        for block in matcher.get_matching_blocks():
            corroborated.update(range(block.a, block.a + block.size))
        decoder = Decoder(samprate=16000, loglevel='ERROR')
        for word, phones in (pronunciations or {}).items():
            decoder.add_word(word.lower(), phones)
        missing = sorted({word for word in words if not decoder.lookup_word(word)})
        if missing:
            raise ValueError('Alignment dictionary lacks ' + ', '.join(missing) + '; add verified pronunciations/spoken forms')
        decoder.set_align_text(' '.join(words))
        decoder.start_utt()
        decoder.process_raw(samples, full_utt=True)
        decoder.end_utt()
        segments = [segment for segment in decoder.seg() if not segment.word.startswith(('<', '['))]
        if len(segments) != len(words):
            raise ValueError('Forced alignment did not cover the complete transcript; manual inspection required')
        results = []
        for token in tokens:
            indices = list(range(token['first'], token['first'] + token['count']))
            first, last = segments[indices[0]], segments[indices[-1]]
            start, end = first.start_frame / 100, (last.end_frame + 1) / 100
            reasons = []
            if not all(index in corroborated for index in indices):
                reasons.append('independent recognition differs')
            if end - start < 0.03 or end - start > 2.0:
                reasons.append('unusual word duration')
            results.append({'text': token['display'].strip(), 'display': token['display'],
                            'start': round(offset + start, 4), 'end': round(offset + end, 4),
                            'confidence': round(sum(index in corroborated for index in indices) / len(indices), 3),
                            'confidence_type': 'uncalibrated independent-recognition agreement',
                            'requires_review': bool(reasons), 'reasons': reasons})
    return results, ' '.join(recognized)


def subtitle_cues(words):
    cues, group = [], []

    def flush():
        if group:
            text = ''.join(word['display'] for word in group).strip()
            lines = textwrap.wrap(text, width=42, break_long_words=False, break_on_hyphens=False)
            cues.append({'start': group[0]['start'], 'end': group[-1]['end'], 'text': '\n'.join(lines)})
            group.clear()

    for word in words:
        candidate = ''.join(item['display'] for item in group) + word['display']
        # Prefer sentence/phrase breaks; keep actual acoustic word boundaries.
        sentence_end = bool(group and re.search(r'[.!?]["\u201d\u2019\']?\s*$', group[-1]['display']))
        phrase_end = bool(group and re.search(r'[,;:]["\u201d\u2019\']?\s*$', group[-1]['display'])
                          and group[-1]['end'] - group[0]['start'] >= 1.5
                          and len(''.join(item['display'] for item in group).strip()) >= 20)
        natural_break = bool(group and group[-1]['end'] - group[0]['start'] >= 1.0
                             and (sentence_end or phrase_end))
        if group and (natural_break or word.get('chunk') != group[0].get('chunk') or len(candidate.strip()) > 80 or
                      word['end'] - group[0]['start'] > 6.0):
            flush()
        group.append(word)
    flush()
    return cues


def validate_alignment_text(turns, profile):
    """Fail on unsupported language/OOV words before synthesis."""
    from pocketsphinx import Decoder
    decoder = Decoder(samprate=16000, loglevel='ERROR')
    for word, phones in profile.get('pronunciations', {}).items():
        decoder.add_word(word.lower(), phones)
    missing = {}
    for turn in turns:
        language = turn.get('config', {}).get('language', profile.get('language', 'en-us')).lower().replace('_', '-')
        if language not in ('en', 'en-us', 'en-gb'):
            raise ValueError('The installed automatic aligner is English; configure compatible/manual alignment before synthesis')
        words, _ = normalize(turn['text'], profile.get('spoken_forms'))
        unknown = sorted({word for word in words if not decoder.lookup_word(word)})
        if unknown:
            missing[turn.get('id', 'transcript')] = unknown
    if missing:
        details = '; '.join(identity + ': ' + ', '.join(words) for identity, words in missing.items())
        raise ValueError('Alignment dictionary lacks ' + details + '; add verified pronunciations/spoken forms before synthesis')


def align_file(audio, transcript=None, profile=None):
    audio = Path(audio).resolve()
    profile = profile or {}
    if profile.get('language', 'en-us').lower().replace('_', '-') not in ('en', 'en-us', 'en-gb'):
        raise ValueError('The installed PocketSphinx model is English; use a compatible approved aligner for this language')
    chunk_path = audio.with_suffix('.chunks.json')
    if chunk_path.is_file():
        manifest = read_json(chunk_path)
        if manifest['audio_sha256'] != sha256_file(audio):
            raise ValueError('Speech changed since its chunk manifest; regenerate or rebuild the actual chunk records')
        chunks = manifest['chunks']
    elif transcript is not None:
        chunks = [{'file': str(audio), 'text': transcript, 'start': 0.0, 'sha256': sha256_file(audio)}]
    else:
        raise ValueError('A transcript or matching measured narration chunk manifest is required')
    all_words, hypotheses = [], []
    for index, chunk in enumerate(chunks):
        if chunk.get('language', profile.get('language', 'en-us')).lower().replace('_', '-') not in ('en', 'en-us', 'en-gb'):
            raise ValueError('This speech chunk needs a compatible language aligner or inspected manual alignment')
        source = Path(chunk['file'])
        if not source.is_absolute():
            source = audio.parent / source
        if chunk.get('sha256') != sha256_file(source):
            raise ValueError('Narration chunk checksum changed')
        cache = audio.parent / '.alignment-cache' / (fingerprint({
            'audio': chunk['sha256'], 'text': chunk['text'], 'spoken_forms': profile.get('spoken_forms'),
            'pronunciations': profile.get('pronunciations'), 'engine': importlib.metadata.version('pocketsphinx')}) + '.json')
        try:
            cached = read_json(cache, {})
        except (ValueError, OSError):
            cached = {}
        if cached and cached.get('checksum') == fingerprint({'words': cached.get('words'), 'hypothesis': cached.get('hypothesis')}):
            words, hypothesis = cached['words'], cached['hypothesis']
        else:
            words, hypothesis = align_chunk(source, chunk['text'], 0.0,
                                             profile.get('spoken_forms'), profile.get('pronunciations'))
            payload = {'words': words, 'hypothesis': hypothesis}
            atomic_json(cache, dict(payload, checksum=fingerprint(payload)))
        for word in words:
            word['chunk'] = index
            word['start'] = round(word['start'] + chunk['start'], 4)
            word['end'] = round(word['end'] + chunk['start'], 4)
        all_words.extend(words)
        hypotheses.append(hypothesis)
    uncertainty = [{'word_index': index, 'start': word['start'], 'end': word['end'],
                    'text': word['text'], 'reasons': word['reasons']}
                   for index, word in enumerate(all_words) if word['requires_review']]
    return {'schema_version': 1, 'method': 'pocketsphinx-forced-word-alignment',
            'engine_version': importlib.metadata.version('pocketsphinx'),
            'source_sha256': sha256_file(audio), 'words': all_words,
            'independent_hypotheses': hypotheses, 'uncertain_ranges': uncertainty,
            'manual_checks': [], 'status': 'review' if uncertainty else 'aligned',
            'subtitles': subtitle_cues(all_words)}


def reviewed_alignment(audio, review_override=None):
    audio = Path(audio).resolve()
    path = audio.with_suffix('.alignment.json')
    result = read_json(path)
    if result.get('source_sha256') != sha256_file(audio):
        raise ValueError('Alignment does not match the current speech file')
    review = read_json(audio.with_suffix('.alignment-review.json'), {}) if review_override is None else review_override
    if review:
        if review.get('audio_sha256') != sha256_file(audio) or review.get('alignment_sha256') != sha256_file(path):
            result['review_warning'] = 'Manual review belongs to different audio/alignment and must be renewed'
            return result
        selected = set(review.get('reviewed_indices', []))
        if any(not isinstance(index, int) or not 0 <= index < len(result['words']) for index in selected):
            raise ValueError('Review contains an invalid word index')
        from mix_audio import probe_duration
        duration = probe_duration(audio)
        for correction in review.get('corrections', []):
            index = correction['word_index']
            start, end = correction['start'], correction['end']
            if index not in selected or not all(isinstance(value, (int, float)) and math.isfinite(value) for value in (start, end)) or not 0 <= start < end <= duration:
                raise ValueError('Corrected words must be inspected indices with finite times inside the actual audio')
            result['words'][index].update(start=start, end=end)
        previous = 0.0
        for word in result['words']:
            if word['start'] < previous - 0.001 or word['end'] <= word['start']:
                raise ValueError('Manual alignment corrections overlap or reverse word order')
            previous = word['end']
        for interval in result['uncertain_ranges']:
            if interval['word_index'] in selected:
                interval['reviewed'] = True
                word = result['words'][interval['word_index']]
                interval.update(start=word['start'], end=word['end'])
        result['manual_checks'] = [review]
        result['subtitles'] = subtitle_cues(result['words'])
        result['status'] = 'review' if any(not item.get('reviewed') for item in result['uncertain_ranges']) else 'aligned'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audio', type=Path)
    parser.add_argument('--text-file', type=Path)
    parser.add_argument('--profile', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--apply-timeline', type=Path)
    parser.add_argument('--review-indices', nargs='+', type=int)
    parser.add_argument('--review-notes')
    parser.add_argument('--reviewer')
    parser.add_argument('--corrections', type=Path, help='Explicit manually inspected word_index/start/end corrections')
    args = parser.parse_args()
    try:
        if args.review_indices is not None:
            if not args.review_notes or not args.reviewer:
                raise ValueError('Record actual listening/inspection notes and reviewer for manual checks')
            raw = args.audio.with_suffix('.alignment.json')
            result = read_json(raw)
            if any(index < 0 or index >= len(result['words']) for index in args.review_indices):
                raise ValueError('Manual review word index outside the alignment')
            review = {
                'audio_sha256': sha256_file(args.audio), 'alignment_sha256': sha256_file(raw),
                'reviewed_indices': args.review_indices, 'notes': args.review_notes,
                'reviewer': args.reviewer, 'at': utc_now(),
                'corrections': read_json(args.corrections) if args.corrections else []}
            reviewed_alignment(args.audio, review_override=review)
            atomic_json(args.audio.with_suffix('.alignment-review.json'), review)
            print(args.audio.with_suffix('.alignment-review.json'))
            return
        transcript = args.text_file.read_text(encoding='utf-8-sig') if args.text_file else None
        result = align_file(args.audio, transcript, read_json(args.profile) if args.profile else None)
        output = args.output or args.audio.with_suffix('.alignment.json')
        atomic_json(output, result)
        if args.apply_timeline:
            timeline = read_json(args.apply_timeline)
            start = timeline.get('narration_start', 0.0)
            timeline['alignment'] = {key: value for key, value in result.items() if key not in ('words', 'subtitles')}
            timeline['subtitles'] = [dict(cue, start=cue['start'] + start, end=cue['end'] + start) for cue in result['subtitles']]
            atomic_json(args.apply_timeline, timeline)
        print(f'{output}: {len(result["words"])} aligned words; {len(result["uncertain_ranges"])} ranges require review')
    except (ValueError, OSError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
