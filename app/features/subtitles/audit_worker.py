"""Offline voice-activity comparison without transcription or text rewriting."""
import argparse,json,wave
from pathlib import Path
from app.features.subtitles.audit import audit_captions,merge_ranges
from app.features.silence.sequence import validate_sequence,sequence_sources,sequence_clips


def speech_ranges(path):
    import numpy as np
    from faster_whisper.vad import get_speech_timestamps,VadOptions
    result=[];base=0;rate=16000
    options=VadOptions(min_speech_duration_ms=250,min_silence_duration_ms=300,speech_pad_ms=100)
    with wave.open(str(path),'rb') as audio:
        while data:=audio.readframes(rate*30):
            samples=np.frombuffer(data,dtype=np.int16).astype(np.float32)/32768
            result.extend(((base+r['start'])/rate,(base+r['end'])/rate) for r in get_speech_timestamps(samples,options,sampling_rate=rate))
            base+=len(samples)
    return merge_ranges(result,.15)


def audio_window(sequence,start,end):
    clips=[]
    for c in sequence_clips(sequence):
        if c['track']!='audio':continue
        left=max(start,c['at']);right=min(end,c['at']+c['end']-c['start'])
        if right>left:
            clips.append(dict(c,at=round(left-start,3),start=round(c['start']+left-c['at'],3),end=round(c['start']+right-c['at'],3)))
    return dict(sequence,clips=clips,ranges=[],timeline_captions=[])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--request',required=True);args=parser.parse_args()
    def emit(value):print(json.dumps(value,ensure_ascii=False),flush=True)
    try:
        request=Path(args.request);data=json.loads(request.read_text(encoding='utf-8'))
        seq=validate_sequence(data['sequence']);speech=None;warning=''
        stamps={p:(Path(p).stat().st_size,Path(p).stat().st_mtime_ns) for p in sequence_sources(seq)} if data['audio'] else {}
        if data['audio']:
            emit(dict(type='status',text='작업본의 말소리 구간을 점검 중…'))
            try:
                from app.features.subtitles.sequence_audio import render_audio
                a=max(0,data['start']-1);b=min(data['duration'],data['end']+1)
                path=request.parent/'audit-audio.wav';render_audio(audio_window(seq,a,b),path,extent_seconds=b-a)
                speech=[(left+a,right+a) for left,right in speech_ranges(path)]
            except Exception as exc:
                warning='음성 점검을 완료하지 못해 자막 구조만 점검했습니다: '+str(exc)
        if any((Path(p).stat().st_size,Path(p).stat().st_mtime_ns)!=stamp for p,stamp in stamps.items()):raise ValueError('점검 중 원본 파일이 변경됐습니다.')
        findings=audit_captions(data['rows'],data['duration'],data['terms'],speech,data['start'],data['end'],data['language'])
        emit(dict(type='done',findings=findings,warning=warning,audio_checked=speech is not None));return 0
    except Exception as exc:emit(dict(type='error',text=str(exc)));return 1


if __name__=='__main__':raise SystemExit(main())
