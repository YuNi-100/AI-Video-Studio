"""Named non-destructive silence-cut sequences in the timeline tab strip."""
from copy import deepcopy
from uuid import uuid4
from pathlib import Path
from PySide6.QtCore import QSignalBlocker
from app.features.timeline_actions import delete_items, gap_at, close_gap, snap_move, safe_move
from app.features.silence.sequence import validate_sequence, sequence_layout, sequence_clips, edit_clip, delete_clip, split_clip, sequence_sources, move_clips, delete_clips, move_timeline_items


class EditSequenceWorkflow:
    def active_sequence(self):
        return next((s for s in self.project.edit_sequences if s['id']==self.active_edit_id),None)

    def sync_sequence_tabs(self):
        self.sync_all_group_children()
        tabs = self.timeline.sequence_tabs
        desired = [(None,'원본')] + [(s['id'],s['name']) for s in self.project.edit_sequences if s['id'] not in self.closed_sequence_ids and (not s.get('parent_id') and not s['id'].startswith('asset-') or s['id'] in (self.active_edit_id,getattr(self,'_requested_edit_id',None)))]
        existing = [(tabs.tabData(i),tabs.tabText(i)) for i in range(tabs.count())]
        if desired != existing:
            with QSignalBlocker(tabs):
                while tabs.count()>1:
                    tabs.removeTab(tabs.count()-1)
                for key,name in desired[1:]:
                    i=tabs.addTab(name)
                    tabs.setTabData(i,key)
                    self.timeline.add_sequence_close(i)
                    seq=next(s for s in self.project.edit_sequences if s['id']==key)
                    tabs.setTabToolTip(i,seq['source'])
                tabs.setCurrentIndex(next((i for i,(key,_) in enumerate(desired) if key==self.active_edit_id),0))
        index=next((i for i,(key,_) in enumerate(desired) if key==self.active_edit_id),0)
        with QSignalBlocker(tabs):
            tabs.setCurrentIndex(index)
        listing=self.timeline.sequence_list
        with QSignalBlocker(listing):
            listing.clear()
            listing.addItem('원본')
            for seq in self.project.edit_sequences:
                if (seq.get('parent_id') or seq['id'].startswith('asset-')) and seq['id']!=self.active_edit_id:continue
                count=sum(c['track']=='video' for c in sequence_clips(seq))
                listing.addItem(f"{seq['name']} · {count}컷")
                listing.item(listing.count()-1).setToolTip(seq['source'])
            listing.setCurrentRow(index)
        tabs.setVisible(bool(self.project.edit_sequences))
        seq=self.active_sequence()
        self.timeline.current_edit.setText('현재 편집 중: '+seq['name'] if seq else '원본 보기')
        self.timeline.current_edit.setToolTip(self.timeline.current_edit.text())
        self.sync_workspace_ui()

    def create_edit_sequence(self, source, ranges, duration):
        if len(self.project.edit_sequences)>=1000:
            self.statusBar().showMessage('시퀀스는 최대 1000개입니다.')
            return
        number=1
        names={s['name'] for s in self.project.edit_sequences}
        while f'무음 컷 {number}' in names:
            number+=1
        seq=validate_sequence(dict(id=uuid4().hex,name=f'무음 컷 {number}',source=source,
                                   ranges=[list(pair) for pair in ranges],duration=duration))
        self.freeze_work_captions(seq)
        self.project.edit_sequences.append(seq)
        self.assign_edit_folder(seq["id"])
        self.closed_sequence_ids.discard(seq["id"])
        self.mark_dirty()
        index=next(i for i in range(self.timeline.sequence_tabs.count()) if self.timeline.sequence_tabs.tabData(i)==seq['id'])
        self.timeline.sequence_tabs.setCurrentIndex(index)
        self.statusBar().showMessage(f"{seq['name']} 생성 · {len(ranges)}개 컷 · 프로젝트를 저장하세요.")

    def select_edit_sequence(self, index):
        tabs=self.timeline.sequence_tabs
        old=self.active_edit_id
        target=next((s for s in self.project.edit_sequences if s['id']==tabs.tabData(index)),None)
        if target and any(not Path(path).is_file() for path in sequence_sources(target)):
            with QSignalBlocker(tabs):
                tabs.setCurrentIndex(next((i for i in range(tabs.count()) if tabs.tabData(i)==old),0))
            self.sync_sequence_tabs()
            self.focus_active_sequence_in_list()
            self.statusBar().showMessage('시퀀스 원본을 찾을 수 없습니다. 미디어 목록에서 파일 찾기를 사용하세요.')
            return
        if self.subtitle_job.busy or not self.resolve_subtitle_edit():
            with QSignalBlocker(tabs):
                tabs.setCurrentIndex(next((i for i in range(tabs.count()) if tabs.tabData(i)==old),0))
            self.sync_sequence_tabs()
            self.focus_active_sequence_in_list()
            return
        self.abort_timeline_scrub()
        self.pending_seek=None
        if self.preview._playing:
            self.preview.toggle_play()
        self.active_edit_id=tabs.tabData(index)
        self.timeline.canvas.selected_gap=None
        self.timeline.canvas.selected_keys=set()
        self.timeline.canvas.individual_selection=False
        self.timeline.canvas.selected_subtitles=set()
        self.timeline.canvas.selected_clip=None
        self.timeline.canvas.selected_track=None
        self.timeline.canvas.preview_blocks=None
        self.timeline.canvas.preview_segments=None
        self.sync_sequence_tabs()
        seq=self.active_sequence()
        if seq and seq['source']!=str(self.preview.source):
            self._opening_edit_sequence=True
            try:
                self.media.restore(self.media.paths(),seq['source'],self.media.names())
                self.open_media(seq['source'])
            finally:
                self._opening_edit_sequence=False
        self.show_source_subtitles(force=True)
        self.focus_active_sequence_in_list()
        if self.preview.ready:
            self.preview.seek_timeline(0)
        self.timeline.set_position(0)
        self.update_subtitle_controls()

    def close_edit_sequence(self, index):
        if index<=0 or self.subtitle_job.busy or not self.resolve_subtitle_edit():
            return
        key=self.timeline.sequence_tabs.tabData(index)
        if key==self.active_edit_id:
            self.timeline.sequence_tabs.setCurrentIndex(0)
        self.closed_sequence_ids.add(key)
        self.sync_sequence_tabs()

    def render_edit_sequence(self):
        seq=self.active_sequence()
        if seq is None:
            return False
        self.freeze_work_captions(seq)
        blocks,cues,duration=sequence_layout(seq,self.project.subtitles,{path:self.placement(path)['video'] for path in self.media.paths()})
        self.subtitle_panel.show_segments(deepcopy(cues))
        self.editor_source="edit:"+seq["id"]
        self.subtitle_panel.setEnabled(True)
        basis=self.subtitle_panel.editor.export_basis
        with QSignalBlocker(basis):basis.setCurrentIndex(basis.findData("timeline"))
        basis.setEnabled(False);basis.setToolTip("선택한 작업본의 시간 기준으로 출력합니다.")
        self.subtitle_panel.editor.run_info.setText("작업 대상: "+seq["name"]+" · 편집본 시간 기준")
        self.subtitle_panel.status.setText("자막 작업 대상: "+seq["name"])
        self.export_action.setEnabled(bool(cues))
        if hasattr(self,"video_export_action"):self.video_export_action.setEnabled(bool(sequence_clips(seq)))
        self.preview.edit_name=seq["name"]
        self.preview.set_sequence_clips(sequence_clips(seq))
        self.preview.set_subtitles(cues)
        self.preview.refresh_title()
        canvas=self.timeline.canvas
        canvas.duration=duration
        canvas.blocks=blocks
        canvas.segments=cues
        canvas.sequence_view=True
        self.timeline.begin_edit.hide()
        clips=sequence_clips(seq)
        selected=canvas.selected_clip
        keys={i for i in canvas.selected_keys if 0<=i<len(clips)} if selected is not None else set()
        if selected is not None and selected<len(clips):
            if selected not in keys:keys={selected}
            if seq.get('linked',True) and not canvas.individual_selection:
                groups={clips[i]['group'] for i in keys};keys|={i for i,c in enumerate(clips) if c['group'] in groups}
        canvas.selected_keys=keys
        for control in (self.timeline.scope,self.timeline.earlier,self.timeline.later):
            control.hide()
            control.setEnabled(False)
        self.timeline.link.setEnabled(True)
        self.timeline.link.setToolTip("연결된 짝이 있는 영상·음성 컷을 함께 편집합니다. 끄면 선택 트랙만 편집합니다.")
        with QSignalBlocker(self.timeline.link):
            self.timeline.link.setChecked(seq.get('linked',True))
        self.timeline.undo.setEnabled(bool(self.sequence_history.get(seq['id'])))
        self.timeline.split_button.show()
        self.timeline.delete_button.show()
        selected=canvas.selected_clip is not None and canvas.selected_clip<len(sequence_clips(seq))
        self.timeline.split_button.setEnabled(selected)
        self.timeline.delete_button.setEnabled(selected or bool(canvas.selected_subtitles))
        self.timeline.hint.setText('빈 곳 드래그: 세트 선택 · Ctrl+클릭: 추가/해제 · Alt+클릭: 개별 · Shift: 뒤 항목 함께 · Ctrl+K: 분할 · Delete: 자리 유지 삭제 · Alt+Backspace: 붙여 삭제 · 끝 근처: 맞춤 · Esc: 해제')
        self.timeline.info.setText(f"자막 {len(cues)}개 · {sum(c['track']=='video' for c in sequence_clips(seq))}개 컷")
        self.timeline.update_scroll()
        canvas.update()
        self.update_history_controls()
        return True

    def select_sequence_clip(self,track,index):
        if not self.active_sequence():
            return
        if self.preview._playing:
            self.preview.toggle_play()
        canvas=self.timeline.canvas
        canvas.selected_gap=None
        seq=self.active_sequence()
        clips=sequence_clips(seq)
        already=index in (canvas.selected_subtitles if track=='subtitle' else canvas.selected_keys)
        owner=canvas.segments[index].get('owner') if track=='subtitle' else clips[index]['group']
        keys=set();subtitles=set()
        individual=canvas.selection_alt
        if individual:
            if track=='subtitle':subtitles={index}
            else:keys={index}
        else:
            if owner:
                keys={i for i,c in enumerate(clips) if c['group']==owner and (seq.get('linked',True) or (c['track']=='video' if track=='subtitle' else i==index))}
                subtitles={i for i,r in enumerate(canvas.segments) if r.get('owner')==owner}
            if track=='subtitle':subtitles.add(index)
        if canvas.selection_additive or individual:
            if already:canvas.selected_keys-=keys;canvas.selected_subtitles-=subtitles
            else:canvas.selected_keys|=keys;canvas.selected_subtitles|=subtitles
            canvas.individual_selection=canvas.individual_selection or individual
        elif individual or not already:
            canvas.selected_keys=keys;canvas.selected_subtitles=subtitles;canvas.individual_selection=individual
        canvas.selected_clip=index if track!='subtitle' and index in canvas.selected_keys else next(iter(canvas.selected_keys),None)
        canvas.selected_track=clips[canvas.selected_clip]['track'] if canvas.selected_clip is not None else None
        self.timeline.split_button.setEnabled(bool(canvas.selected_keys))
        self.timeline.delete_button.setEnabled(bool(canvas.selected_keys or canvas.selected_subtitles))
        self.timeline.canvas.update()

    def timeline_edit_candidate(self,index,mode,delta,ripple,track='video'):
        original=self.active_sequence();canvas=self.timeline.canvas
        canvas.snap_guide=None;canvas.snap_insert=False;canvas.edit_blocked=False
        seq=dict(original,timeline_captions=deepcopy(canvas.segments))
        linked=seq.get('linked',True)
        if canvas.individual_selection:
            seq['linked']=False
            groups={sequence_clips(seq)[i]['group'] for i in canvas.selected_keys if sequence_clips(seq)[i]['track']=='video'}
            for i,r in enumerate(seq['timeline_captions']):
                if r.get('owner') in groups or i in canvas.selected_subtitles:
                    r.pop('owner',None);r['detached']=True
        if mode=='move':
            tolerance=round(8*canvas.span/max(1,canvas.width()-107))
            snapped=snap_move(seq,canvas.selected_keys,delta,tolerance) if not ripple and canvas.selected_keys else None
            if snapped:
                canvas.snap_guide=snapped[1];canvas.snap_insert=True
                if snapped[0]==0:return original
                result=safe_move(seq,canvas.selected_keys,canvas.selected_subtitles,snapped[0])
            else:
                result=move_timeline_items(seq,canvas.selected_keys,canvas.selected_subtitles,delta,ripple,canvas.segments)
            result['linked']=linked
            return result
        if track=='subtitle':
            rows=deepcopy(seq['timeline_captions']);row=rows[index]
            value=round(delta/1000,3)
            if mode=='start':row['start']=round(max(0,min(row['end']-.001,row['start']+value)),3)
            else:row['end']=round(max(row['start']+.001,min(604800,row['end']+value)),3)
            owner=next((c for c in sequence_clips(seq) if c['track']=='video' and c['group']==row.get('owner')),None)
            if owner:
                a=round(owner['start']+row['start']-owner['at'],3);b=round(owner['start']+row['end']-owner['at'],3)
                if 0<=a<b<=604800:row.update(source_start=a,source_end=b)
                else:row.pop('owner',None);row['detached']=True
            return validate_sequence(dict(seq,linked=linked,timeline_captions=sorted(rows,key=lambda r:r['start'])))
        result=edit_clip(seq,index,mode,delta,ripple);result['linked']=linked
        return result

    def preview_sequence_edit(self,index,mode,delta,ripple,track='video'):
        seq=self.active_sequence()
        if not seq:
            return None
        try:
            candidate=self.timeline_edit_candidate(index,mode,delta,ripple,track)
            canvas=self.timeline.canvas
            groups={sequence_clips(seq)[i]['group'] for i in canvas.selected_keys}
            canvas.drag_destinations=[b for b in sequence_layout(candidate)[0] if sequence_clips(candidate)[b[4]]['group'] in groups]
            return sequence_layout(candidate,self.project.subtitles,{p:self.placement(p)['video'] for p in self.media.paths()})[:2]
        except ValueError:
            self.timeline.canvas.snap_guide=None;self.timeline.canvas.snap_insert=False
            self.timeline.canvas.edit_blocked=True;self.timeline.canvas.drag_destinations=[]
            return self.timeline.canvas.blocks,self.timeline.canvas.segments

    def sequence_snapshot(self):
        return (deepcopy(self.active_sequence()),self.timeline.canvas.selected_clip,self.preview.timeline_position(),set(self.timeline.canvas.selected_keys),set(self.timeline.canvas.selected_subtitles))

    def commit_sequence(self,candidate,message,position=None):
        seq=self.active_sequence()
        if sequence_clips(seq)==sequence_clips(candidate) and seq.get('linked',True)==candidate.get('linked',True) and seq.get('timeline_captions')==candidate.get('timeline_captions') and seq.get('scene_tags')==candidate.get('scene_tags'):
            return
        self.abort_timeline_scrub()
        if self.preview._playing:
            self.preview.toggle_play()
        stack=self.sequence_history.setdefault(seq['id'],[])
        stack.append(self.sequence_snapshot())
        del stack[:-30]
        self.sequence_redo.pop(seq['id'],None)
        selected=self.timeline.canvas.selected_clip
        old_clips=sequence_clips(seq)
        new_clips=sequence_clips(candidate)
        if selected is not None and selected<len(old_clips):
            old=old_clips[selected]
            selected=next((i for i,c in enumerate(new_clips) if c['group']==old['group'] and c['track']==old['track']),None)
            if selected is None:
                track_indices=sorted((i for i,c in enumerate(new_clips) if c['track']==old['track']),key=lambda i:new_clips[i]['at'])
                selected=next((i for i in track_indices if new_clips[i]['at']>=old['at']),track_indices[-1] if track_indices else None)
        identities={(old_clips[i]['group'],old_clips[i]['track']) for i in self.timeline.canvas.selected_keys if i<len(old_clips)}
        keys={i for i,c in enumerate(new_clips) if (c['group'],c['track']) in identities}
        canvas=self.timeline.canvas
        selected_ids={canvas.segments[i].get('id') for i in canvas.selected_subtitles if i<len(canvas.segments)}-{None}
        cues=sequence_layout(candidate,self.project.subtitles,{p:self.placement(p)['video'] for p in self.media.paths()})[1]
        subtitles={i for i,r in enumerate(cues) if r.get('id') in selected_ids}
        self.sync_committed_group(seq,candidate)
        self.restore_sequence((candidate,selected,self.preview.timeline_position() if position is None else position,keys,subtitles))
        self.statusBar().showMessage(message+' · Ctrl+Z로 실행 취소 · 프로젝트를 저장하세요.')

    def restore_sequence(self,snapshot):
        seq,selected,position=deepcopy(snapshot[:3])
        keys=set(snapshot[3]) if len(snapshot)>3 else set()
        self.abort_timeline_scrub()
        if self.preview._playing:
            self.preview.toggle_play()
        index=next(i for i,row in enumerate(self.project.edit_sequences) if row['id']==seq['id'])
        self.project.edit_sequences[index]=seq
        clips=sequence_clips(seq)
        self.timeline.canvas.selected_clip=min(selected,len(clips)-1) if selected is not None and clips else None
        self.timeline.canvas.selected_track=clips[self.timeline.canvas.selected_clip]['track'] if self.timeline.canvas.selected_clip is not None else None
        self.timeline.canvas.selected_keys=keys
        self.timeline.canvas.selected_subtitles=set(snapshot[4]) if len(snapshot)>4 else set()
        self.timeline.canvas.selected_gap=None
        self.timeline.canvas.preview_blocks=None
        self.timeline.canvas.preview_segments=None
        self.timeline.canvas.drag=None
        self.mark_dirty()
        self.render_edit_sequence()
        self.preview.seek_timeline(min(position,self.preview.timeline_duration()))
        self.timeline.canvas.update()

    def edit_sequence_clip(self,track,index,mode,delta,ripple):
        seq=self.active_sequence()
        if not seq:
            return
        try:
            candidate=self.timeline_edit_candidate(index,mode,delta,ripple,track)
            self.commit_sequence(candidate,'끝 맞춤 · 컷 길이 보존' if self.timeline.canvas.snap_insert else '뒤 컷 함께 조정' if ripple else '컷 조정')
        except ValueError as exc:
            self.statusBar().showMessage(str(exc))

    def timeline_gap_at(self,position,track):
        seq=self.active_sequence()
        if not seq:return None
        result=gap_at(dict(seq,timeline_captions=self.timeline.canvas.segments),position/1000,track)
        return tuple(round(t*1000) for t in result) if result else None

    def select_timeline_gap(self,track,start,end):
        if not self.active_sequence() or not self.resolve_subtitle_edit():return
        self.clear_workspace_selection()
        canvas=self.timeline.canvas
        canvas.selected_gap=(track,start,end)
        canvas.gap_linked=self.active_sequence().get('linked',True)
        if self.preview._playing:self.preview.toggle_play()
        self.seek_transport(start)
        self.timeline.delete_button.setEnabled(False)
        self.statusBar().showMessage('빈칸 선택 · Backspace / Alt+Backspace로 뒤 항목을 당겨 닫습니다.')
        canvas.update()

    def close_timeline_gap(self):
        canvas=self.timeline.canvas
        if not self.active_sequence() or not canvas.selected_gap:return
        track,start,end=canvas.selected_gap
        try:
            seq=dict(self.active_sequence(),timeline_captions=deepcopy(canvas.segments))
            self.commit_sequence(close_gap(seq,start/1000,end/1000,track),'빈칸 닫기 · 컷 길이 보존',position=start)
        except ValueError as exc:self.statusBar().showMessage(str(exc))

    def delete_sequence_clip(self,ripple=False):
        seq=self.active_sequence()
        if not seq or not self.resolve_subtitle_edit() or self.subtitle_job.busy:return
        canvas=self.timeline.canvas
        if canvas.selected_gap is not None:
            if ripple:self.close_timeline_gap()
            return
        try:
            rows=deepcopy(canvas.segments)
            linked=seq.get('linked',True)
            if canvas.individual_selection:
                groups={sequence_clips(seq)[i]['group'] for i in canvas.selected_keys if sequence_clips(seq)[i]['track']=='video'}
                for i,row in enumerate(rows):
                    if row.get('owner') in groups and i not in canvas.selected_subtitles:
                        row.pop('owner',None);row['detached']=True
            candidate=dict(seq,linked=False if canvas.individual_selection else linked,timeline_captions=rows)
            clips=sequence_clips(candidate)
            starts=[round(clips[i]['at']*1000) for i in canvas.selected_keys if 0<=i<len(clips)]
            if not starts:starts=[round(rows[i]['start']*1000) for i in canvas.selected_subtitles if 0<=i<len(rows)]
            position=min(starts) if ripple and starts else None
            result=delete_items(candidate,canvas.selected_keys,canvas.selected_subtitles,ripple)
            result['linked']=linked
            self.commit_sequence(result,'붙여 삭제 · 뒤 항목 당김' if ripple else '선택 항목만 삭제 · 뒤 컷 위치 유지',position=position)
        except ValueError as exc:self.statusBar().showMessage(str(exc))

    def split_sequence_clip(self):
        seq=self.active_sequence()
        if not seq:
            return
        try:
            clips=sequence_clips(seq);position=self.preview.timeline_position()
            selected=self.timeline.canvas.selected_clip
            if selected is None or selected>=len(clips) or not round(clips[selected]['at']*1000)<position<round((clips[selected]['at']+clips[selected]['end']-clips[selected]['start'])*1000):
                selected=next((i for track in ('video','audio') for i,c in enumerate(clips) if c['track']==track and round(c['at']*1000)<position<round((c['at']+c['end']-c['start'])*1000)),None)
            if selected is None:raise ValueError('컷 안으로 재생 위치를 옮긴 다음 Ctrl+K를 눌러 주세요.')
            self.timeline.canvas.selected_clip=selected
            self.commit_sequence(split_clip(dict(seq,timeline_captions=deepcopy(self.timeline.canvas.segments)),selected,position),'컷 분할')
        except ValueError as exc:
            self.statusBar().showMessage(str(exc))

    def change_sequence_link(self,checked):
        seq=self.active_sequence()
        self.commit_sequence(validate_sequence(dict(seq,clips=sequence_clips(seq),linked=checked)), '영상·음성 연결 변경')

    def change_sequence_history(self,redo):
        if hasattr(self,"project_undo"):
            self.change_project_history(redo)
            return
        seq=self.active_sequence()
        if not seq:
            return
        history=self.sequence_redo if redo else self.sequence_history
        opposite=self.sequence_history if redo else self.sequence_redo
        stack=history.get(seq['id'],[])
        if stack:
            opposite.setdefault(seq['id'],[]).append(self.sequence_snapshot())
            del opposite[seq['id']][:-30]
            self.restore_sequence(stack.pop())
            self.statusBar().showMessage('다시 실행했습니다.' if redo else '실행 취소했습니다.')
