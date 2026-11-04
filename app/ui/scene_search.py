"""Compact project-wide dialogue and scene index."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLineEdit,
    QComboBox, QPushButton, QTreeWidget, QTreeWidgetItem, QLabel, QDoubleSpinBox)
from app.features.scene_search import search_edits, timestamp
from app.features.silence.sequence import sequence_layout, validate_sequence


class SceneSearch(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.studio = window
        self.setWindowTitle('대사 검색 · 장면 태그')
        self.resize(760, 460)
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setPlaceholderText('현재 프로젝트의 편집본에서 대사·태그 검색')
        self.kind = QComboBox()
        self.kind.addItems(['대사와 태그', '대사', '태그'])
        bar.addWidget(self.query, 1)
        bar.addWidget(self.kind)
        layout.addLayout(bar)
        self.results = QTreeWidget()
        self.results.setHeaderLabels(['편집본', '종류', '편집본 시간', '대사 / 태그'])
        self.results.setRootIsDecorated(False)
        self.results.setColumnWidth(0, 140)
        self.results.setColumnWidth(1, 48)
        self.results.setColumnWidth(2, 112)
        layout.addWidget(self.results)
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
        foot.addWidget(self.message, 1)
        remove = QPushButton('선택 태그 삭제')
        remove.clicked.connect(self.remove_tag)
        foot.addWidget(remove)
        layout.addLayout(foot)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(150)
        self.debounce.timeout.connect(self.refresh)
        self.query.textChanged.connect(lambda: self.debounce.start())
        self.kind.currentIndexChanged.connect(self.refresh)
        self.results.itemClicked.connect(self.navigate)

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()
        self.use_position()
        self.query.setFocus()

    def refresh(self, *_):
        self.results.clear()
        self.rows = search_edits(self.studio.project, self.query.text(), ['all', 'captions', 'tags'][self.kind.currentIndex()])
        for result in self.rows:
            item = QTreeWidgetItem([result['name'], result['kind'], timestamp(result['start']), result['text']])
            item.setData(0, Qt.ItemDataRole.UserRole, result)
            item.setToolTip(2, timestamp(result['start'])+' → '+timestamp(result['end'])+' (편집본 기준)')
            self.results.addTopLevelItem(item)
        seq = self.studio.active_sequence()
        self.context.setText('태그 저장 대상: '+(seq['name'] if seq else '편집본을 먼저 열어 주세요'))

    def navigate(self, item, *_):
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
            self.message.setText('태그 저장 완료 · Ctrl+S로 프로젝트 파일에 저장하세요.')
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

