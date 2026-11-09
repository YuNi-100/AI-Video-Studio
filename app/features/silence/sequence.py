"""Non-destructive source clips, timeline layout and ripple operations."""
from copy import deepcopy
import math
from pathlib import Path
from uuid import uuid4,uuid5,NAMESPACE_URL


def _number(value):
    return type(value) in (int,float) and math.isfinite(value)


def sequence_clips(sequence):
    if 'clips' in sequence:
        return deepcopy(sequence['clips'])
    clips, at = [], 0
    for i,(start,end) in enumerate(sequence['ranges']):
        for track in ('video','audio'):
            clips.append(dict(track=track,start=start,end=end,at=round(at,3),group=f'pair-{i}'))
        at=round(at+end-start,3)
    return clips


def validate_sequence(value):
    if not isinstance(value,dict):
        raise ValueError('시퀀스 정보가 올바르지 않습니다.')
    result={}
    for key,limit in (('id',64),('name',120),('source',32767)):
        text=value.get(key)
        if not isinstance(text,str) or not text.strip() or len(text)>limit or any(ord(c)<32 for c in text):
            raise ValueError('시퀀스 이름 또는 원본 정보가 올바르지 않습니다.')
        result[key]=text
    if 'view_base' in value:
        base=value['view_base']
        if not _number(base) or not 0<=base<=604800:raise ValueError('수정본 시작 기준이 올바르지 않습니다.')
        result['view_base']=float(base)
    if 'parent_id' in value:
        parent=value['parent_id']
        if not isinstance(parent,str) or not 0<len(parent)<=64 or parent==result['id']:raise ValueError('상위 편집본 정보가 올바르지 않습니다.')
        result['parent_id']=parent
    if 'scene_tags' in value:
        from app.features.scene_search import validate_tags
        result['scene_tags']=validate_tags(value['scene_tags'])
    duration=value.get('duration')
    if not _number(duration) or not 0<duration<=604800:
        raise ValueError('시퀀스 원본 길이가 올바르지 않습니다.')
    result['duration']=float(duration)
    if 'subtitle_run' in value:
        info=value['subtitle_run']
        if not isinstance(info,dict) or any(not isinstance(k,str) or not isinstance(v,(str,bool)) or len(str(v))>2000 for k,v in info.items()):raise ValueError('작업본 자막 생성 정보가 올바르지 않습니다.')
        result['subtitle_run']=deepcopy(info)
    if 'timeline_captions' in value:
        from app.features.subtitles.model import validate_segments
        rows=value['timeline_captions']
        clean=validate_segments(rows)
        for original,row in zip(rows,clean):
            if row['end']>604800:raise ValueError('자막 시간이 타임라인 범위를 벗어났습니다.')
            if 'id' in original:
                if not isinstance(original['id'],str) or not 0<len(original['id'])<=64:raise ValueError('자막 식별 정보가 올바르지 않습니다.')
                row['id']=original['id']
            if 'owner' in original:
                if not isinstance(original['owner'],str) or not 0<len(original['owner'])<=64:raise ValueError('자막 소속 정보가 올바르지 않습니다.')
                row['owner']=original['owner']
            if 'detached' in original:
                if type(original['detached']) is not bool:raise ValueError('자막 연결 정보가 올바르지 않습니다.')
                row['detached']=original['detached']
            if 'source_start' in original or 'source_end' in original:
                a,b=original.get('source_start'),original.get('source_end')
                if not _number(a) or not _number(b) or not 0<=a<b<=604800:raise ValueError('자막 원본 시간이 올바르지 않습니다.')
                row.update(source_start=float(a),source_end=float(b))
        ids=[r['id'] for r in clean if 'id' in r]
        if len(ids)!=len(set(ids)):raise ValueError('자막 식별 정보가 중복되었습니다.')
        result['timeline_captions']=clean
    if 'clips' in value:
        clips=value['clips']
        if not isinstance(clips,list) or len(clips)>20000:
            raise ValueError('시퀀스 컷 목록이 올바르지 않습니다.')
        clean=[]
        for c in clips:
            if not isinstance(c,dict) or c.get('track') not in ('video','audio'):
                raise ValueError('컷 트랙이 올바르지 않습니다.')
            if any(not _number(c.get(k)) for k in ('start','end','at')):
                raise ValueError('컷 시간이 올바르지 않습니다.')
            start,end,at=(round(c[k],3) for k in ('start','end','at'))
            limit=c.get('source_duration',duration)
            if not _number(limit) or not 0<limit<=604800:
                raise ValueError('컷 원본 길이가 올바르지 않습니다.')
            if not 0<=start<end<=limit+.000001 or not 0<=at or at+end-start>604800:
                raise ValueError('컷 시간이 원본 또는 타임라인 범위를 벗어났습니다.')
            group=c.get('group')
            if not isinstance(group,str) or not group or len(group)>64:
                raise ValueError('영상·음성 연결 정보가 올바르지 않습니다.')
            row=dict(track=c['track'],start=start,end=end,at=at,group=group)
            if 'family' in c:
                if not isinstance(c['family'],str) or not 0<len(c['family'])<=64:raise ValueError('컷 소속 정보가 올바르지 않습니다.')
                row['family']=c['family']
            if 'source' in c:
                if not isinstance(c['source'],str) or not c['source'] or len(c['source'])>32767 or '\0' in c['source']:
                    raise ValueError('컷 원본 경로가 올바르지 않습니다.')
                row.update(source=c['source'],source_duration=float(limit))
            if 'label' in c:
                from app.core.project import validate_display_name
                row['label']=validate_display_name(c['label'])
            if 'captions' in c:
                from app.features.subtitles.model import validate_segments
                row['captions']=validate_segments(c['captions'])
            clean.append(row)
        for track in ('video','audio'):
            previous=0
            groups=set()
            for c in sorted((c for c in clean if c['track']==track),key=lambda c:c['at']):
                if c['at']<previous-.0005 or c['group'] in groups:
                    raise ValueError('같은 트랙의 컷은 겹칠 수 없습니다.')
                groups.add(c['group'])
                previous=c['at']+c['end']-c['start']
        linked=value.get('linked',True)
        if type(linked) is not bool:
            raise ValueError('영상·음성 연결 설정이 올바르지 않습니다.')
        result.update(clips=clean,linked=linked)
        result['ranges']=[[c['start'],c['end']] for c in sorted(clean,key=lambda c:c['at']) if c['track']=='video']
    else:
        ranges=value.get('ranges')
        if not isinstance(ranges,list) or not 1<=len(ranges)<=10000:
            raise ValueError('시퀀스 구간 목록이 올바르지 않습니다.')
        result['ranges']=[]
        previous=0
        for pair in ranges:
            if not isinstance(pair,(tuple,list)) or len(pair)!=2 or any(not _number(v) for v in pair):
                raise ValueError('시퀀스 구간 시간이 올바르지 않습니다.')
            start,end=pair
            if not previous<=start<end<=duration or round(end*1000)<=round(start*1000):
                raise ValueError('시퀀스 구간 시간이 올바르지 않습니다.')
            result['ranges'].append([float(start),float(end)])
            previous=end
    kind=value.get('kind','sequence')
    if kind not in ('sequence','composition'):raise ValueError('편집본 종류가 올바르지 않습니다.')
    if 'kind' in value:result['kind']=kind
    if 'components' in value:
        from app.core.project import validate_display_name
        if not isinstance(value['components'],list) or len(value['components'])>1000:raise ValueError('조합 편집본 정보가 올바르지 않습니다.')
        result['components']=[validate_display_name(v) for v in value['components']]
    return result


