"""Compact project-wide dialogue and scene index."""
from PySide6.QtCore import Qt, QTimer, QSignalBlocker
from PySide6.QtGui import QShortcut,QKeySequence
from uuid import uuid4
from copy import deepcopy
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QComboBox, QPushButton, QTreeWidget, QTreeWidgetItem, QLabel, QDoubleSpinBox,QInputDialog,QCheckBox)
from app.ui.project_history import project_action
from app.core.project import validate_display_name
from app.features.scene_search import search_edits, timestamp
from app.features.silence.sequence import sequence_layout, validate_sequence


class SceneSearch(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.studio = window
        self.setWindowTitle('대사 검색 · 장면 태그')
        self.resize(1000, 620)
        layout = QVBoxLayout(self)
        filters=QHBoxLayout()
        self.edit_filter=QComboBox();self.folder_filter=QComboBox()
        filters.addWidget(QLabel('편집본'));filters.addWidget(self.edit_filter,1)
        filters.addWidget(QLabel('분류'));filters.addWidget(self.folder_filter,1)
        folder_add=QPushButton('새 분류 폴더');folder_add.clicked.connect(self.new_folder)
        filters.addWidget(folder_add);layout.addLayout(filters)
        bar = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText('현재 프로젝트의 편집본에서 대사·태그 검색')
        self.kind = QComboBox()
        self.kind.addItems(['대사와 태그', '대사', '태그'])
        bar.addWidget(self.query, 1)
        bar.addWidget(self.kind)
        layout.addLayout(bar)
        self.results = QTreeWidget()
        self.results.setStyleSheet('QTreeWidget::indicator { width: 14px; height: 14px; border: 1px solid #8290aa; border-radius: 3px; background: #141b29; } QTreeWidget::indicator:checked { background: #9567ff; border-color: #cab3ff; }')
        self.results.setHeaderLabels(['선택','편집본', '종류', '편집본 시간', '대사 / 태그'])
        self.results.setRootIsDecorated(False)
        for col,width in enumerate((48,160,55,125)):self.results.setColumnWidth(col,width)
        layout.addWidget(self.results)
        actions=QHBoxLayout()
        self.select_all=QCheckBox('표시 항목 전체 선택');self.select_all.clicked.connect(self.check_all)
        actions.addWidget(self.select_all)
        self.checked_count=QLabel();actions.addWidget(self.checked_count);actions.addStretch()
        self.move_button=QPushButton('체크 항목 폴더 이동');self.move_button.clicked.connect(self.move_checked)
        self.delete_button=QPushButton('체크 자막·태그 삭제');self.delete_button.clicked.connect(self.delete_checked)
        self.delete_button.setToolTip('체크한 자막은 실제 편집본에서도 삭제됩니다. Ctrl+Z로 복원할 수 있습니다. 원본 영상은 유지됩니다.')
        actions.addWidget(self.move_button);actions.addWidget(self.delete_button);layout.addLayout(actions)
        self.context = QLabel()
        layout.addWidget(self.context)
        row = QHBoxLayout()
        self.tag_name = QLineEdit()
        self.tag_name.setPlaceholderText('장면 태그 이름')
        self.tag_name.setMaxLength(80)
        row.addWidget(self.tag_name, 1)
        self.start, self.end = QDoubleSpinBox(), QDoubleSpinBox()
        for label, control in [('시작', self.start), ('종료', self.end)]:
            control.setRange(0, 604800)
            control.setDecimals(3)
            control.setSuffix(' 초')
            row.addWidget(QLabel(label))
            row.addWidget(control)
        position = QPushButton('현재 구간')
        position.clicked.connect(self.use_position)
        row.addWidget(position)
        add = QPushButton('태그 저장')
        add.clicked.connect(self.add_tag)
        row.addWidget(add)
        layout.addLayout(row)
        foot = QHBoxLayout()
        self.message = QLabel('결과 클릭: 해당 편집본 시간으로 이동 · 태그는 편집본 시간에 고정됩니다.')
        self.message.setWordWrap(True)
        foot.addWidget(self.message, 1)
        layout.addLayout(foot)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(150)
        self.debounce.timeout.connect(self.refresh)
        self.query.textChanged.connect(lambda: self.debounce.start())
        self.kind.currentIndexChanged.connect(self.refresh)
        self.results.itemClicked.connect(self.navigate)
        self.results.itemChanged.connect(self.update_checks)
        self.edit_filter.currentIndexChanged.connect(self.refresh)
        self.folder_filter.currentIndexChanged.connect(self.refresh)
        for key,redo in (('Ctrl+Z',False),('Ctrl+Shift+Z',True)):
            shortcut=QShortcut(QKeySequence(key),self)
            shortcut.activated.connect(lambda r=redo:self.undo_project(r))
        save=QShortcut(QKeySequence('Ctrl+S'),self)
        save.activated.connect(lambda:self.studio.save_current())

    def undo_project(self,redo):
        from PySide6.QtWidgets import QApplication,QLineEdit,QAbstractSpinBox
        focus=QApplication.focusWidget()
        if isinstance(focus,(QLineEdit,QAbstractSpinBox)):
            if isinstance(focus,QLineEdit):focus.redo() if redo else focus.undo()
            return
        self.studio.change_project_history(redo);self.refresh()

    def checked_rows(self):
        return [self.results.topLevelItem(i).data(0,Qt.ItemDataRole.UserRole) for i in range(self.results.topLevelItemCount()) if self.results.topLevelItem(i).checkState(0)==Qt.CheckState.Checked]

    def update_checks(self,*_):
        count=len(self.checked_rows());total=self.results.topLevelItemCount()
        self.checked_count.setText(f'{count}개 선택')
        self.move_button.setEnabled(bool(count));self.delete_button.setEnabled(bool(count))
        with QSignalBlocker(self.select_all):self.select_all.setChecked(bool(total) and count==total)

    def check_all(self,checked):
        with QSignalBlocker(self.results):
            for i in range(self.results.topLevelItemCount()):self.results.topLevelItem(i).setCheckState(0,Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.update_checks()

    @project_action
    def new_folder(self):
        if self.studio.subtitle_job.busy:return
        name,ok=QInputDialog.getText(self,'새 분류 폴더','폴더 이름')
        if not ok:return
        try:name=validate_display_name(name)
        except ValueError as exc:self.message.setText(str(exc));return
        p=self.studio.project
        if len(p.search_folders)>=1000:self.message.setText('분류 폴더는 최대 1000개입니다.');return
        if name=='미분류' or any(f['name']==name for f in p.search_folders):self.message.setText('다른 이름의 분류 폴더를 지정하세요.');return
        p.search_folders.append(dict(id=uuid4().hex,name=name,parent=None))
        self.studio.mark_dirty();self.refresh()

    @project_action
    def move_checked(self):
        rows=self.checked_rows();p=self.studio.project
        if not rows or self.studio.subtitle_job.busy:return
        choices=['미분류']+[f['name'] for f in p.search_folders]
        name,ok=QInputDialog.getItem(self,'체크 항목 폴더 이동','분류 폴더',choices,0,False)
        if not ok:return
        target=next((f['id'] for f in p.search_folders if f['name']==name),None)
        for row in rows:
            if target:p.search_locations[row['key']]=target
            else:p.search_locations.pop(row['key'],None)
        self.studio.mark_dirty();self.refresh()
        self.message.setText('분류를 변경했습니다. 타임라인 배치는 유지됩니다. Ctrl+S로 저장하세요.')

    @project_action
    def delete_checked(self):
        rows=self.checked_rows();w=self.studio
        if not rows or not w.allow_project_switch():return
        current={r['key']:r for key in {r['sequence'] for r in rows} for r in search_edits(w.project,sequence_id=key)}
        if any(current.get(r['key'])!=r for r in rows):
            self.refresh();self.message.setText('작업 내용이 바뀌었습니다. 삭제할 항목을 다시 확인하세요.');return
        previous=w.active_edit_id
        grouped={}
        for row in rows:grouped.setdefault(row['sequence'],[]).append(row)
        keys=sorted(grouped,key=lambda k:bool(next(s for s in w.project.edit_sequences if s['id']==k).get('parent_id')))
        for key in keys:
            w.open_edit_sequence(key)
            if w.active_edit_id!=key:continue
            seq=w.active_sequence();chosen=grouped[key]
            cues=deepcopy(seq.get('timeline_captions',[]));tags=deepcopy(seq.get('scene_tags',[]))
            cue_indices={r['caption_index'] for r in chosen if 'caption_index' in r}
            tag_indices={r['tag_index'] for r in chosen if 'tag_index' in r}
            value=dict(seq,timeline_captions=[c for i,c in enumerate(cues) if i not in cue_indices])
            if tag_indices:value['scene_tags']=[t for i,t in enumerate(tags) if i not in tag_indices]
            w.commit_sequence(validate_sequence(value),'검색 선택 자막·태그 삭제')
            for row in chosen:w.project.search_locations.pop(row['key'],None)
        if previous:w.open_edit_sequence(previous)
        self.refresh();self.message.setText('체크한 자막·태그를 삭제했습니다. Ctrl+Z로 복원할 수 있습니다.')

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self.use_position()
        self.query.setFocus()

    def refresh(self, *_):
        checked={r['key'] for r in self.checked_rows()}
        project=self.studio.project
        all_rows=search_edits(project)
        with QSignalBlocker(self.edit_filter),QSignalBlocker(self.folder_filter):
            edit=self.edit_filter.currentData();folder=self.folder_filter.currentData()
            self.edit_filter.clear();self.edit_filter.addItem('전체 보기',None);self.edit_filter.addItem('현재 편집 중', '@current')
            present={r['sequence'] for r in all_rows}|{self.studio.active_edit_id}|{s['id'] for s in project.edit_sequences if s.get('timeline_captions')}
            for seq in project.edit_sequences:
                if seq['id'] in present:
                    parent=next((s['name'] for s in project.edit_sequences if s['id']==seq.get('parent_id')),None)
                    self.edit_filter.addItem((parent+' / ' if parent else '')+seq['name'],seq['id'])
            self.edit_filter.setCurrentIndex(max(0,self.edit_filter.findData(edit)))
            self.folder_filter.clear();self.folder_filter.addItem('전체 분류',None);self.folder_filter.addItem('미분류','@none')
            for f in project.search_folders:self.folder_filter.addItem(f['name'],f['id'])
            self.folder_filter.setCurrentIndex(max(0,self.folder_filter.findData(folder)))
        self.results.clear()
        edit=self.edit_filter.currentData();folder=self.folder_filter.currentData()
        if edit=='@current':edit=self.studio.active_edit_id or '@missing'
        self.rows = search_edits(self.studio.project, self.query.text(), ['all', 'captions', 'tags'][self.kind.currentIndex()],sequence_id=edit)
        self.rows=[r for r in self.rows if (edit is None or r['sequence']==edit) and (folder is None or r['folder']==(None if folder=='@none' else folder))]
        for result in self.rows:
            item = QTreeWidgetItem(['',result['name'], result['kind'], timestamp(result['start']), result['text']])
            item.setData(0, Qt.ItemDataRole.UserRole, result)
            item.setCheckState(0,Qt.CheckState.Checked if result['key'] in checked else Qt.CheckState.Unchecked)
            item.setToolTip(1,result['name'])
            item.setToolTip(3, timestamp(result['start'])+' → '+timestamp(result['end'])+' (편집본 기준)')
            self.results.addTopLevelItem(item)
        seq = self.studio.active_sequence()
        self.context.setText('태그 저장 대상: '+(seq['name'] if seq else '편집본을 먼저 열어 주세요'))
        self.update_checks()

    def navigate(self, item, *_):
        if _ and _[0]==0:return
        result = item.data(0, Qt.ItemDataRole.UserRole)
        w = self.studio
        if w.subtitle_job.busy or not w.resolve_subtitle_edit():
            return
        w.open_edit_sequence(result['sequence'])
        if w.active_edit_id != result['sequence']:
            return
        w.abort_timeline_scrub()
        if w.preview._playing:
            w.preview.toggle_play()
        position = round(result['start']*1000)
        if w.preview.ready:
            w.seek_transport(position)
        else:
            w.pending_seek = (position, False)
        w.timeline.set_position(position)
        self.start.setValue(result['start'])
        self.end.setValue(result['end'])
        self.context.setText('태그 저장 대상: '+result['name'])
        return True

    def use_position(self):
        w = self.studio
        seq = w.active_sequence()
        start = w.transport_position_value()/1000
        end = start+1
        if seq:
            clips = w.timeline.canvas.blocks
            selected = w.timeline.canvas.selected_clip
            block = next((b for b in clips if b[4] == selected), None)
            if block:
                start, end = block[1]/1000, block[2]/1000
            else:
                end = min(end, w.timeline.canvas.duration/1000)
        self.start.setValue(start)
        self.end.setValue(end)

    def add_tag(self):
        w = self.studio
        seq = w.active_sequence()
        if not seq or w.subtitle_job.busy:
            self.message.setText('편집본을 열고 작업이 끝난 후 태그를 저장하세요.')
            return
        try:
            extent = sequence_layout(seq, w.project.subtitles, {p:w.placement(p)['video'] for p in w.media.paths()})[2]/1000
            if self.end.value() > extent:
                raise ValueError('태그 종료는 편집본 길이 안으로 지정하세요.')
            tag = dict(name=self.tag_name.text(), start=self.start.value(), end=self.end.value())
            candidate = validate_sequence(dict(seq, scene_tags=seq.get('scene_tags', [])+[tag]))
            w.commit_sequence(candidate, '장면 태그 저장')
            self.refresh()
            self.message.setText('태그가 추가되었습니다. 프로젝트 파일에 보관하려면 Ctrl+S를 누르세요.')
        except ValueError as exc:
            self.message.setText(str(exc))

    def remove_tag(self):
        item = self.results.currentItem()
        if item is None:
            return
        result = item.data(0, Qt.ItemDataRole.UserRole)
        if 'tag_index' not in result:
            return
        if not self.navigate(item):
            return
        w = self.studio
        seq = w.active_sequence()
        if w.subtitle_job.busy or not seq or seq['id'] != result['sequence']:
            return
        tags = seq.get('scene_tags', [])
        index = result['tag_index']
        if index >= len(tags) or tags[index] != dict(name=result['text'], start=result['start'], end=result['end']):
            self.refresh()
            return
        w.commit_sequence(validate_sequence(dict(seq, scene_tags=tags[:index]+tags[index+1:])), '장면 태그 삭제')
        self.refresh()

