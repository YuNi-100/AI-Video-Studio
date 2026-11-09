"""File views of one canonical edit; views never duplicate source media."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid5,NAMESPACE_URL
from app.features.silence.sequence import sequence_clips,validate_sequence,project_captions


def asset_key(record):return 'asset-'+uuid5(NAMESPACE_URL,record['id']).hex


def visible_edit(seq):return not seq.get('parent_id') and not seq['id'].startswith('asset-')


def parts(seq):
    result=[]
    for clip in sorted(sequence_clips(seq),key=lambda c:c['at']):
        source=clip.get('source',seq['source'])
        if source not in result:result.append(source)
    return result


def file_view(parent,source,previous=None):
    clips=[c for c in sequence_clips(parent) if c.get('source',parent['source'])==source]
    if not clips:
        return validate_sequence(dict(previous,clips=[],ranges=[],timeline_captions=[])) if previous else None
    base=min((previous or {}).get('view_base',min(c['at'] for c in clips)),min(c['at'] for c in clips));groups={c['group'] for c in clips}
    old_ids={r.get('id') for r in (previous or {}).get('timeline_captions',[]) if r.get('id')}
    videos=[c for c in sequence_clips(parent) if c['track']=='video']
    rows=[]
    for row in parent.get('timeline_captions',[]):
        owner=next((c for c in videos if c['at']<=row['start']<c['at']+c['end']-c['start']),None)
        if row.get('owner') in groups or (not row.get('owner') and (row.get('id') in old_ids or owner and owner.get('source',parent['source'])==source)):
            rows.append(dict(row,start=round(row['start']-base,3),end=round(row['end']-base,3)))
    value=dict(id=(previous or {}).get('id','part-'+uuid5(NAMESPACE_URL,parent['id']+':'+source).hex),
        name=next((c['label'] for c in clips if c.get('label')),Path(source).name)[:120],source=source,
        duration=next((c['source_duration'] for c in clips if 'source_duration' in c),parent['duration']),
        parent_id=parent['id'],view_base=base,ranges=[],clips=[dict(c,at=round(c['at']-base,3)) for c in clips],
        timeline_captions=rows,linked=parent.get('linked',True))
    if previous:
        for field in ('subtitle_run','scene_tags'):
            if field in previous:value[field]=deepcopy(previous[field])
    return validate_sequence(value)


def merge_file_view(parent,old,new):
    source=old['source'];clips=sequence_clips(parent)
    chosen=[c for c in clips if c.get('source',parent['source'])==source]
    base=old.get('view_base',min((c['at'] for c in chosen),default=0))
    end=max((c['at']+c['end']-c['start'] for c in chosen),default=base)
    incoming=sequence_clips(new)
    extent=max((c['at']+c['end']-c['start'] for c in incoming),default=0)
    delta=round(extent-(end-base),3)
    remaining=[dict(c,at=round(c['at']+(delta if c['at']>=end-.000001 else 0),3)) for c in clips if c.get('source',parent['source'])!=source]
    combined=remaining+[dict(c,at=round(c['at']+base,3),source=c.get('source',new['source']),source_duration=c.get('source_duration',new['duration'])) for c in incoming]
    groups={c['group'] for c in chosen};ids={r.get('id') for r in old.get('timeline_captions',[]) if r.get('id')}
    rows=[deepcopy(r) for r in parent.get('timeline_captions',[]) if r.get('owner') not in groups and r.get('id') not in ids]
    for row in rows:
        if not row.get('owner') and row['start']>=end-.000001:row.update(start=round(row['start']+delta,3),end=round(row['end']+delta,3))
    rows=project_captions(parent,combined,rows)
    rows.extend(dict(r,start=round(r['start']+base,3),end=round(r['end']+base,3)) for r in new.get('timeline_captions',[]))
    return validate_sequence(dict(parent,clips=combined,timeline_captions=sorted(rows,key=lambda r:r['start'])))