def sequence_layout(sequence,subtitles=(),video_offset=0):
    blocks,cues,extent=[],[],0
    clips=sequence_clips(sequence)
    mixed=len({c.get('source',sequence['source']) for c in clips})>1
    groups={key:i+1 for i,key in enumerate(dict.fromkeys(c['group'] for c in sorted(clips,key=lambda c:c['at'])))}
    for i,c in enumerate(clips):
        start,end,at=c['start'],c['end'],c['at']
        left,right=round(at*1000),round((at+end-start)*1000)
        extent=max(extent,right)
        name=c.get("label") or (Path(c.get("source",sequence["source"])).stem+" · " if mixed else "")+f"컷 {groups[c['group']]}"
        blocks.append((c["track"],left,right,name,i))
        if c['track']=='video':
            path=c.get('source',sequence['source'])
            rows=c.get('captions',subtitles.get(path,[]) if isinstance(subtitles,dict) else subtitles)
            offset=0 if 'captions' in c else (video_offset.get(path,0) if isinstance(video_offset,dict) else video_offset)
            for caption_index,row in enumerate(rows):
                a,b=max(start,row['start']-offset),min(end,row['end']-offset)
                if a<b:
                    cues.append(dict(row,id=uuid5(NAMESPACE_URL,c['group']+':'+str(caption_index)).hex,owner=c['group'],source_start=round(max(0,row['start']-offset),3),source_end=round(row['end']-offset,3),start=round(at+a-start,3),end=round(at+b-start,3)))
    if 'timeline_captions' in sequence:
        cues=deepcopy(sequence['timeline_captions'])
        cues=attach_captions(clips,cues)
    cues.sort(key=lambda r:r['start'])
    extent=max([extent]+[round(c['end']*1000) for c in cues])
    return blocks,cues,extent


