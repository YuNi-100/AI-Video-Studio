"""Captions owned by the lower edit selection, independent of the library."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4,uuid5,NAMESPACE_URL
import json,tempfile
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QMessageBox
from app.features.silence.sequence import sequence_clips,sequence_layout,validate_sequence
from app.features.subtitles.model import validate_segments


def bind_captions(seq,rows):
    result=[]
    videos=[c for c in sequence_clips(seq) if c['track']=='video']
    for raw,original in zip(rows,validate_segments(rows)):
        a,b=original['start'],original['end']
        points=sorted({a,b}|{max(a,min(b,t)) for c in videos for t in (c['at'],c['at']+c['end']-c['start'])})
        for left,right in zip(points,points[1:]):
            if right<=left:continue
            row=dict(original,start=left,end=right,id=raw.get('id',uuid4().hex) if len(points)==2 else uuid4().hex)
            owner=next((c for c in videos if c['at']<=left+.000001 and right<=c['at']+c['end']-c['start']+.000001),None)
            if raw.get('detached'):owner=None
            if owner:row.update(owner=owner['group'],source_start=round(owner['start']+left-owner['at'],3),source_end=round(owner['start']+right-owner['at'],3))
            else:row['detached']=True
            result.append(row)
    return result


class WorkSubtitles:
    def work_has_audio(self):
        import av
        seq=self.active_sequence()
        if not seq:return False
        cache=getattr(self,'_work_audio_cache',{})
        self._work_audio_cache=cache
        for clip in sequence_clips(seq):
            if clip['track']!='audio':continue
            source=clip.get('source',seq['source'])
            try:
                stat=Path(source).stat();stamp=(stat.st_size,stat.st_mtime_ns)
                if source not in cache or cache[source][0]!=stamp:
                    with av.open(source) as container:cache[source]=(stamp,bool(container.streams.audio))
                if cache[source][1]:return True
            except (OSError,ValueError,av.error.FFmpegError):continue
        return False

    def freeze_work_captions(self,seq):
        if 'timeline_captions' not in seq:
            seq['timeline_captions']=deepcopy(sequence_layout(seq,self.project.subtitles,{p:self.placement(p)['video'] for p in self.media.paths()})[1])

    def commit_work_subtitles(self,rows,index=-1,sequence_id=None,message='작업본 자막 수정'):
        seq=next((s for s in self.project.edit_sequences if s['id']==(sequence_id or self.active_edit_id)),None)
        if seq is None or seq['id']!=self.active_edit_id:raise ValueError('자막 작업 대상이 바뀌었습니다. 작업본을 다시 선택하세요.')
        candidate=validate_sequence(dict(seq,timeline_captions=bind_captions(seq,rows)))
        self.commit_sequence(candidate,message)
        if index>=0:self.subtitle_panel.editor.set_selection(min(index,len(self.timeline.canvas.segments)-1))

    def work_job_arguments(self,seq,work):
        request=Path(work.name)/'sequence.json'
        request.write_text(json.dumps(seq,ensure_ascii=False),encoding='utf-8')
        return ['--sequence',str(request),'--audio-output',str(Path(work.name)/'audio.wav')]

    def generate_work_subtitles(self,model,language):
        seq=self.active_sequence()
        if not seq or self.subtitle_job.busy or not self.resolve_subtitle_edit():return
        if seq.get('timeline_captions') and QMessageBox.question(self,'작업본 자막 다시 생성','선택한 작업본의 자막만 새 결과로 바꿀까요? 다른 작업본과 원본 자막은 유지됩니다.')!=QMessageBox.StandardButton.Yes:return
        self._work_caption_job=(self.project,seq['id'],deepcopy(seq))
        self._work_caption_temp=tempfile.TemporaryDirectory(prefix='studio-work-captions-')
        self.subtitle_panel.set_busy(True);self.media.setEnabled(False);self.timeline.setEnabled(False)
        try:
            if not self.subtitle_job.start(seq['source'],model,language,self.whisper_cache,self.subtitle_panel.terms.text(),self.subtitle_panel.skip_silence.isChecked(),worker_module='app.features.subtitles.sequence_worker',extra_args=self.work_job_arguments(seq,self._work_caption_temp)):
                self.subtitle_finished()
        except (ValueError,OSError) as exc:self.subtitle_failed(str(exc));self.subtitle_finished()

    def work_subtitles_ready(self,rows):
        project,key,snapshot=self._work_caption_job
        seq=self.active_sequence()
        if self.project is not project or not seq or seq['id']!=key or seq!=snapshot:
            self.statusBar().showMessage('작업본이 바뀌어 새 자막을 적용하지 않았습니다.');return
        self.commit_work_subtitles(rows,0,message='작업본 자동 자막 생성')
        seq=self.active_sequence()
        seq['subtitle_run']={k:v for k,v in self.subtitle_job.run_info.items() if isinstance(v,(str,bool))}
        self.mark_dirty();self.subtitle_panel.tabs.setCurrentIndex(1)
        self.subtitle_panel.status.setText(f"{seq['name']} · 자막 {len(rows)}개 생성 완료")

    def preview_library_source(self,path=None):
        if path is None:
            item=self.media.project_tree.currentItem();data=item.data(0,Qt.ItemDataRole.UserRole) if item else None
            record=self.record_for(data);path=record.get('source') if record else None
        if not path:return
        from app.ui.video_player import VideoPlayer
        dialog=QDialog(self);dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose,True)
        dialog.setWindowTitle('보관함 원본 미리보기 · '+Path(path).name);dialog.resize(850,520)
        player=VideoPlayer();layout=QVBoxLayout(dialog);layout.addWidget(player)
        dialog.finished.connect(lambda _:player.shutdown())
        try:player.open_video(path)
        except ValueError as exc:self.statusBar().showMessage(str(exc));dialog.deleteLater();return
        self.library_preview=dialog;dialog.player=player;dialog.show()

    def open_asset_work(self,record):
        if not self.allow_project_switch():return
        key='asset-'+uuid5(NAMESPACE_URL,record['id']).hex
        if not any(s['id']==key for s in self.project.edit_sequences):
            if len(self.project.edit_sequences)>=1000:
                self.statusBar().showMessage('편집본은 최대 1000개입니다.');return
            duration=self.source_items([record['source']])[0][1]
            seq=validate_sequence(dict(id=key,name=record['name'],source=record['source'],duration=duration,ranges=[[0,duration]]))
            self.freeze_work_captions(seq)
            self.project.edit_sequences.append(seq);self.project.edit_locations[key]=record.get('folder');self.mark_dirty()
        self.open_edit_sequence(key)
