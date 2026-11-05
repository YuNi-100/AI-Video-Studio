"""Keep visible group/file rows synchronized with their canonical timeline."""
from copy import deepcopy
from app.features.edit_groups import asset_key,visible_edit,parts,file_view,merge_file_view
from app.features.silence.sequence import sequence_clips,validate_sequence


class EditGroups:
    def sync_group_children(self,parent):
        if not visible_edit(parent):return
        self.freeze_work_captions(parent)
        previous={s['source']:s for s in self.project.edit_sequences if s.get('parent_id')==parent['id']}
        children=[file_view(parent,path,previous.get(path)) for path in parts(parent)]
        self.project.edit_sequences[:]=[s for s in self.project.edit_sequences if s.get('parent_id')!=parent['id']]+children

    def sync_all_group_children(self):
        for parent in list(self.project.edit_sequences):
            if visible_edit(parent):self.sync_group_children(parent)

    def sync_committed_group(self,old,new):
        if old.get('parent_id'):
            parent=next((s for s in self.project.edit_sequences if s['id']==old['parent_id']),None)
            if parent is None:raise ValueError('상위 편집본이 없습니다.')
            candidate=merge_file_view(parent,old,new)
            index=self.project.edit_sequences.index(parent);self.project.edit_sequences[index]=candidate
            self.sync_group_children(candidate)
        elif visible_edit(new):self.sync_group_children(new)

    def asset_state(self,record):
        return next((s for s in self.project.edit_sequences if s['id']==asset_key(record)),None)

    def asset_part(self,record):
        seq=record.get('_work_state') or self.asset_state(record)
        if seq:
            result=deepcopy(seq);result["name"]=record["name"]
            result["clips"]=[dict(c,label=record["name"]) if c.get("source",seq["source"])==record["source"] else c for c in sequence_clips(seq)]
            return validate_sequence(result)
        duration=self.source_items([record['source']])[0][1]
        seq=validate_sequence(dict(id=asset_key(record),name=record['name'],source=record['source'],duration=duration,ranges=[[0,duration]]))
        self.freeze_work_captions(seq)
        return seq