def sequence_source_ms(ranges,position):
    base=0
    for index,(start,end) in enumerate(ranges):
        if position<base+end-start:
            return start+max(0,position-base),index
        base+=end-start
    return (ranges[-1][1],len(ranges)-1) if ranges else (0,-1)


def track_source_ms(clips,track,position):
    for i,c in enumerate(clips):
        start,end,at=(round(c[k]*1000) for k in ('start','end','at'))
        if c['track']==track and at<=position<at+end-start:
            return start+position-at,i
    return None,None


def _targets(clips,index,linked):
    if not 0<=index<len(clips):
        raise ValueError('먼저 편집할 컷을 선택하세요.')
    c=clips[index]
    return [i for i,row in enumerate(clips) if i==index or (linked and row['group']==c['group'])]


def _finish(seq,clips):
    candidate=dict(seq,clips=clips,linked=seq.get('linked',True))
    if 'timeline_captions' in seq:
        candidate['timeline_captions']=project_captions(seq,clips,seq['timeline_captions'])
    return validate_sequence(candidate)


def attach_captions(clips,rows):
    """Assign legacy free captions to video intervals; explicit Alt edits stay free."""
    result=[]
    for r in rows:
        if r.get('owner') or r.get('detached'):
            result.append(dict(r));continue
        parts=[]
        for c in clips:
            if c['track']!='video':continue
            a=max(r['start'],c['at']);b=min(r['end'],c['at']+c['end']-c['start'])
            if a<b:parts.append(dict(r,owner=c['group'],source_start=round(max(0,c['start']+r['start']-c['at']),3),source_end=round(c['start']+r['end']-c['at'],3),start=round(a,3),end=round(b,3)))
        if len(parts)>1:
            for part in parts:part['id']=uuid5(NAMESPACE_URL,r.get('id',r['text'])+':'+part['owner']).hex
        result.extend(parts or [dict(r)])
    return sorted(result,key=lambda r:r['start'])


