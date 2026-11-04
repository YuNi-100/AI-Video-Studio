"""Review-first silence cut dialog. FFmpeg runs outside the UI process."""
import json
from pathlib import Path
import shutil
from PySide6.QtCore import Qt, QProcess
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QDoubleSpinBox, QFormLayout, QWidget, QTableWidget, QTableWidgetItem,
    QFileDialog, QMessageBox, QHeaderView)
from app.features.silence.model import candidates_from_log, retained_ranges
from app.ui.video_player import VideoPlayer


def compact_time(seconds):
    ticks = max(0, round(seconds * 100))
    minutes, remainder = divmod(ticks, 6000)
    seconds, fraction = divmod(remainder, 100)
    hours, minutes = divmod(minutes, 60)
    prefix = f'{hours:02d}:' if hours else ''
    return f'{prefix}{minutes:02d}:{seconds:02d}.{fraction:02d}'


class SilenceDialog(QDialog):
    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.source = Path(source).resolve()
        self.stamp = self.source.stat()
        self.duration = 0
        self.candidates = []
        self.process = None
        self.setWindowTitle('AI 무음 컷 · 선택한 후보만 제외')
        self.resize(1050, 740)
        layout = QVBoxLayout(self)
        note = QLabel('조용해도 중요한 장면일 수 있습니다. 확인한 구간만 체크하세요. 원본은 보존합니다.')
        note.setWordWrap(True)
        layout.addWidget(note)
        body = QHBoxLayout()
        self.preview = VideoPlayer()
        body.addWidget(self.preview, 3)
        side = QVBoxLayout()
        self.advanced = QCheckBox('상세 설정')
        side.addWidget(self.advanced)
        self.settings = QWidget()
        form = QFormLayout(self.settings)
        self.threshold = QDoubleSpinBox()
        self.threshold.setRange(-80, -10)
        self.threshold.setValue(-35)
        self.threshold.setSuffix(' dB')
        self.minimum = QDoubleSpinBox()
        self.minimum.setRange(.5, 30)
        self.minimum.setValue(1)
        self.minimum.setSuffix(' 초')
        self.padding = QDoubleSpinBox()
        self.padding.setRange(0, 1)
        self.padding.setSingleStep(.05)
        self.padding.setValue(.15)
        self.padding.setSuffix(' 초')
        form.addRow('무음 기준', self.threshold)
        form.addRow('최소 무음 길이', self.minimum)
        form.addRow('양 끝 보존', self.padding)
        self.settings.hide()
        self.advanced.toggled.connect(self.settings.setVisible)
        side.addWidget(self.settings)
        self.detect = QPushButton('무음 후보 찾기')
        self.detect.clicked.connect(self.start_probe)
        side.addWidget(self.detect)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(['제외', '원본 구간', '길이'])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 45)
        self.table.setColumnWidth(2, 65)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.itemChanged.connect(self.update_summary)
        self.table.cellClicked.connect(self.seek_candidate)
        side.addWidget(self.table, 1)
        review = QPushButton('선택한 행 재생')
        review.clicked.connect(self.review)
        side.addWidget(review)
        self.summary = QLabel('제외할 후보를 체크하세요.')
        self.summary.setWordWrap(True)
        side.addWidget(self.summary)
        body.addLayout(side, 2)
        layout.addLayout(body, 1)
        self.status = QLabel('현재 영상의 원본 시간 기준 · 적용하면 새 편집 편집본가 생성됩니다.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.applied_ranges = None
        self.export = QPushButton('적용 · 새 편집본 만들기')
        self.export.setEnabled(False)
        self.export.clicked.connect(self.apply_sequence)
        self.cancel = QPushButton('작업 취소')
        self.cancel.setEnabled(False)
        self.cancel.clicked.connect(self.cancel_work)
        close = QPushButton('닫기')
        close.clicked.connect(self.close)
        for button in (self.export, self.cancel, close):
            actions.addWidget(button)
        layout.addLayout(actions)
        self.preview.open_video(str(self.source))
        self.review_end = None
        self.preview.timelinePositionChanged.connect(self.stop_review)

    def pause_preview(self):
        if self.preview._playing:
            self.preview.toggle_play()

    def unchanged(self):
        try:
            current = self.source.stat()
            return (current.st_size, current.st_mtime_ns) == (self.stamp.st_size, self.stamp.st_mtime_ns)
        except OSError:
            return False

    def run_process(self, program, args, stage):
        self.stage = stage
        self.cancelled = False
        self.stdout = bytearray()
        self.stderr = bytearray()
        self.process = QProcess(self)
        self.process.setProgram(program)
        self.process.setArguments(args)
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_output)
        self.process.finished.connect(self.process_finished)
        self.process.errorOccurred.connect(self.process_error)
        self.detect.setEnabled(False)
        self.export.setEnabled(False)
        self.settings.setEnabled(False)
        self.table.setEnabled(False)
        self.cancel.setEnabled(True)
        self.process.started.connect(lambda: self.process.kill() if self.process and self.cancelled else None)
        self.process.start()

    def read_output(self):
        if self.process:
            self.stdout.extend(bytes(self.process.readAllStandardOutput()))
            self.stderr.extend(bytes(self.process.readAllStandardError()))
            # Silence markers are needed for analysis; encoder logs are bounded.
            if self.stage != 'detect':
                self.stderr = self.stderr[-12000:]

    def process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self.status.setText('작업을 시작하지 못했습니다. FFmpeg 설치를 확인하세요.')
            self.cleanup()

    def start_probe(self):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            self.status.setText('FFmpeg와 FFprobe가 필요합니다. 설치 후 다시 실행하세요.')
            return
        if not self.unchanged():
            self.status.setText('원본이 변경되었습니다. 창을 닫고 영상을 다시 여세요.')
            return
        if self.candidates and QMessageBox.question(self, '후보 다시 찾기', '현재 체크를 초기화하고 다시 분석할까요?') != QMessageBox.StandardButton.Yes:
            return
        self.pause_preview()
        self.status.setText('영상 정보를 확인하는 중…')
        self.run_process('ffprobe', ['-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(self.source)], 'probe')

    def selected_cuts(self):
        return [pair for i, pair in enumerate(self.candidates)
                if self.table.item(i, 0).checkState() == Qt.CheckState.Checked]

    def update_summary(self, *_):
        cuts = self.selected_cuts()
        removed = sum(b-a for a,b in cuts)
        self.summary.setText(f'{len(cuts)}개 선택 · {removed:.2f}초 제외 · 편집본 약 {compact_time(max(0,self.duration-removed))}')
        self.export.setEnabled(bool(cuts) and self.process is None)

    def seek_candidate(self, row, column):
        if column == 1 and 0 <= row < len(self.candidates):
            self.review_end = None
            self.pause_preview()
            self.preview.seek_timeline(round(self.candidates[row][0] * 1000))

    def review(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.candidates):
            start, end = self.candidates[row]
            self.review_end = min(self.duration, end + .5) * 1000
            self.preview.seek_timeline(round(max(0,start-.5)*1000))
            if not self.preview._playing:
                self.preview.toggle_play()

    def stop_review(self, position):
        if self.review_end is not None and position >= self.review_end:
            self.review_end = None
            self.pause_preview()

    def apply_sequence(self):
        if self.process or not self.selected_cuts() or not self.unchanged():
            self.status.setText('선택 후보와 원본 상태를 확인하세요.')
            return
        try:
            self.applied_ranges = retained_ranges(self.duration,self.selected_cuts())
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self.accept()

    def process_finished(self, code, exit_status):
        self.read_output()
        stage = self.stage
        old, self.process = self.process, None
        old.deleteLater()
        try:
            if self.cancelled:
                self.status.setText('작업을 취소했습니다. 원본과 기존 파일은 보존됩니다.')
            elif code != 0 or not self.unchanged():
                raise ValueError('작업 실패 또는 원본 변경: '+self.stderr.decode('utf-8', errors='replace')[-900:])
            elif stage == 'probe':
                info = json.loads(self.stdout)
                if not any(s['codec_type']=='audio' for s in info['streams']):
                    raise ValueError('음성 트랙이 없어 무음을 분석할 수 없습니다.')
                if not any(s['codec_type']=='video' for s in info['streams']):
                    raise ValueError('영상 트랙이 없습니다.')
                self.duration = float(info['format']['duration'])
                retained_ranges(self.duration, [])
                self.status.setText('무음 후보 분석 중…')
                self.run_process('ffmpeg', ['-hide_banner', '-nostdin', '-i', str(self.source), '-map', '0:a:0',
                    '-af', f'silencedetect=noise={self.threshold.value()}dB:d={self.minimum.value()}', '-vn', '-sn', '-f', 'null', '-'], 'detect')
                return
            elif stage == 'detect':
                self.candidates = []
                self.table.setRowCount(0)
                self.candidates = candidates_from_log(self.stderr.decode('utf-8', errors='replace'), self.duration, self.padding.value())
                self.table.blockSignals(True)
                self.table.setRowCount(len(self.candidates))
                for i, (start,end) in enumerate(self.candidates):
                    item = QTableWidgetItem()
                    item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                    item.setCheckState(Qt.CheckState.Unchecked)
                    self.table.setItem(i, 0, item)
                    self.table.setItem(i, 1, QTableWidgetItem(f'{compact_time(start)} → {compact_time(end)}'))
                    self.table.setItem(i, 2, QTableWidgetItem(f'{end-start:.2f}초'))
                self.table.blockSignals(False)
                self.status.setText(f'무음 후보 {len(self.candidates)}개 · 체크한 구간만 새 편집본에서 제외됩니다. 후보는 이 창을 닫으면 초기화됩니다.')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.status.setText(str(exc))
        self.cleanup()

    def cleanup(self):
        if self.process:
            self.process.deleteLater()
            self.process = None
        self.detect.setEnabled(True)
        self.settings.setEnabled(True)
        self.table.setEnabled(True)
        self.cancel.setEnabled(False)
        self.update_summary()

    def cancel_work(self):
        if self.process:
            self.cancelled = True
            self.process.kill()

    def done(self, result):
        if self.process:
            self.cancel_work()
            self.process.waitForFinished(5000)
        self.preview.shutdown()
        super().done(result)


