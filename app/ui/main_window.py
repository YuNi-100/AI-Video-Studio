from PySide6.QtCore import Qt, QSignalBlocker, QTimer
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QButtonGroup, QLineEdit, QSplitter, QMessageBox, QFileDialog, QComboBox, QFrame, QSizePolicy)
from copy import deepcopy
from pathlib import Path
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from app.storage.project_store import load_project, save_project
from app.core.project import Project
from app.features.roadmap import ROADMAP
from app.features.subtitles.editing import edit_segment, review_reasons
from app.features.subtitles.export import export_srt
from app.features.subtitles.job import SubtitleJob, recognition_installed
from app.ui.components import label, pending
from app.ui.timeline import Timeline
from app.ui.workspace import SubtitlePanel
from app.ui.media_panel import MediaPanel
from app.ui.video_player import VideoPlayer
from app.ui.playback_keys import PlaybackKeys
from app.ui.timeline_focus import TimelineFocus
from app.ui.history_keys import HistoryKeys
from app.ui.project_history import ProjectHistory, install_history_actions
from app.ui.drop_import import VideoDropImport
from app.ui.project_workspace import ProjectWorkspace
from app.ui.project_picker import ProjectPicker
from app.ui.selection_interaction import SelectionInteraction
from app.ui.sequence_drop import SequenceDropWorkflow
from app.ui.organizer_workflow import OrganizerWorkflow
from app.features.silence.sequence import sequence_sources

from app.ui.timeline_workflow import TimelineWorkflow

from app.ui.edit_groups import EditGroups
from app.ui.work_subtitles import WorkSubtitles
from app.ui.edit_sequence_workflow import EditSequenceWorkflow
from app.ui.clip_clipboard import ClipClipboardWorkflow

