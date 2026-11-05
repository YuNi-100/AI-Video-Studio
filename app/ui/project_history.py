"""Project-scoped chronological commands, including bin and timeline changes."""
from contextlib import contextmanager
from copy import deepcopy
from functools import wraps
import json
from pathlib import Path
from PySide6.QtCore import QSignalBlocker


def project_action(function):
    @wraps(function)
    def invoke(self,*args,**kwargs):
        owner=getattr(self,'studio',self)
        if not getattr(owner,'_history_enabled',False):
            return function(self,*args,**kwargs)
        with owner.project_transaction():
            return function(self,*args,**kwargs)
    return invoke


class ProjectHistory:
    def init_project_history(self):
        self.project_undo=[]
        self.project_redo=[]
        self._history_enabled=True
        self._history_restoring=False
        self._history_depth=0
        for name in ('add_files','replace_selected','rename_selected','remove_selected'):
            original=getattr(self.media,name)
            def wrapped(*args,_function=original,**kwargs):
                with self.project_transaction():
                    return _function(*args,**kwargs)
            setattr(self.media,name,wrapped)

    def history_snapshot(self):
        project=deepcopy(self.project)
        project.media_paths=self.media.paths()
        project.media_names=self.media.names()
        project.active_path=self.media.selected_path()
        canvas=self.timeline.canvas
        return dict(project=project,active=self.active_edit_id,closed=set(self.closed_sequence_ids),
            position=self.transport_position_value(),scope=self.timeline.scope.currentIndex(),
            clip=canvas.selected_clip,keys=set(canvas.selected_keys),captions=set(canvas.selected_subtitles))

    @staticmethod
    def history_data(snapshot):
        data=dict(snapshot['project'].__dict__)
        data.pop('active_path',None)  # Browsing is not an edit command.
        return data

    @contextmanager
    def project_transaction(self):
        if (not getattr(self,'_history_enabled',False) or getattr(self,'_history_restoring',False)
                or getattr(self,'_workspace_loading',False) or self._history_depth):
            yield
            return
        before=self.history_snapshot()
        uid=self.active_document_id
        self._history_depth+=1
        try:
            yield
        finally:
            self._history_depth-=1
            if uid==self.active_document_id and self.history_data(before)!=self.history_data(self.history_snapshot()):
                self.project_undo.append(before)
                self.project_redo.clear()
                self.trim_project_history(self.project_undo)
                self.update_history_controls()

    def trim_project_history(self,stack):
        del stack[:-30]
        total=0
        keep=len(stack)
        for snapshot in reversed(stack):
            total+=len(json.dumps(snapshot['project'].__dict__,ensure_ascii=False).encode('utf-8'))
            if total>32*1024*1024 and keep<len(stack):
                break
            keep-=1
        if keep>0:
            del stack[:keep]

    def update_history_controls(self):
        if hasattr(self,'project_undo'):
            self.timeline.undo.setEnabled(bool(self.project_undo) and not self.subtitle_job.busy)
            self.timeline.undo.setToolTip('Ctrl+Z · 현재 프로젝트의 마지막 작업 취소 · Ctrl+Shift+Z로 다시 실행')

    def change_project_history(self,redo):
        if self.subtitle_job.busy or self._history_depth or not self.resolve_subtitle_edit():
            return
        source=self.project_redo if redo else self.project_undo
        other=self.project_undo if redo else self.project_redo
        if not source:
            self.statusBar().showMessage('다시 실행할 작업이 없습니다.' if redo else '실행 취소할 작업이 없습니다.')
            return
        current=self.history_snapshot()
        snapshot=source.pop()
        other.append(current)
        self.trim_project_history(other)
        self.restore_project_snapshot(snapshot)
        self.statusBar().showMessage('프로젝트 작업을 다시 실행했습니다.' if redo else '프로젝트 작업을 실행 취소했습니다.')

    def restore_project_snapshot(self,snapshot):
        self._history_restoring=True
        loading=self._workspace_loading
        self._workspace_loading=True
        try:
            self.abort_timeline_scrub()
            self.pending_seek=None
            if self.preview._playing:
                self.preview.toggle_play()
            project=deepcopy(snapshot['project'])
            self.project.__dict__.clear()
            self.project.__dict__.update(project.__dict__)
            self.active_edit_id=snapshot['active'] if any(s['id']==snapshot['active'] for s in project.edit_sequences) else None
            self.closed_sequence_ids=set(snapshot['closed'])
            if self.active_edit_id:self.closed_sequence_ids.discard(self.active_edit_id)
            self.media.restore(project.media_paths,project.active_path,project.media_names)
            self.project_name.setText(project.name)
            self.subtitle_panel.terms.setText(project.subtitle_terms)
            self.subtitle_panel.skip_silence.setChecked(project.subtitle_skip_silence)
            self.subtitle_history={};self.subtitle_redo={};self.sequence_history={};self.sequence_redo={}
            self.editor_source=None
            with QSignalBlocker(self.timeline.scope):
                self.timeline.scope.setCurrentIndex(snapshot['scope'])
            canvas=self.timeline.canvas
            canvas.drag=None;canvas.preview_blocks=None;canvas.preview_segments=None;canvas.selected_gap=None
            canvas.selected_clip=snapshot['clip'];canvas.selected_keys=set(snapshot['keys'])
            canvas.selected_subtitles=set(snapshot['captions'])
            selected=project.active_path
            if selected and Path(selected).is_file():
                if str(self.preview.source)!=selected or not self.preview.ready:
                    self._opening_edit_sequence=True
                    try:self.open_media(selected)
                    finally:self._opening_edit_sequence=False
            else:
                self.preview.shutdown();self.preview.source=None;self.preview.ready=False
                self.preview.empty.setText('원본 파일을 다시 연결하세요.' if selected else '영상 파일을 선택하세요')
                self.preview.stack.setCurrentWidget(self.preview.empty)
                self.preview.status.setText('원본 연결 필요' if selected else '미디어 없음')
                self.preview.update_controls()
            self.sync_sequence_tabs()
            self.show_source_subtitles(force=True)
            if self.preview.ready:self.preview.seek_timeline(snapshot['position'])
            elif selected:self.pending_seek=(snapshot['position'],False)
            self.dirty=True
            self.refresh_title()
        finally:
            self._workspace_loading=loading
            self._history_restoring=False
        self.sync_workspace_ui()
        self.update_history_controls()


def install_history_actions(window_class):
    names=('open_asset_work','rename_project','new_organized_folder','rename_organized','delete_organized','paste_organized',
        'compose_selected','reorder_organized','handle_media_drop','handle_organization_drop','create_labeled_edit',
        'edit_from_selected_assets','begin_timeline_edit','request_timeline_split','create_edit_sequence',
        'commit_sequence','edit_sequence_clip','split_sequence_clip','delete_sequence_clip','delete_timeline_selection',
        'close_timeline_gap','change_sequence_link','new_edit_from_clipboard','paste_timeline_sets','subtitles_ready','apply_subtitle_edit',
        'add_subtitle','remove_subtitle','move_timeline_block','resize_timeline_subtitle','subtitle_terms_changed',
        'subtitle_filter_changed','change_link','reorder_media')
    for name in names:
        setattr(window_class,name,project_action(getattr(window_class,name)))