def project_captions(seq,clips,rows):
    """Keep caption source offsets fixed as their owning clips move or split."""
    original={c['group']:c for c in sequence_clips(seq) if c['track']=='video'}
    result=[]
    for row in rows:
        old=original.get(row.get('owner'))
        if old is None:
            result.append(dict(row));continue
        a=old['start']+row['start']-old['at'];b=old['start']+row['end']-old['at']
        for c in clips:
            if c['track']!='video' or c.get('family',c['group'])!=old.get('family',old['group']) or c.get('source',seq['source'])!=old.get('source',seq['source']):continue
            left=max(row.get('source_start',a) if c['group']==old['group'] else a,c['start'])
            right=min(row.get('source_end',b) if c['group']==old['group'] else b,c['end'])
            if left<right:
                item=dict(row,owner=c['group'],start=round(c['at']+left-c['start'],3),end=round(c['at']+right-c['start'],3))
                if c['group']!=row['owner']:item['id']=uuid5(NAMESPACE_URL,row.get('id',row['text'])+':'+c['group']).hex
                result.append(item)
    return sorted(result,key=lambda r:r['start'])


def edit_clip(seq,index,mode,delta_ms,ripple=False):
    clips=sequence_clips(seq)
    targets=_targets(clips,index,seq.get('linked',True))
    low,high=-604800.,604800.
    for i in targets:
        c=clips[i]; length=c['end']-c['start']
        previous=max((x['at']+x['end']-x['start'] for j,x in enumerate(clips) if j not in targets and x['track']==c['track'] and x['at']<c['at']),default=0)
        next_at=min((x['at'] for j,x in enumerate(clips) if j not in targets and x['track']==c['track'] and x['at']>=c['at']+length-.0005),default=604800)
        minimum=min(.1,length)
        if mode=='move':
            low=max(low,previous-c['at'])
            high=min(high,(604800 if ripple else next_at)-c['at']-length)
        elif mode=='start':
            low=max(low,-c['start'],previous-c['at'] if not ripple else -604800)
            high=min(high,length-minimum)
        elif mode=='end':
            low=max(low,minimum-length)
            high=min(high,c.get('source_duration',seq['duration'])-c['end'],next_at-c['at']-length if not ripple else 604800)
        else:
            raise ValueError('지원하지 않는 컷 편집입니다.')
    delta=round(max(low,min(high,delta_ms/1000)),3)
    if not delta:
        return _finish(seq,clips)
    original=deepcopy(clips)
    for i in targets:
        c,old=clips[i],original[i]
        if mode=='move': c['at']+=delta
        elif mode=='start':
            c['start']+=delta
            if not ripple: c['at']+=delta
        else: c['end']+=delta
        if ripple:
            shift=-delta if mode=='start' else delta
            for j,row in enumerate(clips):
                if j not in targets and row['track']==old['track'] and original[j]['at']>=old['at']+old['end']-old['start']-.0005:
                    row['at']+=shift
    return _finish(seq,clips)


def delete_clip(seq,index):
    clips=sequence_clips(seq)
    targets=_targets(clips,index,seq.get('linked',True))
    original=deepcopy(clips)
    for i in targets:
        c=original[i]; length=c['end']-c['start']
        for j,row in enumerate(clips):
            if j not in targets and row['track']==c['track'] and original[j]['at']>=c['at']+length-.0005:
                row['at']-=length
    return _finish(seq,[row for i,row in enumerate(clips) if i not in targets])


def split_clip(seq,index,position_ms):
    clips=sequence_clips(seq)
    targets=_targets(clips,index,seq.get('linked',True))
    position=round(position_ms/1000,3)
    group=uuid4().hex
    for i in targets:
        c=clips[i]
        if not c['at']+.0005<position<c['at']+c['end']-c['start']-.0005:
            raise ValueError('선택한 연결 컷 안으로 재생 위치를 옮겨 주세요.')
    result=[]
    for i,c in enumerate(clips):
        if i not in targets:
            result.append(c); continue
        source=round(c['start']+position-c['at'],3)
        result.extend((dict(c,end=source),dict(c,start=source,at=position,group=group,family=c.get('family',c['group']))))
    return _finish(seq,result)