class MainWindow(EditGroups, WorkSubtitles, ProjectHistory, ClipClipboardWorkflow, OrganizerWorkflow, SequenceDropWorkflow, ProjectWorkspace, EditSequenceWorkflow, TimelineWorkflow, QMainWindow):
    def open_subtitle_audit(self):
        if self.subtitle_job.busy or not self.resolve_subtitle_edit():return
        if not self.active_sequence():
            self.statusBar().showMessage('아래 편집본 목록에서 점검할 작업본을 먼저 선택하세요.');return
        from app.ui.subtitle_audit import SubtitleAudit
        if not hasattr(self,'audit_dialog'):self.audit_dialog=SubtitleAudit(self)
        d=self.audit_dialog
        if d.isVisible():d.raise_();return
        if d.process:return
        d.prepare();d.show();d.raise_()

    def open_subtitle_recheck(self):
        selected_caption = self.subtitle_panel.editor.selected_index
        if self.subtitle_job.busy or not self.resolve_subtitle_edit():
            return
        if not self.active_sequence() or not self.preview.ready:
            self.statusBar().showMessage("아래 편집본 목록에서 다시 인식할 작업본을 먼저 선택하세요.")
            return
        if hasattr(self,"recheck_dialog") and self.recheck_dialog.isVisible():
            self.recheck_dialog.raise_()
            return
        with QSignalBlocker(self.timeline.scope):
            self.timeline.scope.setCurrentIndex(0)
        self.show_source_subtitles(select=selected_caption,force=True)
        from app.ui.subtitle_recheck import SubtitleRecheck
        if not hasattr(self,"recheck_dialog"):
            self.recheck_dialog = SubtitleRecheck(self)
            self.subtitle_job.status.connect(lambda text:self.recheck_dialog.status.setText(text) if self.recheck_dialog.running else None)
        self.recheck_dialog.prepare()
        self.recheck_dialog.show()
        self.recheck_dialog.raise_()

    def open_scene_search(self):
        from app.ui.scene_search import SceneSearch
        if not hasattr(self, "scene_search"):
            self.scene_search = SceneSearch(self)
        self.scene_search.show()
        self.scene_search.raise_()
        self.scene_search.activateWindow()

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.project = Project()
        self.project_undo=[]
        self.project_redo=[]
        self.sequence_history = {}
        self.sequence_redo = {}
        self.closed_sequence_ids=set()
        self.active_edit_id = None
        self._opening_edit_sequence = False
        self.project_path = None
        self.editor_source = None
        self.subtitle_history = {}
        self.subtitle_redo = {}
        self.sequence_items = []
        self.duration_cache = {}
        self.pending_seek = None
        self.switch_queued = False
        self.dirty = False
        self.whisper_cache = Path(__file__).resolve().parents[2] / ".cache" / "whisper"
        self.resize(1480, 940)
        self.setMinimumSize(1180, 780)
        self.setWindowTitle("AI Video Studio · V0.3 / 검색·장면 태그")
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 14, 16, 8)
        layout.setSpacing(12)
        header = QHBoxLayout()
        header.addWidget(label("◈  AI VIDEO STUDIO", "brand"))
        header.addWidget(label("V0.3", "badge"))
        header.addSpacing(12)
        project_header=QFrame()
        project_header.setObjectName('projectHeader')
        project_header.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        project_controls=QHBoxLayout(project_header)
        project_controls.setContentsMargins(0,0,0,0)
        project_controls.setSpacing(9)
        project_controls.addWidget(label('프로젝트 이름','projectCaption'))
        self.project_name = QLineEdit(self.project.name)
        self.project_name.setObjectName('projectName')
        self.project_name.setMaxLength(80)
        self.project_name.setFixedWidth(156)
        self.project_name.setFixedHeight(30)
        self.project_name.setTextMargins(2,1,2,1)
        self.project_name.setAccessibleName('프로젝트 이름')
        self.project_name.setToolTip('현재 프로젝트의 이름입니다. 이름을 바꾼 후 Ctrl+S로 저장하세요.')
        self.project_name.editingFinished.connect(self.rename_project)
        project_controls.addWidget(self.project_name)
        project_separator=QFrame()
        project_separator.setObjectName('projectSeparator')
        project_separator.setFixedSize(1,22)
        project_controls.addWidget(project_separator)
        project_controls.addWidget(label('프로젝트 전환','projectCaption'))
        self.project_picker=ProjectPicker()
        self.project_picker.setObjectName('projectPicker')
        self.project_picker.setFixedWidth(156)
        self.project_picker.setFixedHeight(30)
        self.project_picker.setAccessibleName('프로젝트 전환')
        self.project_picker.setToolTip('열려 있는 다른 프로젝트로 전환합니다.')
        self.project_picker.currentIndexChanged.connect(lambda i:self.activate_document(self.project_picker.itemData(i)) if i>=0 and hasattr(self,'documents') else None)
        project_controls.addWidget(self.project_picker)
        header.addWidget(project_header)
        header.addStretch()
        self.save_state = label("저장 안 됨", "muted")
        header.addWidget(self.save_state)
        layout.addLayout(header)
        tabs = QHBoxLayout()
        self.tabs = QButtonGroup(self)
        for text in ("미디어", "편집", "자막", "AI 도구", "내보내기"):
            button = QPushButton(text)
            button.setObjectName("workspaceTab")
            button.setCheckable(True)
            self.tabs.addButton(button)
            tabs.addWidget(button)
            if text == "편집":
                button.setChecked(True)
        silence_button = QPushButton("AI 무음 컷")
        silence_button.clicked.connect(self.open_silence_editor)
        tabs.addWidget(silence_button)
        search_button = QPushButton("대사 검색 · 태그")
        search_button.clicked.connect(self.open_scene_search)
        tabs.addWidget(search_button)
        recheck_button = QPushButton("자막 재검토")
        recheck_button.clicked.connect(self.open_subtitle_audit)
        tabs.addWidget(recheck_button)
        tabs.addStretch()
        roadmap = QPushButton("개발 계획")
        roadmap.clicked.connect(self.show_roadmap)
        tabs.addWidget(roadmap)
        self.mode_label = label("편집 작업 공간", "muted")
        tabs.addWidget(self.mode_label)
        self.tabs.buttonClicked.connect(self.select_tab)
        layout.addLayout(tabs)
        header_boundary=QFrame()
        header_boundary.setObjectName('headerBoundary')
        header_boundary.setFixedHeight(1)
        layout.addWidget(header_boundary)
        vertical = QSplitter(Qt.Orientation.Vertical)
        horizontal = QSplitter(Qt.Orientation.Horizontal)
        self.workspace_vertical=vertical
        self.workspace_horizontal=horizontal
        for splitter in (horizontal,vertical):
            splitter.setHandleWidth(9)
        self.media = MediaPanel()
        self.preview = VideoPlayer()
        self.preview.setMinimumWidth(320)
        self.preview.name_for_path = self.media.display_name
        self.media.selected.connect(self.open_media)
        self.media.changed.connect(self.mark_dirty)
        self.media.cleared.connect(self.clear_media)
        self.media.rejected.connect(self.media_error)
        self.preview.failed.connect(self.media_error)
        self.preview.loaded.connect(self.media_loaded)
        horizontal.addWidget(self.media)
        horizontal.addWidget(self.preview)
        self.subtitle_panel = SubtitlePanel()
        self.subtitle_panel.terms.textEdited.connect(self.subtitle_terms_changed)
        self.subtitle_panel.skip_silence.clicked.connect(self.subtitle_filter_changed)
        self.subtitle_job = SubtitleJob(self)
        self.media.before_change = self.resolve_subtitle_edit
        self.subtitle_panel.editor.selected.connect(self.select_subtitle)
        self.subtitle_panel.editor.apply_requested.connect(self.apply_subtitle_edit)
        self.subtitle_panel.editor.add_requested.connect(self.add_subtitle)
        self.subtitle_panel.editor.remove_requested.connect(self.remove_subtitle)
        self.subtitle_panel.editor.undo_requested.connect(self.undo_subtitle)
        self.subtitle_panel.editor.export_requested.connect(lambda: self.export_current_subtitles())
        self.subtitle_panel.editor.overlay_changed.connect(self.preview.set_subtitles_visible)
        self.subtitle_panel.requested.connect(self.generate_subtitles)
        self.subtitle_panel.cancelled.connect(self.subtitle_job.cancel)
        self.subtitle_job.status.connect(self.subtitle_panel.status.setText)
        self.subtitle_job.completed.connect(self.subtitles_ready)
        self.subtitle_job.failed.connect(self.subtitle_failed)
        self.subtitle_job.ended.connect(self.subtitle_finished)
        self.preview.player.hasAudioChanged.connect(self.update_subtitle_controls)
        horizontal.addWidget(self.subtitle_panel)
        horizontal.setSizes([260, 792, 310])
        horizontal.setChildrenCollapsible(False)
        vertical.addWidget(horizontal)
        self.timeline = Timeline()
        self.timeline.canvas.copy_requested.connect(self.copy_timeline_sets)
        self.timeline.canvas.cut_requested.connect(self.cut_timeline_sets)
        self.timeline.canvas.paste_requested.connect(self.paste_timeline_sets)
        self.timeline.sequence_tabs.currentChanged.connect(self.select_edit_sequence)
        self.timeline.sequence_tabs.tabBarClicked.connect(lambda i:self.focus_active_sequence_in_list()
            if not self.subtitle_job.busy and self.timeline.sequence_tabs.tabData(i)==self.active_edit_id else None)
        self.timeline.sequence_tabs.tabCloseRequested.connect(self.close_edit_sequence)
        self.timeline.begin_edit.clicked.connect(self.begin_timeline_edit)
        self.timeline.canvas.edit_requested.connect(self.begin_timeline_edit)
        self.split_shortcut=QShortcut(QKeySequence('Ctrl+K'),self.timeline)
        self.split_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.split_shortcut.activated.connect(self.request_timeline_split)
        self.timeline.canvas.clip_selected.connect(self.select_sequence_clip)
        self.timeline.canvas.clip_edited.connect(self.edit_sequence_clip)
        self.timeline.canvas.edit_preview=self.preview_sequence_edit
        self.timeline.canvas.split_requested.connect(self.split_sequence_clip)
        self.timeline.canvas.delete_requested.connect(self.delete_timeline_selection)
        self.timeline.canvas.ripple_delete_requested.connect(lambda:self.delete_timeline_selection(True))
        self.timeline.canvas.gap_selected.connect(self.select_timeline_gap)
        self.timeline.canvas.gap_probe=self.timeline_gap_at
        self.timeline.canvas.range_selected.connect(self.timeline_range_selected)
        self.timeline.split_button.clicked.connect(self.split_sequence_clip)
        self.timeline.delete_button.clicked.connect(self.delete_sequence_clip)
        self.preview.timelinePositionChanged.connect(self.transport_position)
        self.preview.finished.connect(self.transport_finished)
        self.preview.play_button.clicked.disconnect()
        self.preview.play_button.clicked.connect(self.toggle_transport)
        self.preview.start_button.clicked.disconnect()
        self.preview.start_button.clicked.connect(lambda:self.seek_transport(0))
        self.preview.stop_button.clicked.connect(lambda:self.seek_transport(0) if self.timeline.scope.currentIndex() == 1 else None)
        self._scrubbing = False
        self._scrub_target = None
        self._scrub_resume = False
        self._scrub_timer = QTimer(self)
        self._scrub_timer.setInterval(120)
        self._scrub_timer.timeout.connect(self.flush_timeline_seek)
        self.timeline.canvas.scrub_started.connect(self.begin_timeline_scrub)
        self.timeline.canvas.scrub_finished.connect(self.end_timeline_scrub)
        self.timeline.canvas.seek_requested.connect(self.request_timeline_seek)
        self.timeline.canvas.clip_seek_requested.connect(self.seek_transport)
        self.timeline.canvas.subtitle_selected.connect(self.timeline_select)
        self.timeline.canvas.block_moved.connect(self.move_timeline_block)
        self.timeline.canvas.subtitle_resized.connect(self.resize_timeline_subtitle)
        self.timeline.link.clicked.connect(self.change_link)
        self.timeline.undo.clicked.connect(self.undo_subtitle)
        self.timeline.earlier.clicked.connect(lambda:self.reorder_media(-1))
        self.timeline.later.clicked.connect(lambda:self.reorder_media(1))
        self.timeline.scope.currentIndexChanged.connect(self.scope_changed)
        vertical.addWidget(self.timeline)
        vertical.setChildrenCollapsible(False)
        vertical.setSizes([495, 335])
        layout.addWidget(vertical, 1)
        menu = self.menuBar().addMenu("파일")
        for title, shortcut, callback in (
            ("새 프로젝트", QKeySequence.StandardKey.New, self.new_project),
            ("프로젝트 열기", QKeySequence.StandardKey.Open, self.open_project_dialog),
            ("프로젝트 저장", QKeySequence.StandardKey.Save, lambda: self.save_current()),
            ("다른 이름으로 저장", QKeySequence.StandardKey.SaveAs, lambda: self.save_current(True)),
        ):
            action = QAction(title, self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            menu.addAction(action)
        menu.addSeparator()
        self.export_action = QAction("SRT 내보내기…", self)
        self.export_action.setEnabled(False)
        self.export_action.triggered.connect(lambda:self.export_current_subtitles())
        menu.addAction(self.export_action)
        self.video_export_action=QAction("편집본 영상 출력…",self)
        self.video_export_action.setEnabled(False)
        self.video_export_action.triggered.connect(self.export_edit_video)
        menu.addAction(self.video_export_action)
        self.playback_keys = PlaybackKeys(self)
        self.history_keys = HistoryKeys(self)
        self.drop_import = VideoDropImport(self)
        self.selection_interaction=SelectionInteraction(self)
        self.timeline_focus=TimelineFocus(self)
        self.timeline.canvas.clear_requested.connect(self.clear_workspace_selection)
        self.init_workspace()
        self.init_organizer()
        self.init_project_history()
        close_project_action=QAction("현재 프로젝트 닫기",self)
        close_project_action.setShortcut(QKeySequence("Ctrl+W"))
        close_project_action.triggered.connect(self.close_current_project)
        menu.addAction(close_project_action)
        self.timeline.undo.setToolTip("실행 취소 Ctrl+Z · 다시 실행 Ctrl+Shift+Z · 현재 프로젝트 작업")
        self.statusBar().showMessage("●  자동 생성 → 검수·수정 → 영상 위 표시 → SRT 출력")

    def export_edit_video(self):
        seq=self.active_sequence()
        if not seq or not self.resolve_subtitle_edit() or self.subtitle_job.busy:return
        if self.preview._playing:self.preview.toggle_play()
        from app.ui.video_export_dialog import VideoExportDialog
        rows=self.timeline.canvas.segments
        dialog=VideoExportDialog(seq,rows,self)
        dialog.exec();dialog.deleteLater()

    def open_silence_editor(self):
        if self.subtitle_job.busy or not self.resolve_subtitle_edit():
            return
        source = self.media.selected_path()
        if not source or not Path(source).is_file():
            self.statusBar().showMessage("먼저 원본 영상을 선택하세요.")
            return
        self.abort_timeline_scrub()
        if self.preview._playing:
            self.preview.toggle_play()
        from app.ui.silence_dialog import SilenceDialog
        dialog = SilenceDialog(source, self)
        dialog.exec()
        if dialog.applied_ranges is not None:
            self.create_edit_sequence(source,dialog.applied_ranges,dialog.duration)
        dialog.deleteLater()

    def rename_project(self):
        previous = self.project.name
        if not self.project.rename(self.project_name.text()):
            self.project_name.setText(self.project.name)
        self.project_name.setText(self.project.name)
        if previous != self.project.name:
            self.mark_dirty()
        self.refresh_title()

    def select_tab(self, button):
        if button.text()=='내보내기':
            if self.active_sequence():self.export_edit_video()
            else:self.statusBar().showMessage('출력할 편집본을 먼저 선택하세요.')
            return
        self.mode_label.setText(f"{button.text()} 작업 공간")
        self.statusBar().showMessage(f"{button.text()} 탭 선택 · 현재 공통 스튜디오 레이아웃을 표시합니다. 영상 불러오기·재생 가능 / 자동 생성·검수·영상 자막·SRT 출력 가능")

    def activate_tab(self, name):
        for button in self.tabs.buttons():
            if button.text() == name:
                button.click()
                break

    def show_roadmap(self):
        QMessageBox.information(self, "V0.1 개발 계획", "\n".join(f"{i}. {name} — {state}" for i, (name, state) in enumerate(ROADMAP, 1)))

    def open_media(self, path):
        if self.active_sequence() and not self._opening_edit_sequence and not self._workspace_loading:
            self.statusBar().showMessage("보관함에 원본을 추가했습니다. 현재 작업본은 유지됩니다.")
            return
        if hasattr(self, "subtitle_job") and self.subtitle_job.busy:
            return
        if not self.resolve_subtitle_edit():
            from PySide6.QtCore import QSignalBlocker
            with QSignalBlocker(self.media.listing):
                for i in range(self.media.listing.count()):
                    if self.media.listing.item(i).toolTip() == self.editor_source:
                        self.media.listing.setCurrentRow(i)
                        break
            return
        if self.active_edit_id and not self._opening_edit_sequence:
            self.timeline.sequence_tabs.setCurrentIndex(0)
        if self.project.active_path != path:
            self.project.active_path = path
            self.mark_dirty()
        self.show_source_subtitles()
        try:
            self.preview.open_video(path)
            self.update_subtitle_controls()
            self.show_source_subtitles()
            self.timeline.info.setText("원본 영상 확인 중 · 편집 클립 없음")
        except ValueError as exc:
            self.media_error(str(exc))

    def media_loaded(self, path, duration):
        from pathlib import Path
        from app.core.media import timecode
        self.duration_cache[path] = duration
        self.statusBar().showMessage(f"영상 준비 완료 · {Path(path).name} · {timecode(duration)} · 원본 재생")
        self.preview.status.setText(self.media.display_name(path))
        self.preview.status.setToolTip(path)
        self.timeline.info.setText("원본 미리보기 중 · 편집 클립 없음")
        self.show_source_subtitles()
        self.update_subtitle_controls()
        if self.pending_seek is not None:
            position, resume = self.pending_seek
            self.pending_seek = None
            self.preview.seek_timeline(position)
            if resume and not self.preview._playing:
                self.preview.toggle_play()

    def media_error(self, message):
        self.media.refresh_controls()
        self.statusBar().showMessage(f"영상 오류: {message}")
        if hasattr(self, "subtitle_panel"):
            self.update_subtitle_controls()
        if not self.preview.ready:
            self.timeline.info.setText("영상 로드 실패 · 편집 클립 없음")

    def closeEvent(self, event):
        if self.subtitle_job.busy:
            answer = QMessageBox.question(self, "자막 생성 중", "생성을 취소하고 종료할까요?")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.subtitle_job.shutdown()
        if not self.resolve_subtitle_edit():
            event.ignore()
            return
        self.rename_project()
        if not self.confirm_all_projects():
            event.ignore()
            return
        self.subtitle_job.shutdown()
        self.abort_timeline_scrub()
        self.preview.shutdown()
        super().closeEvent(event)

    def refresh_title(self):
        self.setWindowTitle(f"{'* ' if self.dirty else ''}{self.project.name} · AI Video Studio V0.3 / 검색·장면 태그")
        self.save_state.setText("변경됨" if self.dirty else ("저장됨" if self.project_path else "저장 안 됨"))

    def mark_dirty(self):
        self.dirty = True
        # Removing or relinking a source invalidates its old recognition result.
        paths = set(self.media.paths())
        self.project.media_placements = {p:v for p,v in self.project.media_placements.items() if p in paths}
        self.project.subtitles = {p: s for p, s in self.project.subtitles.items() if p in paths}
        self.project.subtitle_runs = {p: s for p, s in self.project.subtitle_runs.items() if p in paths}
        if self.preview.source and self.preview.ready:
            self.preview.refresh_title()
        self.project.edit_sequences = [s for s in self.project.edit_sequences if sequence_sources(s)<=paths]
        parents={s['id'] for s in self.project.edit_sequences if not s.get('parent_id')}
        self.project.edit_sequences[:]=[s for s in self.project.edit_sequences if not s.get('parent_id') or s['parent_id'] in parents]
        if self.active_edit_id and self.active_sequence() is None:
            self.active_edit_id = None
            self.preview.set_sequence_ranges(None)
        self.sync_sequence_tabs()
        self.refresh_title()

    def _save_current_single(self, save_as=False, path=None):
        if not self.resolve_subtitle_edit():
            return False
        self.rename_project()
        destination = path or (None if save_as else self.project_path)
        if destination is None:
            destination, _ = QFileDialog.getSaveFileName(self, "프로젝트 저장", str(self.project_path or "Untitled.avsp"), "AI Video Studio (*.avsp)")
            if not destination:
                return False
            if not str(destination).lower().endswith(".avsp"):
                destination += ".avsp"
        if self.destination_in_use(destination):
            QMessageBox.warning(self,"저장 실패","다른 열린 프로젝트와 같은 파일에 저장할 수 없습니다.")
            return False
        self.project.media_paths = self.media.paths()
        self.project.active_path = self.media.selected_path()
        self.project.media_names = self.media.names()
        self.project.subtitle_terms = self.subtitle_panel.terms.text().strip()
        self.project.subtitle_skip_silence = self.subtitle_panel.skip_silence.isChecked()
        try:
            save_project(self.project, destination)
        except ValueError as exc:
            QMessageBox.warning(self, "저장 실패", str(exc))
            return False
        self.project_path = Path(destination).resolve()
        self.dirty = False
        self.refresh_title()
        self.statusBar().showMessage(f"프로젝트 저장 완료 · {self.project_path}")
        return True

    def confirm_discard(self):
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, "저장하지 않은 변경", f"‘{self.project.name}’의 변경 내용을 저장할까요?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Save:
            return self.save_current()
        return answer == QMessageBox.StandardButton.Discard

    def open_project_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '프로젝트 열기', '', 'AI Video Studio (*.avsp)')
        for path in paths:
            if not self.open_project_path(path):
                break

    def _apply_project_single(self, project, path):
        self.abort_timeline_scrub()
        self.timeline.canvas.drag=None
        self.timeline.canvas.preview_blocks=None
        self.timeline.canvas.selected_keys=set()
        self.timeline.canvas.selected_subtitles=set()
        self.editor_source = None
        self.subtitle_history = {}
        self.subtitle_redo = {}
        self.preview.shutdown()
        self.preview.source = None
        self.preview.ready = False
        self.preview.empty.setText("영상 파일을 선택하세요")
        self.preview.stack.setCurrentWidget(self.preview.empty)
        self.preview.status.setText("미디어 없음")
        self.preview.update_controls()
        self.active_edit_id = None
        self.project_undo=[]
        self.project_redo=[]
        self.closed_sequence_ids=set()
        self.sequence_history = {}
        self.sequence_redo = {}
        self.preview.set_sequence_ranges(None)
        self.project = project
        self.sync_sequence_tabs()
        self.subtitle_panel.terms.setText(project.subtitle_terms)
        self.subtitle_panel.skip_silence.setChecked(project.subtitle_skip_silence)
        self.project_path = path
        self.project_name.setText(project.name)
        self.media.restore(project.media_paths, project.active_path, project.media_names)
        self.timeline.info.setText("클립 0개 · 프로젝트 불러옴")
        if project.active_path:
            self.open_media(project.active_path)
        self.show_source_subtitles()
        self.update_subtitle_controls()
        missing = sum(not Path(p).is_file() for p in project.media_paths)
        self.dirty = False
        self.refresh_title()
        self.statusBar().showMessage(f"프로젝트 열기 완료 · 미디어 {len(project.media_paths)}개" + (f" · 찾을 수 없는 영상 {missing}개: 목록 선택 후 ‘파일 찾기’" if missing else ""))

    def clear_media(self):
        self.preview.shutdown()
        self.preview.ready = False
        self.preview.source = None
        self.project.active_path = None
        self.project.media_paths = []
        self.project.media_names = {}
        self.project.subtitles = {}
        self.project.subtitle_runs = {}
        self.project.media_placements = {}
        self.project.edit_sequences = []
        self.active_edit_id = None
        self.sync_sequence_tabs()
        self.preview.empty.setText("영상 파일을 불러오세요\nMP4 · MOV")
        self.preview.stack.setCurrentWidget(self.preview.empty)
        self.preview.status.setText("미디어 없음")
        self.preview.update_controls()
        self.timeline.info.setText("클립 0개 · 빈 프로젝트")
        self.show_source_subtitles()
        self.update_subtitle_controls()
        self.statusBar().showMessage("목록에서 제거했습니다. 원본 파일은 유지됩니다. 변경 내용을 저장하세요.")

    def allow_project_switch(self):
        if not self.resolve_subtitle_edit():
            return False
        if self.subtitle_job.busy:
            self.statusBar().showMessage("자막 생성 중입니다. 먼저 자막 패널의 ‘취소’를 눌러주세요.")
            return False
        return True

    def update_subtitle_controls(self, *_):
        if not hasattr(self, "subtitle_job"):
            return
        available = (bool(self.active_sequence()) and self.preview.ready
                     and self.work_has_audio()
                     and recognition_installed() and not self.subtitle_job.busy)
        self.subtitle_panel.generate.setEnabled(available)
        if not self.subtitle_job.busy:
            if not recognition_installed():
                self.subtitle_panel.status.setText("음성 인식 패키지가 필요합니다. requirements.txt 설치 후 앱을 다시 실행하세요.")
            elif not self.preview.ready:
                self.subtitle_panel.status.setText("음성이 있는 영상을 선택하세요.")
            elif self.active_sequence() and not self.work_has_audio():
                self.subtitle_panel.status.setText("선택한 작업본에 음성 트랙이 없습니다.")
            elif self.subtitle_panel.status.text() in ("음성이 있는 영상을 선택하세요.", "영상에 음성 트랙이 없습니다."):
                self.subtitle_panel.status.setText("생성 준비됨 · 완료 후 검수·수정하세요.")

    def show_source_subtitles(self, select=-1, force=False):
        if self.render_edit_sequence():
            if select>=0:self.subtitle_panel.editor.set_selection(select)
            return
        self.preview.edit_name=""
        self.preview.set_sequence_ranges(None)
        if hasattr(self,"video_export_action"):self.video_export_action.setEnabled(False)
        self.subtitle_panel.setEnabled(False)
        self.subtitle_panel.status.setText("아래 편집본 목록에서 작업 대상을 선택하세요.")
        self.timeline.canvas.sequence_view = False
        self.timeline.begin_edit.show()
        self.timeline.begin_edit.setEnabled(self.preview.ready and not self.subtitle_job.busy)
        self.timeline.begin_edit.setToolTip("독립 작업본을 아래 편집본 목록에 만들어 편집합니다.")
        self.timeline.canvas.preview_blocks = None
        self.timeline.split_button.hide()
        self.timeline.delete_button.hide()
        for control in (self.timeline.scope,self.timeline.earlier,self.timeline.later):
            control.hide()
        self.timeline.hint.setText("원본 확인 중 · 빈 곳 드래그: 선택 · 편집 시작 / Ctrl+K / Shift+드래그: 새 편집본")
        for control in (self.timeline.scope,self.timeline.link,self.timeline.earlier,self.timeline.later,self.timeline.undo):
            control.setEnabled(True)
        path = self.media.selected_path()
        segments = self.project.subtitles.get(path, [])
        info = self.project.subtitle_runs.get(path, {})
        language = info.get("language", self.subtitle_panel.language.currentData())
        if force or self.editor_source != path or self.subtitle_panel.editor.segments != segments:
            self.subtitle_panel.show_segments(segments, language, select)
            self.editor_source = path
        self.preview.set_subtitles(segments)
        placement = self.placement(path)
        if (self.preview.video_offset,self.preview.audio_offset) != (round(placement["video"]*1000),round(placement["audio"]*1000)):
            self.preview.set_placements(placement["video"],placement["audio"])
        self.export_action.setEnabled(bool(segments) or (self.timeline.scope.currentIndex() == 1 and any(self.project.subtitles.values())))
        self.subtitle_panel.editor.run_info.setText(
            (f"{info.get('model', '모델 미기록')} · {info.get('language', '언어 미기록')} · "
            + ("조용한 구간 건너뜀" if info.get("skip_silence") else "전체 구간 분석"))
            if info else "이전 결과 · 생성 설정 미기록")
        self.subtitle_panel.editor.run_info.setToolTip(info.get("created_at", "생성 일시 미기록"))
        if hasattr(self.timeline, "set_source"):
            duration = self.preview.player.duration() if self.preview.ready else 0
            self.timeline.set_source(self.preview.timeline_duration() if self.preview.ready else duration, segments,
                self.media.display_name(path) if path else "", duration, **placement)
            if self.timeline.scope.currentIndex() == 1:
                self.refresh_sequence()
        self.update_history_controls()

    def generate_subtitles(self, model, language):
        if self.active_sequence():
            self.generate_work_subtitles(model,language)
            return
        if not self.resolve_subtitle_edit():
            return
        if not self.subtitle_panel.generate.isEnabled() or self.subtitle_job.busy:
            return
        source = self.media.selected_path()
        if source in self.project.subtitles and self.project.subtitles[source]:
            answer = QMessageBox.question(self, "자막 다시 생성", "완료되면 기존 자막을 새 결과로 바꿉니다. 계속할까요?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        # Project-local cache avoids changing system Python or GPU configuration.
        cache = self.whisper_cache
        self.subtitle_panel.set_busy(True)
        self.media.setEnabled(False)
        self.timeline.setEnabled(False)
        self.subtitle_panel.status.setToolTip("")
        self.subtitle_panel.status.setText("음성 인식 작업 시작 중…")
        try:
            if not self.subtitle_job.start(source, model, language, cache, self.subtitle_panel.terms.text(), self.subtitle_panel.skip_silence.isChecked()):
                self.subtitle_finished()
        except (OSError, ValueError) as exc:
            self.subtitle_failed(str(exc))
            self.subtitle_finished()

    def subtitles_ready(self, source, segments):
        if getattr(self,"_work_caption_job",None):
            self.work_subtitles_ready(segments)
            return
        if hasattr(self,"recheck_dialog") and self.recheck_dialog.running:
            self.recheck_dialog.receive(source,segments)
            return
        if source not in self.media.paths():
            return
        self.subtitle_panel.status.setToolTip("")
        self.remember_subtitles(source)
        offset = self.placement(source)["video"]
        segments = [dict(row,start=round(row["start"]+offset,3),end=round(row["end"]+offset,3)) for row in segments]
        self.project.subtitles[source] = segments
        self.project.subtitle_runs[source] = deepcopy(self.subtitle_job.run_info)
        self.mark_dirty()
        self.show_source_subtitles(select=0, force=True)
        self.subtitle_panel.tabs.setCurrentIndex(1)
        text = f"자막 {len(segments)}개 생성 완료 · 프로젝트를 저장하세요." if segments else "인식된 음성이 없습니다. 언어·모델·음질을 확인하세요."
        self.subtitle_panel.status.setText(text)
        self.timeline.info.setText(f"생성 자막 {len(segments)}개 · 검수·수정 가능")
        self.statusBar().showMessage(text)

    def subtitle_failed(self, message):
        if hasattr(self,"recheck_dialog") and self.recheck_dialog.running:
            self.recheck_dialog.status.setText("재검토 실패 · 기존 자막 유지 · "+message)
        self.subtitle_panel.status.setText("생성에 실패했습니다. 기존 자막은 유지됩니다.")
        self.subtitle_panel.status.setToolTip(message)
        self.statusBar().showMessage(message.splitlines()[0])

    def subtitle_finished(self):
        if getattr(self,"_work_caption_temp",None):
            self._work_caption_temp.cleanup();self._work_caption_temp=None
        self._work_caption_job=None
        if hasattr(self,"recheck_dialog") and self.recheck_dialog.running:
            self.recheck_dialog.finish()
        self.media.setEnabled(True)
        self.timeline.setEnabled(True)
        self.subtitle_panel.set_busy(False)
        self.update_subtitle_controls()
        self.update_history_controls()

    def subtitle_terms_changed(self, text):
        self.project.subtitle_terms = text.strip()
        self.mark_dirty()

    def subtitle_filter_changed(self, checked):
        self.project.subtitle_skip_silence = checked
        self.mark_dirty()

    def resolve_subtitle_edit(self):
        if not hasattr(self, "subtitle_panel") or not self.subtitle_panel.editor.pending:
            return True
        answer = QMessageBox.question(self, "미적용 자막 수정", "수정 중인 자막을 적용할까요?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Save:
            return self.apply_subtitle_edit()
        if answer == QMessageBox.StandardButton.Discard:
            self.subtitle_panel.editor.set_selection(self.subtitle_panel.editor.selected_index)
            return True
        return False

    def remember_subtitles(self, path):
        self.subtitle_redo.pop(path, None)
        stack = self.subtitle_history.setdefault(path, [])
        stack.append(self.edit_snapshot(path))
        del stack[:-30]

    def subtitle_duration(self):
        if self.active_sequence():return self.preview.timeline_duration()/1000
        if self.preview.ready and str(self.preview.source) == self.media.selected_path():
            return self.preview.timeline_duration() / 1000
        return None

    def apply_subtitle_edit(self):
        if self.active_sequence():
            editor=self.subtitle_panel.editor
            if self.subtitle_job.busy:return False
            try:
                rows,index=edit_segment(self.timeline.canvas.segments,editor.selected_index,editor.start.value(),editor.end.value(),editor.text.toPlainText(),None)
                self.commit_work_subtitles(rows,index)
                self.seek_transport(round(rows[index]['start']*1000))
                return True
            except ValueError as exc:QMessageBox.warning(self,'자막 수정 확인',str(exc));return False
        editor = self.subtitle_panel.editor
        source = self.editor_source
        if not source or self.subtitle_job.busy:
            return False
        try:
            segments, index = edit_segment(self.project.subtitles.get(source, []), editor.selected_index,
                editor.start.value(), editor.end.value(), editor.text.toPlainText(),
                None)
        except ValueError as exc:
            QMessageBox.warning(self, "자막 수정 확인", str(exc))
            return False
        self.remember_subtitles(source)
        self.project.subtitles[source] = segments
        self.mark_dirty()
        self.show_source_subtitles(index, force=True)
        if self.preview.ready:
            self.preview.seek_timeline(round(segments[index]["start"] * 1000))
        self.statusBar().showMessage("자막 수정을 적용했습니다. 프로젝트를 저장하세요.")
        return True

    def select_subtitle(self, row):
        editor = self.subtitle_panel.editor
        target = deepcopy(editor.segments[row]) if 0 <= row < len(editor.segments) else None
        if not self.resolve_subtitle_edit():
            with QSignalBlocker(editor.table):
                if editor.selected_index >= 0:
                    editor.table.setCurrentCell(editor.selected_index, 0)
            return
        if target is not None:
            row = next((i for i, s in enumerate(editor.segments) if s == target), row)
        editor.set_selection(row)
        if 0 <= row < len(editor.segments) and self.preview.ready:
            self.preview.seek_timeline(round(editor.segments[row]["start"] * 1000))
        self.subtitle_panel.tabs.setCurrentIndex(1)

    def add_subtitle(self):
        if self.active_sequence():
            if self.subtitle_job.busy or not self.resolve_subtitle_edit():return
            rows=deepcopy(self.timeline.canvas.segments)
            start=self.preview.timeline_position()/1000
            end=min(start+2,self.preview.timeline_duration()/1000)
            if end<=start:return
            row=dict(start=start,end=end,text='새 자막',reviewed=False);rows.append(row);rows.sort(key=lambda r:r['start'])
            self.commit_work_subtitles(rows,rows.index(row),message='작업본 자막 추가')
            self.subtitle_panel.tabs.setCurrentIndex(1);self.subtitle_panel.editor.text.setFocus();self.subtitle_panel.editor.text.selectAll()
            return
        if not self.resolve_subtitle_edit() or self.subtitle_job.busy:
            return
        source = self.media.selected_path()
        if not source:
            self.statusBar().showMessage("먼저 영상을 선택하세요.")
            return
        duration = self.subtitle_duration()
        start = self.preview.timeline_position() / 1000 if self.preview.ready else 0
        if duration is not None:
            start = min(start, max(0, duration - 2))
        end = min(start + 2, duration) if duration is not None else start + 2
        if end <= start:
            return
        self.remember_subtitles(source)
        segments = deepcopy(self.project.subtitles.get(source, []))
        row = {"start": round(start, 3), "end": round(end, 3), "text": "새 자막", "reviewed": False}
        segments.append(row)
        segments.sort(key=lambda s: s["start"])
        index = next(i for i, s in enumerate(segments) if s is row)
        self.project.subtitles[source] = segments
        self.mark_dirty()
        self.show_source_subtitles(index, force=True)
        self.subtitle_panel.tabs.setCurrentIndex(1)
        self.subtitle_panel.editor.text.setFocus()
        self.subtitle_panel.editor.text.selectAll()

    def remove_subtitle(self):
        if self.active_sequence():
            if self.subtitle_job.busy or not self.resolve_subtitle_edit():return
            index=self.subtitle_panel.editor.selected_index;rows=self.timeline.canvas.segments
            if 0<=index<len(rows):self.commit_work_subtitles([r for i,r in enumerate(rows) if i!=index],max(0,index-1),message='작업본 자막 삭제')
            return
        if not self.resolve_subtitle_edit() or self.subtitle_job.busy:
            return
        source = self.editor_source
        index = self.subtitle_panel.editor.selected_index
        segments = self.project.subtitles.get(source, [])
        if not 0 <= index < len(segments):
            return
        self.remember_subtitles(source)
        self.project.subtitles[source] = [s for i, s in enumerate(segments) if i != index]
        self.mark_dirty()
        self.show_source_subtitles(min(index, len(segments) - 2), force=True)

    def edit_snapshot(self, source):
        return {"segments":deepcopy(self.project.subtitles.get(source,[])),
                "run":deepcopy(self.project.subtitle_runs.get(source)),
                "placement":deepcopy(self.placement(source))}

    def restore_edit(self, source, snapshot):
        self.project.subtitles[source] = snapshot["segments"]
        self.project.media_placements[source] = snapshot["placement"]
        if snapshot["run"] is None:
            self.project.subtitle_runs.pop(source,None)
        else:
            self.project.subtitle_runs[source] = snapshot["run"]
        self.mark_dirty()
        self.show_source_subtitles(force=True)

    def undo_subtitle(self):
        self.change_edit_history(False)

    def redo_subtitle(self):
        self.change_edit_history(True)

    def change_edit_history(self, redo):
        if hasattr(self,"project_undo"):
            self.change_project_history(redo)
            return
        if self.active_sequence():
            self.change_sequence_history(redo)
            return
        if self.subtitle_job.busy or not self.resolve_subtitle_edit():
            return
        source = self.media.selected_path()
        history = self.subtitle_redo if redo else self.subtitle_history
        opposite = self.subtitle_history if redo else self.subtitle_redo
        stack = history.get(source,[])
        if stack:
            opposite.setdefault(source,[]).append(self.edit_snapshot(source))
            del opposite[source][:-30]
            self.restore_edit(source,stack.pop())
            self.statusBar().showMessage("다시 실행했습니다." if redo else "실행 취소했습니다.")
        else:
            self.statusBar().showMessage("다시 실행할 작업이 없습니다." if redo else "실행 취소할 작업이 없습니다.")

    def export_current_subtitles(self, path=None):
        if self.active_sequence():
            if not self.resolve_subtitle_edit():return False
            rows=self.timeline.canvas.segments
            if not rows:return False
            if any(not r.get('reviewed') for r in rows) and QMessageBox.question(self,'미검수 자막 포함','현재 작업본의 미검수 자막도 SRT로 저장할까요?')!=QMessageBox.StandardButton.Yes:return False
            if path is None:path,_=QFileDialog.getSaveFileName(self,'작업본 SRT 내보내기',self.active_sequence()['name']+'.srt','SubRip 자막 (*.srt)')
            if not path:return False
            if not str(path).lower().endswith('.srt'):path=str(path)+'.srt'
            try:export_srt(rows,path)
            except ValueError as exc:QMessageBox.warning(self,'SRT 저장 실패',str(exc));return False
            self.statusBar().showMessage('작업본 자막 저장 완료');return True
        if not self.resolve_subtitle_edit():
            return False
        source = self.media.selected_path()
        segments = self.project.subtitles.get(source, [])
        if self.timeline.scope.currentIndex() == 1 and self.subtitle_panel.editor.export_basis.currentData() == "timeline":
            self.refresh_sequence()
            segments = self.timeline.canvas.segments
        if not segments:
            self.statusBar().showMessage("내보낼 자막이 없습니다.")
            return False
        if any(not s.get("reviewed") for s in segments):
            answer = QMessageBox.question(self, "미검수 자막 포함", "아직 검수 완료하지 않은 자막이 있습니다. 현재 내용으로 SRT를 저장할까요?")
            if answer != QMessageBox.StandardButton.Yes:
                return False
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, "SRT 내보내기", Path(source).stem + ".srt", "SubRip 자막 (*.srt)")
            if not path:
                return False
            if not str(path).lower().endswith(".srt"):
                path += ".srt"
        try:
            if self.subtitle_panel.editor.export_basis.currentData() == "source":
                offset = self.placement(source)["video"]
                segments = [dict(row,start=round(row["start"]-offset,3),end=round(row["end"]-offset,3)) for row in segments]
                if any(row["start"] < 0 for row in segments):
                    raise ValueError("영상 시작보다 앞선 자막이 있습니다. 타임라인 기준으로 출력하거나 시간을 수정하세요.")
            export_srt(segments, path)
        except ValueError as exc:
            QMessageBox.warning(self, "SRT 저장 실패", str(exc))
            return False
        self.statusBar().showMessage(f"SRT 저장 완료 · {path}")
        return True


install_history_actions(MainWindow)
