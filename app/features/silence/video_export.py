"""Local, non-destructive rendering of a completed edit to a new MP4."""
from pathlib import Path
from fractions import Fraction
import av
from app.features.silence.sequence import sequence_clips,sequence_layout


def probe_sources(sequence):
    clips=sequence_clips(sequence)
    paths=list(dict.fromkeys(c.get('source',sequence['source']) for c in clips))
    if not paths:raise ValueError('출력할 컷이 없습니다.')
    metadata={}
    for path in paths:
        with av.open(path) as container:
            if not container.streams.video:raise ValueError('영상 트랙이 없습니다: '+Path(path).name)
            stream=container.streams.video[0]
            frame=next(container.decode(video=0),None)
            if frame is None:raise ValueError('영상 프레임을 읽을 수 없습니다: '+Path(path).name)
            rotation=round(frame.rotation)%360
            width,height=stream.width,stream.height
            if rotation in (90,270):width,height=height,width
            stat=Path(path).stat()
            metadata[path]=dict(width=width,height=height,rotation=rotation,fps=str(stream.average_rate or Fraction(25)),audio=bool(container.streams.audio),stamp=(stat.st_size,stat.st_mtime_ns))
    return paths,metadata


def render_dimensions(sequence,metadata):
    video=sorted((c for c in sequence_clips(sequence) if c['track']=='video'),key=lambda c:c['at'])
    primary=metadata[video[0].get('source',sequence['source'])] if video else next(iter(metadata.values()))
    return max(2,primary['width']//2*2),max(2,primary['height']//2*2),primary['fps']


def render_filter(sequence,metadata,include_audio=True):
    clips=sequence_clips(sequence)
    paths=list(metadata)
    width,height,fps=render_dimensions(sequence,metadata)
    extent=sequence_layout(sequence)[2]/1000
    if not extent:raise ValueError('출력할 편집본이 비어 있습니다.')
    points=sorted({0.,extent}|{round(c['at'],3) for c in clips}|{round(c['at']+c['end']-c['start'],3) for c in clips})
    parts=[];inputs=[]
    for i,(start,end) in enumerate(zip(points,points[1:])):
        duration=round(end-start,3)
        if duration<=0:continue
        for track,suffix in ((('video','v'),('audio','a')) if include_audio else (('video','v'),)):
            c=next((c for c in clips if c['track']==track and c['at']<=start+.0001 and c['at']+c['end']-c['start']>=end-.0001),None)
            label=f'{suffix}{i}'
            if c:
                source=c.get('source',sequence['source']);index=paths.index(source)
                left=round(c['start']+start-c['at'],3);right=round(left+duration,3)
            if track=='video':
                if c:
                    parts.append(f'[{index}:v:0]trim=start={left:.3f}:end={right:.3f},setpts=PTS-STARTPTS,scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps},format=yuv420p[{label}]')
                else:parts.append(f'color=c=black:s={width}x{height}:r={fps}:d={duration:.3f},setsar=1[{label}]')
            else:
                if c and metadata[source]['audio']:
                    parts.append(f'[{index}:a:0]atrim=start={left:.3f}:end={right:.3f},asetpts=PTS-STARTPTS,aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo,apad,atrim=duration={duration:.3f}[{label}]')
                else:parts.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={duration:.3f},asetpts=PTS-STARTPTS[{label}]')
        inputs.append(f'[v{i}][a{i}]' if include_audio else f'[v{i}]')
    parts.append(''.join(inputs)+f'concat=n={len(inputs)}:v=1:a={int(include_audio)}[video]'+('[audio]' if include_audio else ''))
    return ';\n'.join(parts),extent
