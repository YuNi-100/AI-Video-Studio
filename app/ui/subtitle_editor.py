from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QPlainTextEdit, QDoubleSpinBox, QPushButton, QCheckBox, QScrollArea, QComboBox)
from app.ui.components import label
from app.features.subtitles.model import subtitle_time
from app.features.subtitles.editing import review_reasons


class SubtitleEditor(QWidget):
    selected = Signal(int)
    apply_requested = Signal()
    add_requested = Signal()
    remove_requested = Signal()
    undo_requested = Signal()
    export_requested = Signal()
    overlay_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setObjectName("subtitleReview")
        self.setStyleSheet("QWidget#subtitleReview QPushButton { padding: 7px 5px; }")
        self.segments = []
        self.selected_index = -1
        self.original = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        self.scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        root.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.run_info = label("생성 정보 없음 · 이전 프로젝트도 검수할 수 있습니다.", "muted")
        layout.addWidget(self.run_info)
        self.summary = label("자막을 생성하거나 추가하세요.", "muted")
        layout.addWidget(self.summary)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["시작", "문장", "검수"])
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(100)
        self.table.setMaximumHeight(150)
        self.table.currentCellChanged.connect(self.row_changed)
        layout.addWidget(self.table, 1)
        times = QHBoxLayout()
        self.start = QDoubleSpinBox()
        self.end = QDoubleSpinBox()
        for name, control in (("시작 초", self.start), ("종료 초", self.end)):
            column = QVBoxLayout()
            column.addWidget(label(name, "muted"))
            control.setRange(0, 604800)
            control.setDecimals(3)
            control.setSingleStep(.1)
            control.setAccessibleName(name)
            column.addWidget(control)
            times.addLayout(column)
        layout.addLayout(times)
        self.text = QPlainTextEdit()
        self.text.setObjectName("captionEditor")
        self.text.setMinimumHeight(60)
        self.text.setMaximumHeight(90)
        self.text.setPlaceholderText("문장을 선택해 수정하세요.")
        self.text.setAccessibleName("선택 자막 문장 편집")
        layout.addWidget(self.text)
        self.apply_button = QPushButton("수정 적용")
        self.apply_button.setObjectName("primary")
        self.apply_button.clicked.connect(self.apply_requested.emit)
        self.apply_button.setToolTip("수정 내용을 적용하고 이 자막을 검수 완료로 표시합니다.")
        apply_row = QHBoxLayout()
        apply_row.addWidget(self.apply_button)
        self.export_button = QPushButton("SRT 출력")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self.export_requested.emit)
        apply_row.addWidget(self.export_button)
        layout.addLayout(apply_row)
        controls = QHBoxLayout()
        for text, signal in (("추가", self.add_requested), ("제거", self.remove_requested), ("실행 취소", self.undo_requested)):
            button = QPushButton(text)
            button.clicked.connect(signal.emit)
            if signal == self.undo_requested:
                button.setToolTip("Ctrl+Z · 현재 영상의 적용한 자막 수정과 타임라인 이동을 취소합니다. Ctrl+Shift+Z로 다시 실행합니다.")
            controls.addWidget(button)
        layout.addLayout(controls)
        self.export_basis = QComboBox()
        self.export_basis.addItem("SRT: 타임라인 시간 기준", "timeline")
        self.export_basis.addItem("SRT: 원본 영상 시간 기준", "source")
        self.export_basis.setMinimumContentsLength(10)
        self.export_basis.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.export_basis.setToolTip("타임라인: 배치한 위치대로 출력. 전체 보기에서는 여러 영상의 자막을 이어 출력합니다.\n원본 영상: 선택 영상의 배치 시작 시간을 빼고 원본에 맞춰 출력합니다.")
        layout.addWidget(self.export_basis)
        self.overlay = QCheckBox("영상 위에 자막 표시")
        self.overlay.setChecked(True)
        self.overlay.toggled.connect(self.overlay_changed.emit)
        layout.addWidget(self.overlay)
        self.summary.setToolTip("의심 표시는 오류 확정이 아닙니다. 원본을 재생해 확인하고 수정 적용을 누르세요.")
        self.set_selection(-1)

    @property
    def pending(self):
        return self.original is not None and self.values() != self.original

    def values(self):
        return (self.start.value(), self.end.value(), self.text.toPlainText())

    def row_changed(self, row, column, old_row, old_column):
        # MainWindow resolves the previous editor buffer before loading another row.
        self.selected.emit(row)

    def set_selection(self, row):
        self.selected_index = row if 0 <= row < len(self.segments) else -1
        with QSignalBlocker(self.table):
            if self.selected_index >= 0:
                self.table.selectRow(self.selected_index)
            else:
                self.table.clearSelection()
                self.table.setCurrentCell(-1, -1)
        enabled = self.selected_index >= 0
        for widget in (self.start, self.end, self.text, self.apply_button):
            widget.setEnabled(enabled)
        segment = self.segments[row] if enabled else {"start": 0, "end": 0, "text": ""}
        self.start.setValue(segment["start"])
        self.end.setValue(segment["end"])
        self.text.setPlainText(segment["text"])
        self.original = self.values() if enabled else None

    def show_segments(self, segments, language="ko", select=-1):
        self.segments = segments
        flags = review_reasons(segments, language)
        with QSignalBlocker(self.table):
            self.table.setRowCount(len(segments))
            for i, (segment, reasons) in enumerate(zip(segments, flags)):
                status = "✓" if segment.get("reviewed") else ("확인" if reasons else "미검수")
                for col, value in enumerate((subtitle_time(segment["start"])[3:], segment["text"].replace("\n", " "), status)):
                    item = QTableWidgetItem(value)
                    item.setToolTip(" · ".join(reasons) if col == 2 else value)
                    self.table.setItem(i, col, item)
        count = sum(bool(reasons) and not segment.get("reviewed") for segment, reasons in zip(segments, flags))
        self.summary.setText(f"자막 {len(segments)}개 · 검수 권장 {count}개")
        self.export_button.setEnabled(bool(segments))
        self.set_selection(select)
