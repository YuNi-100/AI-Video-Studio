"""Independent snapshots of selected sets, packed without unselected gaps."""
from uuid import uuid4
from bisect import bisect_left
from app.features.silence.sequence import sequence_clips, sequence_layout, validate_sequence


def copy_sets(seq, indices, caption_indices=(), subtitles=None, offsets=None, whole_sets=True):
    clips = sequence_clips(seq)
    cues = sequence_layout(seq, subtitles or {}, offsets or {})[1]
    groups = {clips[i]['group'] for i in indices if 0 <= i < len(clips)}
    if whole_sets:groups |= {cues[i]['owner'] for i in caption_indices if 0 <= i < len(cues) and cues[i].get('owner')}
    groups &= {c['group'] for c in clips}
    chosen = [dict(c, source=c.get('source', seq['source']), source_duration=c.get('source_duration',seq['duration'])) for i,c in enumerate(clips) if (c['group'] in groups if whole_sets else i in indices)]
    rows = [dict(r) for i,r in enumerate(cues) if (whole_sets and r.get('owner') in groups) or i in caption_indices]
    video_groups={c['group'] for c in chosen if c['track']=='video'}
    for row in rows:
        if row.get('owner') not in video_groups:
            row.pop('owner',None)
            row['detached'] = True
    # Preserve intentional audio/video offsets within each selected set.
    bounds = {}
    for c in chosen:
        a,b = c['at'],c['at']+c['end']-c['start']
        left,right = bounds.get(c['group'],(a,b))
        bounds[c['group']] = (min(left,a),max(right,b))
    intervals = list(bounds.values())
    intervals += [(r['start'],r['end']) for r in rows if not r.get('owner')]
    merged = []
    for a,b in sorted(intervals):
        if merged and a <= merged[-1][1]+.000001:
            merged[-1][1] = max(b,merged[-1][1])
        else:
            merged.append([a,b])
    if not merged:
        raise ValueError('먼저 복사할 컷을 선택하세요.')
    ends = [b for a,b in merged]
    bases = []
    total = 0
    for a,b in merged:
        bases.append(total)
        total += b-a
    def packed(t):
        index = bisect_left(ends,t-.000001)
        if index == len(merged):
            return round(total,3)
        return round(bases[index]+max(0,t-merged[index][0]),3)
    for c in chosen:
        c['at'] = packed(c['at'])
    packed_rows = []
    for r in rows:
        packed_rows.append(dict(r,id=uuid4().hex,start=packed(r['start']),end=packed(r['end'])))
    source = chosen[0]['source'] if chosen else seq['source']
    duration = chosen[0]['source_duration'] if chosen else seq['duration']
    return validate_sequence(dict(id=uuid4().hex,name='복사한 컷',source=source,duration=duration,
        clips=chosen,linked=True,timeline_captions=sorted(packed_rows,key=lambda r:r['start'])))
