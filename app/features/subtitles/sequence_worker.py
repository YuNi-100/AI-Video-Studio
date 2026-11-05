"""Recognize the selected edit's audio without touching source caption data."""
import argparse,json,os
from pathlib import Path
from app.features.silence.sequence import validate_sequence,sequence_sources
from app.features.subtitles.sequence_audio import render_audio


def main():
    parser=argparse.ArgumentParser()
    for name in ('source','sequence','audio-output','model','language','cache'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--hotwords',default='');parser.add_argument('--vad',choices=('on','off'),default='off')
    parser.add_argument('--request')
    args=parser.parse_args()
    def emit(value):print(json.dumps(value,ensure_ascii=False),flush=True)
    try:
        seq=validate_sequence(json.loads(Path(args.sequence).read_text(encoding='utf-8')))
        stamps={p:(Path(p).stat().st_size,Path(p).stat().st_mtime_ns) for p in sequence_sources(seq)}
        emit(dict(type='status',text='선택한 작업본의 컷·음성·빈칸을 분석용으로 준비 중…'))
        duration=render_audio(seq,args.audio_output)
        completed=[]
        def guarded(value):
            if value.get('type')=='done':completed.append(value)
            else:emit(value)
        if args.request:
            from faster_whisper import WhisperModel
            from faster_whisper.audio import decode_audio
            from app.features.subtitles.recheck_worker import recognize_ranges
            from app.features.subtitles.recheck import validate_ranges
            from app.features.subtitles.model import validate_hotwords
            if args.model not in ('tiny','base','small','large-v3-turbo') or args.language not in ('auto','ko','en','ja'):raise ValueError('지원되지 않는 모델 또는 언어입니다.')
            ranges=validate_ranges(json.loads(Path(args.request).read_text(encoding='utf-8')),duration)
            model=WhisperModel(args.model,device='cpu',compute_type='int8',download_root=args.cache,cpu_threads=max(1,min(8,(os.cpu_count() or 2)-1)))
            variants=recognize_ranges(decode_audio(args.audio_output),model,ranges,args.language,validate_hotwords(args.hotwords),args.vad=='on',emit)
            completed.append(dict(type='done',segments=variants[0],run=dict(alternate=variants[1],model=args.model,language=args.language,hotwords=args.hotwords,skip_silence=args.vad=='on')))
        else:
            from app.features.subtitles.worker import transcribe
            transcribe(args.audio_output,args.model,args.language,Path(args.cache),guarded,hotwords=args.hotwords,skip_silence=args.vad=='on',_audio_input=True)
        if any((Path(p).stat().st_size,Path(p).stat().st_mtime_ns)!=stamp for p,stamp in stamps.items()):raise ValueError('처리 중 작업본의 원본 파일이 변경됐습니다. 다시 연결하세요.')
        for value in completed:emit(value)
        return 0
    except Exception as exc:
        emit(dict(type='error',text=f'{type(exc).__name__}: {exc}'));return 1


if __name__=='__main__':raise SystemExit(main())
