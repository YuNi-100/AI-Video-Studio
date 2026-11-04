"""Independent in-memory project sessions and project-scoped media/sequence trees."""
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import Qt,QSignalBlocker
from PySide6.QtWidgets import QTreeWidgetItem,QMessageBox
from app.core.project import Project
from app.storage.project_store import load_project


class ProjectWorkspace:
    SESSION_FIELDS=('subtitle_history','subtitle_redo','sequence_history','sequence_redo','active_edit_id','closed_sequence_ids')

    def init_workspace(self):
        self.documents=[]
        self.active_document_id=uuid4().hex
        self._workspace_loading=False
        self.documents.append(dict(id=self.active_document_id,project=self.project,path=self.project_path,dirty=self.dirty,state={}))
        self.media.restored.connect(self.sync_workspace_ui)
        self.media.project_tree.itemClicked.connect(self.project_media_clicked)
        self.timeline.sequence_tree.itemClicked.connect(self.project_sequence_clicked)
        self.sync_workspace_ui()

    def snapshot_document(self):
        if self._workspace_loading:
            return
        doc=next(d for d in self.documents if d['id']==self.active_document_id)
        self.sync_library_records(self.media.paths(),self.project.media_paths)
        self.project.media_paths=self.media.paths()
        self.project.media_names=self.media.names()
        self.project.active_path=self.media.selected_path()
        state={key:getattr(self,key) for key in self.SESSION_FIELDS}
        state.update(scope=self.timeline.scope.currentIndex(),position=self.preview.timeline_position(),selected_clip=self.timeline.canvas.selected_clip,language=self.subtitle_panel.language.currentData(),model=self.subtitle_panel.model.currentData(),tab=self.subtitle_panel.tabs.currentIndex(),zoom=self.timeline.zoom.value(),offset=self.timeline.canvas.offset)
        doc.update(project=self.project,path=self.project_path,dirty=self.dirty,state=state)

    def activate_document(self,key):
        if key==self.active_document_id:
            return True
        if not self.allow_project_switch():
            self.sync_workspace_ui()
            return False
        target=next((d for d in self.documents if d['id']==key),None)
        if target is None:
            return False
        self.rename_project()
        self.snapshot_document()
        self.abort_timeline_scrub()
        self.pending_seek=None
        self.switch_queued=False
        self._workspace_loading=True
        self.active_document_id=key
        try:
            with QSignalBlocker(self.timeline.scope):
                self.timeline.scope.setCurrentIndex(0)
            self._apply_project_single(target['project'],target['path'])
            state=target['state']
            for field in self.SESSION_FIELDS:
                if field in state:
                    setattr(self,field,state[field])
            with QSignalBlocker(self.timeline.scope):
                self.timeline.scope.setCurrentIndex(state.get('scope',0))
            self.subtitle_panel.language.setCurrentIndex(max(0,self.subtitle_panel.language.findData(state.get('language','ko'))))
            self.subtitle_panel.model.setCurrentIndex(max(0,self.subtitle_panel.model.findData(state.get('model','large-v3-turbo'))))
            self.subtitle_panel.tabs.setCurrentIndex(state.get('tab',0))
            self.timeline.zoom.setValue(state.get('zoom',100))
            self.dirty=target['dirty']
            self.timeline.canvas.selected_clip=state.get('selected_clip')
            self.sync_sequence_tabs()
            self.show_source_subtitles(force=True)
            position=state.get('position',0)
            if self.preview.ready:
                self.preview.seek_timeline(position)
            elif self.project.active_path:
                self.pending_seek=(position,False)
            self.timeline.canvas.offset=state.get("offset",0)
            self.timeline.update_scroll()
            self.refresh_title()
        finally:
            self._workspace_loading=False
        self.sync_workspace_ui()
        return True

    def apply_project(self,project,path):
        # Explicit replacement is retained for internal restoration and tests.
        self._workspace_loading=True
        try:
            self.pending_seek=None
            self._apply_project_single(project,path)
        finally:
            self._workspace_loading=False
        self.snapshot_document()
        self.sync_workspace_ui()

    def add_project_document(self,project,path=None):
        if not self.allow_project_switch():
            return False
        self.rename_project()
        self.snapshot_document()
        pristine=(len(self.documents)==1 and self.project_path is None and not self.dirty and not self.media.paths() and not self.project.edit_sequences)
        if pristine:
            doc=self.documents[0]
            doc.update(project=project,path=path,dirty=False,state={})
            self._workspace_loading=True
            try: self._apply_project_single(project,path)
            finally: self._workspace_loading=False
            self.snapshot_document();self.sync_workspace_ui()
            return True
        doc=dict(id=uuid4().hex,project=project,path=path,dirty=False,state={})
        self.documents.append(doc)
        return self.activate_document(doc['id'])

    def open_project_path(self,path):
        if not self.allow_project_switch():
            return False
        resolved=Path(path).resolve()
        existing=next((d for d in self.documents if d['path'] and Path(d['path'])==resolved),None)
        if existing:
            return self.activate_document(existing['id'])
        try: project=load_project(resolved)
        except ValueError as exc:
            QMessageBox.warning(self,'열기 실패',str(exc));return False
        return self.add_project_document(project,resolved)

    def new_project(self):
        names={d['project'].name for d in self.documents}
        number=1
        while f'새 프로젝트 {number}' in names: number+=1
        self.add_project_document(Project(name=f'새 프로젝트 {number}'))

    def save_current(self,save_as=False,path=None):
        result=self._save_current_single(save_as,path)
        if result:
            self.snapshot_document();self.sync_workspace_ui()
        return result

    def destination_in_use(self,path):
        return any(d['id']!=self.active_document_id and d['path'] and Path(d['path'])==Path(path).resolve() for d in self.documents)

    def close_current_project(self):
        if not self.allow_project_switch():return False
        self.rename_project()
        if not self.confirm_discard():return False
        old=self.active_document_id
        if len(self.documents)==1:
            self.apply_project(Project(),None)
        else:
            target=next(d['id'] for d in self.documents if d['id']!=old)
            if not self.activate_document(target):return False
            self.documents=[d for d in self.documents if d['id']!=old]
            self.sync_workspace_ui()
        return True

    def confirm_all_projects(self):
        self.snapshot_document()
        for key in [d['id'] for d in self.documents]:
            doc=next(d for d in self.documents if d['id']==key)
            if not doc['dirty']:continue
            if not self.activate_document(key) or not self.confirm_discard():return False
        return True

    def sync_workspace_ui(self):
        if not hasattr(self,'documents') or self._workspace_loading:return
        self.render_organized_trees()
        if hasattr(self, "scene_search") and self.scene_search.isVisible():
            self.scene_search.refresh()

    def project_media_clicked(self,item,column=0):
        self.organized_clicked(item,'library')

    def project_sequence_clicked(self,item,column=0):
        self.organized_clicked(item,'edit')
