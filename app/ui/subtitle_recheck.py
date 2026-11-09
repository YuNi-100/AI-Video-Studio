"""Non-destructive source caption candidates with explicit per-window approval."""
import json
import tempfile
from copy import deepcopy
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QDoubleSpinBox,
    QPushButton,QTableWidget,QTableWidgetItem,QHeaderView,QCheckBox,QPlainTextEdit)
from app.features.subtitles.recheck import plan_ranges, apply_candidates, overlaps
from app.features.subtitles.model import validate_segments, subtitle_time
from app.features.subtitles.editing import review_reasons
from app.ui.project_history import project_action
from app.ui.apply_checkbox import ApplyCheckDelegate


class SubtitleRecheck(QDialog):
    def __init__(self, studio):
        super().__init__(studio)
        self.studio = studio
        self.running = False
        self.request_path = None
        self.candidates = None
        self.listen_end = None
        self.listen_timer = QTimer(self)
        self.listen_timer.setInterval(50)
        self.listen_timer.timeout.connect(self.stop_at_end)
        self.setWindowTitle('자막 재검토 · 기존 자막과 비교')
        self.resize(1040,620)
        layout = QVBoxLayout(self)
        self.source_label = QLabel()
        layout.addWidget(self.source_label)
        self.basis_label=QLabel('작업본 시간 기준 · 앞뒤 2초를 함께 듣고 최대 30초 단위로 비교합니다. 새 후보도 검수가 필요합니다.')
        layout.addWidget(self.basis_label)
        bar = QHBoxLayout()
        self.scope = QComboBox()
        self.scope.addItems(['전체 구간','지정 구간','의심 구간만'])
        bar.addWidget(self.scope)
        self.start,self.end = QDoubleSpinBox(),QDoubleSpinBox()
        for name,control in [('시작',self.start),('종료',self.end)]:
            control.setRange(0,604800)
            control.setDecimals(3)
            control.setSuffix(' 초')
            bar.addWidget(QLabel(name))
            bar.addWidget(control)
        selected = QPushButton('선택 자막 구간')
        selected.clicked.connect(self.use_selection)
        bar.addWidget(selected)
        self.generate = QPushButton('재검토 시작')
        self.generate.clicked.connect(self.begin)
        bar.addWidget(self.generate)
        self.cancel = QPushButton('인식 취소')
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(studio.subtitle_job.cancel)
        bar.addWidget(self.cancel)
        layout.addLayout(bar)
        self.settings = QLabel()
        layout.addWidget(self.settings)
        self.table = QTableWidget(0,5)
        self.table.setItemDelegateForColumn(0,ApplyCheckDelegate(self.table))
        self.table.setHorizontalHeaderLabels(['적용','원본 구간','기존 자막','새 후보','후보 선택'])
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0,64)
        self.table.setColumnWidth(1,165)
        self.table.setColumnWidth(4,100)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(lambda row,col:self.listen(row) if col!=0 else None)
        layout.addWidget(self.table,1)
        details = QHBoxLayout()
        self.old_detail,self.new_detail = QPlainTextEdit(),QPlainTextEdit()
        for name,control in [('기존 자막 전체',self.old_detail),('선택 후보 전체',self.new_detail)]:
            control.setReadOnly(True)
            control.setPlaceholderText(name+' · 위에서 구간을 선택하세요.')
            control.setAccessibleName(name)
            control.setMinimumHeight(80)
            control.setMaximumHeight(110)
            details.addWidget(control)
        layout.addLayout(details)
        self.table.currentCellChanged.connect(lambda *_:self.update_details())
        foot = QHBoxLayout()
        self.protect = QCheckBox('검수 완료 자막 보호')
        self.protect.setChecked(True)
        self.protect.toggled.connect(self.render)
        foot.addWidget(self.protect)
        listen = QPushButton('선택 구간 재생')
        listen.clicked.connect(lambda:self.listen(self.table.currentRow()))
        foot.addWidget(listen)
        foot.addStretch()
        self.apply = QPushButton('체크한 후보만 적용')
        self.apply.setEnabled(False)
        self.apply.clicked.connect(self.apply_selected)
        foot.addWidget(self.apply)
        layout.addLayout(foot)
        self.status = QLabel('기존 자막은 그대로 유지됩니다. 비교 후 적용할 구간만 체크하세요.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def prepare(self):
        w = self.studio
        self.project_ref = w.project
        seq=w.active_sequence()
        self.sequence_id=seq["id"] if seq else None
        self.sequence_snapshot=deepcopy(seq)
        self.work=None
        self.source = seq["source"] if seq else w.media.selected_path()
        stat = Path(self.source).stat()
        self.source_stamp = (stat.st_size,stat.st_mtime_ns)
        self.snapshot = deepcopy(w.timeline.canvas.segments if seq else w.project.subtitles.get(self.source,[]))
        self.offset = 0 if seq else w.placement(self.source)['video']
        self.duration = w.preview.timeline_duration()/1000 if seq else w.preview.player.duration()/1000
        self.model = w.subtitle_panel.model.currentData()
        self.language = w.subtitle_panel.language.currentData()
        self.terms = w.subtitle_panel.terms.text()
        self.vad = w.subtitle_panel.skip_silence.isChecked()
        self.source_label.setText('재검토 대상: '+(seq['name'] if seq else w.media.display_name(self.source)))
        self.settings.setText(f'{self.model} · {self.language} · 기본 설정 / 용어 힌트 제외 후보 비교 · 적용 후 Ctrl+Z로 되돌리기')
        self.end.setValue(self.duration)
        self.start.setValue(0)
        self.candidates = None
        self.table.setRowCount(0)
        self.old_detail.clear()
        self.new_detail.clear()
        self.apply.setEnabled(False)

    def use_selection(self):
        w = self.studio
        index = w.subtitle_panel.editor.selected_index
        if 0 <= index < len(self.snapshot):
            r = self.snapshot[index]
            self.scope.setCurrentIndex(1)
            self.start.setValue(max(0,r['start']-self.offset))
            self.end.setValue(min(self.duration,r['end']-self.offset))

    def unchanged(self):
        w = self.studio
        try:
            stat = Path(self.source).stat()
            if (stat.st_size,stat.st_mtime_ns) != self.source_stamp:
                return False
        except OSError:
            return False
        if self.sequence_id:
            return w.project is self.project_ref and w.active_edit_id==self.sequence_id and w.active_sequence()==self.sequence_snapshot
        return (w.project is self.project_ref and self.source in w.media.paths()
            and w.project.subtitles.get(self.source,[]) == self.snapshot
            and w.placement(self.source)['video'] == self.offset)

    def begin(self):
        w = self.studio
        if w.subtitle_job.busy or not w.resolve_subtitle_edit():
            return
        if not self.unchanged():
            self.status.setText('자막이나 프로젝트가 바뀌었습니다. 창을 닫고 다시 열어 주세요.')
            return
        try:
            self.ranges = plan_ranges(['full','range','suspect'][self.scope.currentIndex()],self.duration,
                self.snapshot,self.offset,self.start.value(),self.end.value(),self.language)
            self.listen_timer.stop()
            w.abort_timeline_scrub()
            if w.preview._playing:
                w.preview.toggle_play()
            with tempfile.NamedTemporaryFile(mode='w',suffix='.json',prefix='studio-recheck-',encoding='utf-8',delete=False) as stream:
                self.request_path = Path(stream.name)
                json.dump(self.ranges,stream)
            self.running = True
            self.candidates = None
            self.table.setRowCount(0)
            self.apply.setEnabled(False)
            self.generate.setEnabled(False)
            self.cancel.setEnabled(True)
            w.subtitle_panel.set_busy(True)
            w.media.setEnabled(False)
            w.timeline.setEnabled(False)
            self.status.setText('재검토 중 · 기본 후보와 힌트 제외 후보를 만듭니다. 기존 자막은 유지됩니다.')
            module='app.features.subtitles.recheck_worker';extra=['--request',str(self.request_path)]
            if self.sequence_id:
                self.work=tempfile.TemporaryDirectory(prefix='studio-work-recheck-')
                module='app.features.subtitles.sequence_worker';extra+=w.work_job_arguments(self.sequence_snapshot,self.work)
            if not w.subtitle_job.start(self.source,self.model,self.language,w.whisper_cache,self.terms,self.vad,
                    worker_module=module,extra_args=extra):
                self.finish()
                w.subtitle_finished()
        except (ValueError,OSError) as exc:
            self.status.setText(str(exc))
            self.finish()
            w.subtitle_finished()

    def receive(self, source, rows):
        try:
            alternate = validate_segments(self.studio.subtitle_job.run_info.get('alternate',[]))
            self.candidates = [deepcopy(rows),alternate]
            self.render()
            self.status.setText('재검토 완료 · 영상으로 확인하고 적용할 구간만 체크하세요. 빈 후보는 적용하지 않습니다.')
        except ValueError as exc:
            self.status.setText(str(exc))

    def render(self, *_):
        if self.candidates is None:
            return
        self.table.setRowCount(len(self.ranges))
        for i,(a,b) in enumerate(self.ranges):
            check = QTableWidgetItem()
            protected = self.protect.isChecked() and any(r.get('reviewed') and overlaps(r,a+self.offset,b+self.offset) for r in self.snapshot)
            check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable|(Qt.ItemFlag.NoItemFlags if protected else Qt.ItemFlag.ItemIsUserCheckable))
            check.setCheckState(Qt.CheckState.Unchecked)
            check.setToolTip('검수 완료 자막 보호 중' if protected else '이 구간의 기존 자막을 선택 후보로 바꿉니다.')
            self.table.setItem(i,0,check)
            self.table.setItem(i,1,QTableWidgetItem(subtitle_time(a)+' → '+subtitle_time(b)))
            old = '\n'.join(r['text'] for r in self.snapshot if overlaps(r,a+self.offset,b+self.offset))
            item = QTableWidgetItem(old or '(기존 자막 없음)')
            item.setToolTip(old)
            self.table.setItem(i,2,item)
            choice = QComboBox()
            choice.addItems(['기본 설정','힌트 제외'])
            choice.setFixedHeight(30)
            choice.currentIndexChanged.connect(lambda index,row=i:self.update_candidate(row,index))
            self.table.setCellWidget(i,4,choice)
            self.update_candidate(i,0)
            self.table.setRowHeight(i,90)
        self.apply.setEnabled(True)
        if self.ranges:
            self.table.setCurrentCell(0,1)
            self.update_details()

    def update_candidate(self, row, variant):
        a,b = self.ranges[row]
        rows = [r for r in self.candidates[variant] if overlaps(r,a,b)]
        text = '\n'.join(r['text'] for r in rows)
        flags = sorted({reason for reasons in review_reasons(rows,self.language) for reason in reasons})
        if flags:
            text = '확인 필요: '+' · '.join(flags)+'\n'+text
        item = QTableWidgetItem(text or '(인식된 후보 없음 · 기존 유지)')
        item.setToolTip(text)
        self.table.setItem(row,3,item)
        if self.table.currentRow() == row:
            self.update_details()

    def update_details(self):
        row = self.table.currentRow()
        for column,control in [(2,self.old_detail),(3,self.new_detail)]:
            item = self.table.item(row,column) if row >= 0 else None
            control.setPlainText((item.toolTip() or item.text()) if item else '')

    def listen(self, row):
        w = self.studio
        if self.running or self.candidates is None or not 0 <= row < len(self.ranges):
            return
        if not self.unchanged() or w.subtitle_job.busy or not w.resolve_subtitle_edit():
            self.status.setText('원본 자막이 바뀌었습니다. 다시 열어 재검토하세요.')
            return
        if not self.sequence_id and w.active_sequence():
            w.timeline.sequence_tabs.setCurrentIndex(0)
        if not self.sequence_id and w.media.selected_path() != self.source:
            w.media.restore(w.media.paths(),self.source,w.media.names())
            w.open_media(self.source)
        self.listen_end = round((self.ranges[row][1]+self.offset)*1000)
        self.listen_timer.start()
        position = round((self.ranges[row][0]+self.offset)*1000)
        if w.preview.ready:
            w.preview.seek_timeline(position)
            if not w.preview._playing:
                w.preview.toggle_play()
        else:
            w.pending_seek = (position,True)

    @project_action
    def apply_selected(self):
        w = self.studio
        if self.running or self.candidates is None or w.subtitle_job.busy or not w.resolve_subtitle_edit():
            return
        if not self.unchanged():
            self.status.setText('기존 자막이나 프로젝트가 바뀌어 적용을 중단했습니다. 다시 재검토하세요.')
            return
        replacements = []
        for i,(a,b) in enumerate(self.ranges):
            if self.table.item(i,0).checkState() != Qt.CheckState.Checked:
                continue
            variant = self.table.cellWidget(i,4).currentIndex()
            rows = [r for r in self.candidates[variant] if overlaps(r,a,b)]
            if rows:
                replacements.append((a,b,rows))
        if not replacements:
            self.status.setText('새 후보가 있는 구간을 체크하세요. 기존 자막은 유지됩니다.')
            return
        try:
            rows = apply_candidates(self.snapshot,replacements,self.offset,self.protect.isChecked())
            if self.sequence_id:
                w.commit_work_subtitles(rows,sequence_id=self.sequence_id,message="작업본 자막 재검토 적용")
            else:
                w.remember_subtitles(self.source)
                w.project.subtitles[self.source] = rows
            from datetime import datetime, timezone
            info = dict(w.active_sequence().get("subtitle_run",{}) if self.sequence_id else w.project.subtitle_runs.get(self.source,{}))
            info.update(recheck_model=self.model,recheck_language=self.language,recheck_at=datetime.now(timezone.utc).isoformat(),recheck_scope=f"{len(replacements)}개 구간 선택 적용")
            if self.sequence_id:w.active_sequence()["subtitle_run"]=info
            else:w.project.subtitle_runs[self.source] = info
            w.mark_dirty()
            if self.sequence_id or w.media.selected_path() == self.source:
                w.show_source_subtitles(force=True)
            self.apply.setEnabled(False)
            self.candidates = None
            self.status.setText(f'{len(replacements)}개 구간 적용 · 작업본 검수에서 Ctrl+Z로 되돌리기 · Ctrl+S로 저장하세요.')
        except ValueError as exc:
            self.status.setText(str(exc))

    def stop_at_end(self):
        w = self.studio
        if w.project is not self.project_ref or (w.active_edit_id!=self.sequence_id if self.sequence_id else w.media.selected_path()!=self.source or w.active_sequence()):
            self.listen_timer.stop()
            return
        if self.listen_end is not None and w.preview.timeline_position() >= self.listen_end:
            if w.preview._playing:
                w.preview.toggle_play()
            self.listen_timer.stop()

    def reject(self):
        self.close()

    def finish(self):
        self.running = False
        if self.work:self.work.cleanup();self.work=None
        self.generate.setEnabled(True)
        self.cancel.setEnabled(False)
        if self.request_path:
            self.request_path.unlink(missing_ok=True)
            self.request_path = None

    def closeEvent(self,event):
        if self.running:
            self.status.setText('먼저 인식 취소를 누르고 작업 종료 후 닫아 주세요.')
            event.ignore()
        else:
            self.listen_timer.stop()
            event.accept()
