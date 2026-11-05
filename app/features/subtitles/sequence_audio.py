"""Stream the edit's audio track to a disposable mono WAV, including gaps."""
import wave
import av
from app.features.silence.sequence import sequence_clips,sequence_layout

RATE=16000


def render_audio(sequence,destination):
    extent=round(sequence_layout(sequence)[2]/1000*RATE)
    if extent<=0:raise ValueError('음성을 분석할 편집 구간이 없습니다.')
    cursor=0
    with wave.open(str(destination),'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(RATE)
        def silence(count):
            while count>0:
                size=min(count,RATE*10);output.writeframesraw(bytes(size*2));count-=size
        for clip in sorted((c for c in sequence_clips(sequence) if c['track']=='audio'),key=lambda c:c['at']):
            at=round(clip['at']*RATE);length=round((clip['end']-clip['start'])*RATE)
            silence(max(0,at-cursor));cursor=max(cursor,at)
            written=0;source_start=round(clip['start']*RATE)
            with av.open(clip.get('source',sequence['source'])) as container:
                if container.streams.audio:
                    stream=container.streams.audio[0]
                    container.seek(max(0,int(clip['start']/stream.time_base)),stream=stream,backward=True)
                    resampler=av.AudioResampler(format='s16',layout='mono',rate=RATE)
                    for frame in container.decode(stream):
                        if frame.time is not None and frame.time>clip['end']+.1:break
                        for sample in resampler.resample(frame):
                            start=round(float(sample.pts*sample.time_base)*RATE) if sample.pts is not None else source_start+written
                            left=max(0,source_start+written-start);right=min(sample.samples,source_start+length-start)
                            if right<=left:continue
                            gap=max(0,start+left-source_start-written)
                            silence(gap);written+=gap
                            data=sample.to_ndarray().reshape(-1)[left:right].tobytes()
                            output.writeframesraw(data);written+=right-left
                        if written>=length:break
                    for sample in resampler.resample(None):
                        if written>=length:break
                        count=min(length-written,sample.samples)
                        output.writeframesraw(sample.to_ndarray().reshape(-1)[:count].tobytes());written+=count
            silence(max(0,length-written));cursor=at+max(length,written)
        silence(max(0,extent-cursor))
    return extent/RATE