def sequence_sources(seq):
    return {seq['source']} | {c.get('source',seq['source']) for c in sequence_clips(seq)}


def insert_sources(seq,items,position_ms,subtitles=None,video_offsets=None):
    """Insert full sources, splitting spanning clips and rippling both tracks."""
    position=round(max(0,position_ms)/1000,3)
    total=round(sum(duration for _,duration in items),3)
    original=sequence_clips(seq)
    result=[]
    split_groups={}
    for c in original:
        c=dict(c)
        end=round(c['at']+c['end']-c['start'],3)
        if c['at']>=position:
            c['at']=round(c['at']+total,3)
            result.append(c)
        elif end>position:
            source=round(c['start']+position-c['at'],3)
            group=split_groups.setdefault(c['group'],uuid4().hex)
            result.extend((dict(c,end=source),dict(c,start=source,at=round(position+total,3),group=group,family=c.get('family',c['group']))))
        else:
            result.append(c)
    at=position
    for path,duration in items:
        group=uuid4().hex
        for track in ('video','audio'):
            result.append(dict(track=track,source=path,source_duration=duration,start=0.,end=duration,at=at,group=group))
        at=round(at+duration,3)
    candidate=dict(seq,clips=result)
    if 'timeline_captions' in seq:
        rows=project_captions(seq,result,[r for r in seq['timeline_captions'] if r.get('owner')])
        for r in seq['timeline_captions']:
            if r.get('owner'):continue
            if r['start']>=position:rows.append(dict(r,start=round(r['start']+total,3),end=round(r['end']+total,3)))
            elif r['end']>position:
                rows.extend((dict(r,end=position),dict(r,id=uuid4().hex,start=round(position+total,3),end=round(r['end']+total,3))))
            else:rows.append(dict(r))
        base=position
        for path,duration in items:
            offset=(video_offsets or {}).get(path,0)
            for r in (subtitles or {}).get(path,[]):
                start=max(0,r['start']-offset);end=min(duration,r['end']-offset)
                if start<end:rows.append(dict(r,id=uuid4().hex,start=round(base+start,3),end=round(base+end,3)))
            base=round(base+duration,3)
        candidate['timeline_captions']=sorted(rows,key=lambda r:r['start'])
    return validate_sequence(candidate)


def combine_sequences(sequences,subtitles=None,placements=None,name='조합 편집본'):
    if not sequences:raise ValueError('조합할 편집본을 선택하세요.')
    subtitles=subtitles or {};placements=placements or {}
    clips=[];base=0;timeline_captions=[];scene_tags=[]
    explicit_captions=any('timeline_captions' in seq for seq in sequences)
    for seq in sequences:
        groups={};families={}
        for c in sequence_clips(seq):
            c=dict(c);source=c.get('source',seq['source'])
            old_group=c['group'];old_family=c.get('family',old_group)
            c.update(source=source,source_duration=c.get('source_duration',seq['duration']),at=round(c['at']+base,3),group=groups.setdefault(old_group,uuid4().hex),family=families.setdefault(old_family,uuid4().hex))
            if 'captions' not in c:
                offset=placements.get(source,0)
                c['captions']=[dict(r,start=round(max(0,r['start']-offset),3),end=round(r['end']-offset,3)) for r in subtitles.get(source,[]) if r['end']>offset]
            clips.append(c)
        if explicit_captions:
            for r in sequence_layout(seq,subtitles,placements)[1]:
                row=dict(r,id=uuid4().hex,start=round(r['start']+base,3),end=round(r['end']+base,3))
                if row.get('owner') in groups:row['owner']=groups[row['owner']]
                timeline_captions.append(row)
        scene_tags.extend(dict(t,start=round(t['start']+base,3),end=round(t['end']+base,3)) for t in seq.get('scene_tags',[]))
        base+=sequence_layout(seq)[2]/1000
    first=sequences[0]
    result=dict(id=uuid4().hex,name=name,source=first['source'],duration=first['duration'],clips=clips,ranges=[],linked=True,kind='composition',components=[s['name'] for s in sequences])
    if scene_tags:result['scene_tags']=scene_tags
    if explicit_captions:result['timeline_captions']=sorted(timeline_captions,key=lambda r:r['start'])
    return validate_sequence(result)

