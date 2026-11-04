"""Isolated recheck worker: two candidates, source-time crops, no project writes."""
import argparse
import json
import os
from pathlib import Path
from app.core.media import validate_video
from app.features.subtitles.model import validate_hotwords, validate_segments
from app.features.subtitles.recheck import validate_ranges


def recognize_ranges(audio, model, ranges, language, hotwords, skip_silence, emit):
    duration = len(audio)/16000
    ranges = validate_ranges(ranges, duration)
    variants = [[], []]
    for index, (a, b) in enumerate(ranges):
        left, right = max(0, a-2), min(duration, b+2)
        clip = audio[round(left*16000):round(right*16000)]
        for variant, terms in enumerate((hotwords, '')):
            if variant and not hotwords:
                variants[1].extend(dict(row) for row in variants[0] if row['start'] < b and row['end'] > a)
                continue
            segments, info = model.transcribe(clip, language=None if language=='auto' else language,
                beam_size=5, vad_filter=skip_silence, condition_on_previous_text=False,
                hotwords=terms or None, word_timestamps=True)
            for segment in segments:
                words = [w for w in (getattr(segment, 'words', None) or [])
                         if w.end+left > a and w.start+left < b]
                if getattr(segment, 'words', None):
                    if not words:
                        continue
                    text = ''.join(w.word for w in words).strip()
                    start, end = words[0].start+left, words[-1].end+left
                else:
                    text = segment.text.strip()
                    start, end = segment.start+left, segment.end+left
                start, end = round(float(max(a, start)), 3), round(float(min(b, end)), 3)
                if text and start < end:
                    row = dict(start=start, end=end, text=text)
                    for key in ('avg_logprob', 'no_speech_prob'):
                        if hasattr(segment, key):
                            row[key] = float(getattr(segment, key))
                    variants[variant].append(row)
                    if len(variants[variant]) > 50000:
                        raise ValueError('후보 자막이 최대 개수를 초과했습니다.')
            emit(dict(type='status', text=f'구간 {index+1}/{len(ranges)} · '+('힌트 제외 후보' if variant else '기본 후보')+' 분석 완료'))
    return [validate_segments(sorted(rows, key=lambda r:r['start'])) for rows in variants]


def main():
    parser = argparse.ArgumentParser()
    for key in ('source', 'model', 'language', 'cache', 'request'):
        parser.add_argument('--'+key, required=True)
    parser.add_argument('--hotwords', default='')
    parser.add_argument('--vad', choices=('on','off'), default='off')
    args = parser.parse_args()
    def emit(value):
        print(json.dumps(value, ensure_ascii=False), flush=True)
    try:
        source = validate_video(args.source)
        if args.model not in ('tiny','base','small','large-v3-turbo') or args.language not in ('auto','ko','en','ja'):
            raise ValueError('지원되지 않는 모델 또는 언어입니다.')
        terms = validate_hotwords(args.hotwords)
        request = Path(args.request)
        if request.stat().st_size > 2*1024*1024:
            raise ValueError('재검토 요청이 너무 큽니다.')
        ranges = json.loads(request.read_text(encoding='utf-8'))
        emit(dict(type='status', text='재검토 모델·음성 준비 중…'))
        from faster_whisper import WhisperModel
        from faster_whisper.audio import decode_audio
        model = WhisperModel(args.model, device='cpu', compute_type='int8', download_root=args.cache,
                             cpu_threads=max(1, min(8, (os.cpu_count() or 2)-1)))
        audio = decode_audio(str(source))
        candidates = recognize_ranges(audio, model, ranges, args.language, terms, args.vad=='on', emit)
        emit(dict(type='done', segments=candidates[0], run=dict(alternate=candidates[1], ranges=ranges,
            model=args.model, language=args.language, hotwords=terms, skip_silence=args.vad=='on')))
        return 0
    except Exception as exc:
        emit(dict(type='error', text=f'{type(exc).__name__}: {exc}'))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
