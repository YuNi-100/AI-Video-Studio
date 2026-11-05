"""Gap-preserving deletion, common-gap closing and non-destructive snap moves."""
from bisect import bisect_left
from copy import deepcopy
from app.features.silence.sequence import sequence_clips, validate_sequence, project_captions


def union(intervals):
    merged=[]
    for a,b in sorted(intervals):
        if a>=b:continue
        if merged and a<=merged[-1][1]+.000001:merged[-1][1]=max(b,merged[-1][1])
        else:merged.append([a,b])
    return merged


def empty_parts(intervals,occupied):
    result=[]
    occupied=union(occupied)
    for a,b in union(intervals):
        parts=[(a,b)]
        for left,right in occupied:
            if left>=b:break
            if right<=a:continue
            rest=[]
            for x,y in parts:
                if right<=x or left>=y:rest.append((x,y))
                else:
                    if x<left:rest.append((x,left))
                    if right<y:rest.append((right,y))
            parts=rest
        result.extend(parts)
    return result


def finish(seq,clips,rows):
    return validate_sequence(dict(seq,clips=clips,timeline_captions=project_captions(seq,clips,rows)))


def shift_after_gaps(seq,clips,rows,gaps,tracks):
    def shift(time):return round(sum(b-a for a,b in gaps if b<=time+.000001),3)
    result=[]
    for c in clips:
        row=dict(c)
        if row['track'] in tracks:row['at']=round(row['at']-shift(row['at']),3)
        result.append(row)
    cues=[]
    for row in rows:
        row=dict(row)
        if not row.get('owner') and 'video' in tracks:
            delta=shift(row['start'])
            row.update(start=round(row['start']-delta,3),end=round(row['end']-delta,3))
        cues.append(row)
    return finish(seq,result,cues)


def delete_items(seq,indices,caption_indices=(),ripple=False):
    clips=sequence_clips(seq);rows=deepcopy(seq.get('timeline_captions',[]))
    targets={i for i in indices if type(i) is int and 0<=i<len(clips)}
    if seq.get('linked',True):
        groups={clips[i]['group'] for i in targets}
        targets|={i for i,c in enumerate(clips) if c['group'] in groups}
    selected={i for i in caption_indices if 0<=i<len(rows)}
    if not targets and not selected:raise ValueError('삭제할 컷 또는 자막을 선택하세요.')
    removed_video={clips[i]['group'] for i in targets if clips[i]['track']=='video'}
    surviving=[c for i,c in enumerate(clips) if i not in targets]
    cues=[r for i,r in enumerate(rows) if i not in selected and r.get('owner') not in removed_video]
    if not ripple or not targets:return finish(seq,surviving,cues)
    tracks={clips[i]['track'] for i in targets}
    spans=[(clips[i]['at'],clips[i]['at']+clips[i]['end']-clips[i]['start']) for i in targets]
    occupied=[(c['at'],c['at']+c['end']-c['start']) for c in surviving if c['track'] in tracks]
    if 'video' in tracks:occupied.extend((r['start'],r['end']) for r in cues)
    gaps=empty_parts(spans,occupied)
    return shift_after_gaps(seq,surviving,cues,gaps,tracks)


def gap_at(seq,position,track):
    tracks={'video','audio'} if seq.get('linked',True) else {track}
    occupied=[(c['at'],c['at']+c['end']-c['start']) for c in sequence_clips(seq) if c['track'] in tracks]
    if 'video' in tracks:occupied.extend((r['start'],r['end']) for r in seq.get('timeline_captions',[]))
    previous=0
    for a,b in union(occupied):
        if previous<=position<a:return round(previous,3),round(a,3)
        previous=max(previous,b)
    return None


def close_gap(seq,start,end,track):
    found=gap_at(seq,(start+end)/2,track)
    if found is None or abs(found[0]-start)>.001 or abs(found[1]-end)>.001:
        raise ValueError('선택한 빈칸이 바뀌었습니다. 빈칸을 다시 선택하세요.')
    tracks={'video','audio'} if seq.get('linked',True) else {track}
    return shift_after_gaps(seq,sequence_clips(seq),seq.get('timeline_captions',[]),[(start,end)],tracks)