def splice_sequence(target,parts,position_ms,subtitles=None,placements=None):
    incoming=combine_sequences(parts,subtitles,placements)
    length=sequence_layout(incoming)[2]/1000
    position=round(position_ms/1000,3)
    result=[];groups={}
    for c in sequence_clips(target):
        c=dict(c);end=round(c['at']+c['end']-c['start'],3)
        if c['at']>=position:c['at']=round(c['at']+length,3);result.append(c)
        elif end>position:
            source=round(c['start']+position-c['at'],3)
            group=groups.setdefault(c['group'],uuid4().hex)
            result.extend((dict(c,end=source),dict(c,start=source,at=round(position+length,3),group=group,family=c.get('family',c['group']))))
        else:result.append(c)
    for c in incoming['clips']:result.append(dict(c,at=round(c['at']+position,3)))
    candidate=dict(target,clips=result,kind='composition',components=target.get('components',[target['name']])+[s['name'] for s in parts])
    if incoming.get('scene_tags'):
        candidate['scene_tags']=target.get('scene_tags',[])+[dict(t,start=round(t['start']+position,3),end=round(t['end']+position,3)) for t in incoming['scene_tags']]
    if 'timeline_captions' in target or 'timeline_captions' in incoming:
        original_cues=sequence_layout(target,subtitles or {},placements or {})[1]
        rows=project_captions(target,result,[r for r in original_cues if r.get('owner')])
        for row in original_cues:
            if row.get('owner'):continue
            r=dict(row)
            if r['start']>=position:r.update(start=round(r['start']+length,3),end=round(r['end']+length,3))
            elif r['end']>position:
                rows.append(dict(r,end=position))
                r.update(id=uuid4().hex,start=round(position+length,3),end=round(r['end']+length,3))
            rows.append(r)
        rows.extend(dict(r,id=uuid4().hex,start=round(r['start']+position,3),end=round(r['end']+position,3)) for r in sequence_layout(incoming)[1])
        candidate['timeline_captions']=sorted(rows,key=lambda r:r['start'])
    return validate_sequence(candidate)

def move_clips(seq,indices,delta_ms,ripple=False):
    clips=sequence_clips(seq);targets={i for i in indices if 0<=i<len(clips)}
    if not targets:raise ValueError('이동할 컷을 선택하세요.')
    if seq.get('linked',True):
        groups={clips[i]['group'] for i in targets};targets|={i for i,c in enumerate(clips) if c['group'] in groups}
    if ripple:
        for track in ('video','audio'):
            earliest=min((clips[i]['at'] for i in targets if clips[i]['track']==track),default=None)
            if earliest is not None:targets|={i for i,c in enumerate(clips) if c['track']==track and c['at']>=earliest}
    low,high=-604800.,604800.
    for i in targets:
        c=clips[i];end=c['at']+c['end']-c['start']
        previous=max((r['at']+r['end']-r['start'] for j,r in enumerate(clips) if j not in targets and r['track']==c['track'] and r['at']<c['at']),default=0)
        following=min((r['at'] for j,r in enumerate(clips) if j not in targets and r['track']==c['track'] and r['at']>=end-.0005),default=604800)
        low=max(low,(previous if ripple else 0)-c['at']);high=min(high,(following if ripple else 604800)-end)
    delta=round(max(low,min(high,delta_ms/1000)),3)
    for i in targets:clips[i]['at']=round(clips[i]['at']+delta,3)
    if not ripple:
        clips=_overwrite_clips(clips,targets)
    return _finish(seq,clips)


def _overwrite_clips(clips,targets):
    """Subtract moving intervals from stationary clips; preserve source handles."""
    result=[];split_groups={}
    for i,c in enumerate(clips):
        if i in targets:
            result.append(c);continue
        intervals=[(c['at'],round(c['at']+c['end']-c['start'],3))]
        for j in targets:
            moving=clips[j]
            if moving['track']!=c['track']:continue
            a=moving['at'];b=round(a+moving['end']-moving['start'],3)
            remaining=[]
            for left,right in intervals:
                if b<=left or a>=right:remaining.append((left,right))
                else:
                    if left<a:remaining.append((left,a))
                    if b<right:remaining.append((b,right))
            intervals=remaining
        for part,(left,right) in enumerate(intervals):
            group=c['group'] if part==0 else split_groups.setdefault((c['group'],left),uuid4().hex)
            result.append(dict(c,at=left,start=round(c['start']+left-c['at'],3),end=round(c['start']+right-c['at'],3),group=group,family=c.get('family',c['group'])))
    return result


def move_timeline_items(seq,indices,caption_indices,delta_ms,ripple=False,captions=None):
    """Move mixed selections with one bounded delta and one history transaction."""
    clips=sequence_clips(seq);indices={i for i in indices if 0<=i<len(clips)}
    rows=deepcopy(seq.get('timeline_captions',captions or []))
    selected={i for i in caption_indices if 0<=i<len(rows)}
    if not indices and not selected:raise ValueError('이동할 컷 또는 자막을 선택하세요.')
    if ripple and selected:
        first=min(rows[i]['start'] for i in selected)
        selected|={i for i,r in enumerate(rows) if r['start']>=first}
    if ripple and indices and 'timeline_captions' in seq:
        first=min(clips[i]['at'] for i in indices)
        selected|={i for i,r in enumerate(rows) if r['start']>=first}
    delta=delta_ms
    if selected:
        delta=max(delta,-round(min(rows[i]['start'] for i in selected)*1000))
        delta=min(delta,round((604800-max(rows[i]['end'] for i in selected))*1000))
    if indices:
        # The clip operation may clamp a negative ripple at the previous clip.
        result=move_clips(seq,indices,delta,ripple)
        group=clips[min(indices)]['group'];track=clips[min(indices)]['track']
        moved=next(c for c in sequence_clips(result) if c['group']==group and c['track']==track)
        delta=round((moved['at']-clips[min(indices)]['at'])*1000)
    else:result=deepcopy(seq)
    if selected or 'timeline_captions' in seq:
        old_groups={c['group']:c for c in clips if c['track']=='video'}
        moved_groups={c['group'] for c in sequence_clips(result) if c['track']=='video' and c['group'] in old_groups and c['at']!=old_groups[c['group']]['at']}
        for i in selected:
            if rows[i].get('owner') in moved_groups:continue
            rows[i]=dict(rows[i],start=round(rows[i]['start']+delta/1000,3),end=round(rows[i]['end']+delta/1000,3))
            if rows[i].get('owner'):
                rows[i].pop('owner',None);rows[i]['detached']=True
        result['timeline_captions']=project_captions(seq,sequence_clips(result),rows)
    return validate_sequence(result)


def delete_clips(seq,indices):
    clips=sequence_clips(seq)
    targets={i for i in indices if type(i) is int and 0<=i<len(clips)}
    if not targets:raise ValueError('삭제할 컷을 선택하세요.')
    identities=[(clips[i]['group'],clips[i]['track']) for i in sorted(targets,key=lambda i:clips[i]['at'],reverse=True)]
    result=seq
    for group,track in identities:
        index=next((i for i,c in enumerate(sequence_clips(result)) if c['group']==group and c['track']==track),None)
        if index is not None:result=delete_clip(result,index)
    return result