def snap_move(seq,indices,delta_ms,tolerance_ms):
    clips=sequence_clips(seq);chosen={i for i in indices if 0<=i<len(clips)}
    if seq.get('linked',True):
        groups={clips[i]['group'] for i in chosen}
        chosen|={i for i,c in enumerate(clips) if c['group'] in groups}
    if not chosen:return None
    boundaries={};occupied={}
    minimum=min(clips[k]['at'] for k in chosen)
    for track in ('video','audio'):
        stationary=[c for i,c in enumerate(clips) if i not in chosen and c['track']==track]
        occupied[track]=[(round(c['at']*1000),round((c['at']+c['end']-c['start'])*1000)) for c in stationary]
        boundaries[track]=(sorted(round((c['at']+c['end']-c['start'])*1000) for c in stationary),
                           sorted(round(c['at']*1000) for c in stationary))
    options=[]
    for i in chosen:
        c=clips[i]
        for edge_index,(edge,values) in enumerate(zip((c['at'],c['at']+c['end']-c['start']),boundaries[c['track']])):
            if edge_index:
                left=round(c['at']*1000)+delta_ms;right=round((c['at']+c['end']-c['start'])*1000)+delta_ms
                if any(min(right,b)-max(left,a)>tolerance_ms for a,b in occupied[c['track']]):
                    continue  # A deep overlap means overwrite, even if the far edge aligns.
            predicted=round(edge*1000)+delta_ms
            index=bisect_left(values,predicted)
            for j in (index-1,index):
                if not 0<=j<len(values):continue
                distance=abs(values[j]-predicted);delta=values[j]-round(edge*1000)
                if distance<=tolerance_ms and minimum+delta/1000>=0:
                    options.append((distance,values[j],delta))
    if not options:return None
    _,guide,delta=min(options)
    return delta,guide


def safe_move(seq,indices,caption_indices,delta_ms):
    clips=sequence_clips(seq);selected=set(indices);rows=deepcopy(seq.get('timeline_captions',[]))
    if seq.get('linked',True):
        groups={clips[i]['group'] for i in selected}
        selected|={i for i,c in enumerate(clips) if c['group'] in groups}
    moving=[dict(c,at=round(c['at']+delta_ms/1000,3)) for i,c in enumerate(clips) if i in selected]
    if not moving:raise ValueError('붙일 컷을 선택하세요.')
    tracks={c['track'] for c in moving}
    left=min(c['at'] for c in moving);right=max(c['at']+c['end']-c['start'] for c in moving)
    stationary=[c for i,c in enumerate(clips) if i not in selected]
    if any(c['track'] in tracks and c['at']<left-.0005 and c['at']+c['end']-c['start']>left+.0005 for c in stationary):
        raise ValueError('다른 트랙의 컷이 붙일 경계에 걸쳐 있습니다. 공통 경계로 옮겨 주세요.')
    hits=[c['at'] for c in stationary if c['track'] in tracks and c['at']<right-.0005 and c['at']+c['end']-c['start']>left+.0005]
    anchor=min(hits) if hits else right
    shift=round(right-anchor,3) if hits else 0
    pushed={c['group'] for c in stationary if c['track'] in tracks and c['at']>=anchor-.0005} if shift else set()
    result=[]
    for i,c in enumerate(clips):
        if i in selected:result.append(dict(c,at=round(c['at']+delta_ms/1000,3)))
        elif shift and ((c['group'] in pushed and seq.get('linked',True)) or (c['track'] in tracks and c['at']>=anchor-.0005)):
            result.append(dict(c,at=round(c['at']+shift,3)))
        else:result.append(dict(c))
    moved_video={c['group'] for i,c in enumerate(clips) if i in selected and c['track']=='video'}
    for i,row in enumerate(rows):
        if i in caption_indices and row.get('owner') not in moved_video:
            row.update(start=round(row['start']+delta_ms/1000,3),end=round(row['end']+delta_ms/1000,3))
            if row.get('owner'):row.pop('owner');row['detached']=True
        elif not row.get('owner') and 'video' in tracks and shift and row['start']>=anchor and i not in caption_indices:
            row.update(start=round(row['start']+shift,3),end=round(row['end']+shift,3))
    return finish(seq,result,rows)
