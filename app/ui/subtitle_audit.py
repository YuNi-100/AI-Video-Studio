"""Read-only final review of the currently selected work, separate from ASR."""
import json,sys,tempfile
from copy import deepcopy
from pathlib import Path
from PySide6.QtCore import Qt,QProcess,QProcessEnvironment,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QDoubleSpinBox,QCheckBox,QPushButton,QTableWidget,QTableWidgetItem,QHeaderView)
from app.features.silence.sequence import sequence_layout,sequence_sources,sequence_clips
from app.features.subtitles.model import subtitle_time


class SubtitleAudit(QDialog):
    def __init__(self,studio):
        super().__init__(studio);self.studio=studio;self.process=None;self.work=None;self.findings=[];self.closing=False
        self.listen_timer=QTimer(self);self.listen_timer.setInterval(50);self.listen_timer.timeout.connect(self.stop_at_end)
        self.setWindowTitle('자막 재검토 · 수정본 최종 점검');self.resize(1000,580)
        layout=QVBoxLayout(self);self.target=QLabel();layout.addWidget(self.target)
        explanation=QLabel('수정한 문장과 검수 상태는 그대로 유지합니다. 아래 목록은 오류 확정이 아닌 확인할 위치입니다.');explanation.setWordWrap(True);layout.addWidget(explanation)
        bar=QHBoxLayout();self.scope=QComboBox();self.scope.addItems(['전체 구간','지정 구간']);bar.addWidget(self.scope)
        self.start,self.end=QDoubleSpinBox(),QDoubleSpinBox()
        self.scope.currentIndexChanged.connect(lambda *_:self.set_actions(self.process is None))
        for name,control in (('시작',self.start),('종료',self.end)):
            control.setRange(0,604800);control.setDecimals(3);control.setSuffix(' 초');bar.addWidget(QLabel(name));bar.addWidget(control)
        self.audio=QCheckBox('음성과 시간도 점검');self.audio.setChecked(True);bar.addWidget(self.audio)
        self.run=QPushButton('점검 시작');self.run.clicked.connect(self.begin);bar.addWidget(self.run);layout.addLayout(bar)
        self.table=QTableWidget(0,4);self.table.setHorizontalHeaderLabels(['작업본 시간','확인할 내용','현재 자막','검수 상태'])
        self.table.setStyleSheet('QTableWidget::item:selected { color: #ffffff; background: #36294f; }')
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0,180);self.table.setColumnWidth(3,90)
        self.table.setEditTriggers(self.table.EditTrigger.NoEditTriggers);self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection);layout.addWidget(self.table,1)
        foot=QHBoxLayout()
        self.listen=QPushButton('선택 구간 재생');self.listen.clicked.connect(self.play)
        self.edit=QPushButton('메인에서 확인·수정');self.edit.clicked.connect(self.edit_selected)
        self.recognize=QPushButton('구간 재인식…');self.recognize.clicked.connect(self.recognize_selected)
        for button in (self.listen,self.edit,self.recognize):foot.addWidget(button)
        close=QPushButton('닫기');close.clicked.connect(self.close);foot.addStretch();foot.addWidget(close);layout.addLayout(foot)
        self.status=QLabel('음성 점검은 말소리 구간과 자막 시간을 비교합니다. 단어의 정답 여부를 자동으로 판단하지 않습니다.');self.status.setWordWrap(True);layout.addWidget(self.status)

    def prepare(self):
        w=self.studio;seq=w.active_sequence();self.project_ref=w.project;self.sequence=deepcopy(seq)
        self.rows=deepcopy(sequence_layout(seq,w.project.subtitles,{p:w.placement(p)['video'] for p in w.media.paths()})[1])
        self.duration=max((c['at']+c['end']-c['start'] for c in sequence_clips(seq)),default=sequence_layout(seq)[2]/1000)
        self.terms=w.subtitle_panel.terms.text();self.language=w.subtitle_panel.language.currentData()
        self.target.setText('점검 대상: '+seq['name']+' · 문장 자동 변경 없음')
        self.start.setValue(0);self.end.setValue(self.duration);self.findings=[];self.report=None;self.table.setRowCount(0)
        self.status.setText('점검 시작을 누르세요. 사람이 고친 문장과 검수 완료 표시는 변경하지 않습니다.')
        self.set_actions(True)

    def unchanged(self):
        w=self.studio
        return w.project is self.project_ref and w.active_sequence()==self.sequence and self.terms==w.subtitle_panel.terms.text() and self.language==w.subtitle_panel.language.currentData() and self.rows==sequence_layout(w.active_sequence(),w.project.subtitles,{p:w.placement(p)['video'] for p in w.media.paths()})[1]

    def begin(self):
        w=self.studio
        if self.process or w.subtitle_job.busy:return
        if not w.resolve_subtitle_edit() or not self.unchanged():self.status.setText('작업본이 바뀌었습니다. 창을 닫고 다시 열어 점검하세요.');return
        start,end=(0,self.duration) if self.scope.currentIndex()==0 else (self.start.value(),self.end.value())
        if not 0<=start<end<=self.duration:self.status.setText('점검할 시간 범위를 확인하세요.');return
        self.findings=[];self.table.setRowCount(0);self.work=tempfile.TemporaryDirectory(prefix='studio-audit-')
        self.stamps={}
        try:
            if self.audio.isChecked():self.stamps={p:(Path(p).stat().st_size,Path(p).stat().st_mtime_ns) for p in sequence_sources(self.sequence)}
            path=Path(self.work.name)/'request.json'
            path.write_text(json.dumps(dict(sequence=self.sequence,rows=self.rows,duration=self.duration,terms=self.terms,language=self.language,audio=self.audio.isChecked(),start=start,end=end),ensure_ascii=False),encoding='utf-8')
            self.buffer=b'';self.detail='';self.report=None;self.closing=False
            process=QProcess(self);self.process=process
            env=QProcessEnvironment.systemEnvironment();env.insert('PYTHONIOENCODING','utf-8');env.insert('PYTHONUTF8','1');process.setProcessEnvironment(env)
            process.setWorkingDirectory(str(Path(__file__).resolve().parents[2]));process.setProgram(sys.executable)
            process.setArguments(['-u','-m','app.features.subtitles.audit_worker','--request',str(path)])
            process.readyReadStandardOutput.connect(self.read);process.readyReadStandardError.connect(self.read)
            process.finished.connect(self.process_finished);process.errorOccurred.connect(self.failed)
            process.started.connect(lambda:process.kill() if self.closing else None)
            self.run.setEnabled(False);self.set_actions(False);self.status.setText('최종 점검 중… 문장은 변경하지 않습니다.');process.start()
        except (ValueError,OSError) as exc:self.status.setText(str(exc));self.cleanup()

    def read(self):
        if not self.process:return
        self.buffer+=bytes(self.process.readAllStandardOutput())
        self.detail=(self.detail+bytes(self.process.readAllStandardError()).decode('utf-8',errors='replace'))[-3000:]
        while b'\n' in self.buffer:
            line,self.buffer=self.buffer.split(b'\n',1)
            try:
                message=json.loads(line.decode('utf-8'))
                if message['type']=='done':self.report=message
                elif message['type'] in ('status','error'):self.status.setText(message['text'])
            except (ValueError,KeyError):continue

    def set_actions(self,enabled):
        self.scope.setEnabled(enabled);self.audio.setEnabled(enabled)
        for control in (self.start,self.end):control.setEnabled(enabled and self.scope.currentIndex()==1)
        for button in (self.listen,self.edit):button.setEnabled(enabled and bool(self.findings))
        self.recognize.setEnabled(enabled)

    def process_finished(self,code,*_):
        self.read();process=self.process;self.process=None
        if process:process.deleteLater()
        if self.closing:self.cleanup();return
        try:
            if not self.unchanged() or any((Path(p).stat().st_size,Path(p).stat().st_mtime_ns)!=s for p,s in self.stamps.items()):
                self.status.setText('점검 중 작업본이 바뀌어 결과를 사용하지 않았습니다. 다시 열어 점검하세요.');return
            if code!=0 or self.report is None:
                self.status.setText('점검을 완료하지 못했습니다. '+self.status.text());return
            self.findings=self.report['findings'];self.table.setRowCount(len(self.findings))
            for i,row in enumerate(self.findings):
                values=[subtitle_time(row['start'])+' → '+subtitle_time(row['end']),' · '.join(row['reasons']),row['text'] or '(자막 없음)','—' if row['index'] is None else '검수 완료' if row['reviewed'] else '미검수']
                for col,text in enumerate(values):item=QTableWidgetItem(text);item.setToolTip(text);self.table.setItem(i,col,item)
                self.table.setRowHeight(i,64)
            self.status.setText(f"확인할 위치 {len(self.findings)}개 · 자막은 변경하지 않았습니다. "+(self.report['warning'] or ('음성 구간 비교 포함 · 말소리 추정은 직접 듣고 확인하세요.' if self.report['audio_checked'] else '자막 구조 점검만 수행했습니다.')))
            if self.findings:self.table.setCurrentCell(0,0)
        except (OSError,ValueError,KeyError) as exc:self.status.setText('점검 결과 확인 실패: '+str(exc))
        finally:self.cleanup()

    def failed(self,error):
        if error==QProcess.ProcessError.FailedToStart:
            process=self.process;self.process=None
            if process:process.deleteLater()
            self.status.setText('점검을 시작하지 못했습니다.');self.cleanup()

    def selected(self):
        if not self.unchanged():self.status.setText('작업본이 바뀌었습니다. 다시 열어 점검하세요.');return None
        row=self.table.currentRow()
        return self.findings[row] if 0<=row<len(self.findings) else None

    def locate(self,row):
        w=self.studio
        if w.subtitle_job.busy or not w.resolve_subtitle_edit() or not self.unchanged():return False
        if row['index'] is not None:w.select_subtitle(row['index'])
        w.seek_transport(round(row['start']*1000),resume=False);return True

    def play(self):
        row=self.selected()
        if row and row['start']>=self.duration:self.status.setText('영상 밖의 자막입니다. 메인에서 시간을 확인하세요.');return
        if row and self.locate(row):
            self.listen_end=round(row['end']*1000);self.studio.preview.toggle_play();self.listen_timer.start()

    def stop_at_end(self):
        if not self.unchanged():self.listen_timer.stop();return
        p=self.studio.preview
        if not p._playing:self.listen_timer.stop();return
        if p.timeline_position()>=self.listen_end:
            if p._playing:p.toggle_play()
            self.listen_timer.stop()

    def edit_selected(self):
        row=self.selected()
        if row and self.locate(row):
            self.hide();w=self.studio;w.subtitle_panel.tabs.setCurrentIndex(1);w.raise_();w.activateWindow()
            if row['index'] is not None:w.subtitle_panel.editor.text.setFocus()
            else:w.statusBar().showMessage('재생선 위치의 음성을 듣고 검수·수정에서 필요한 자막을 추가하세요.')

    def recognize_selected(self):
        if self.studio.subtitle_job.busy:self.status.setText('진행 중인 자막 작업이 끝난 뒤 실행하세요.');return
        if not self.unchanged():self.status.setText('작업본이 바뀌었습니다. 다시 열어 점검하세요.');return
        row=self.selected()
        if row and row['start']>=self.duration:self.status.setText('영상 밖의 자막은 메인에서 시간을 수정하세요.');return
        if row and not self.locate(row):return
        self.hide();self.studio.open_subtitle_recheck()
        d=getattr(self.studio,'recheck_dialog',None)
        if row and d and d.isVisible():d.scope.setCurrentIndex(1);d.start.setValue(max(0,row['start']));d.end.setValue(min(self.duration,row['end']))

    def cleanup(self):
        if self.work:self.work.cleanup();self.work=None
        self.run.setEnabled(True);self.set_actions(True)

    def done(self,result):
        self.closing=True
        self.listen_timer.stop()
        if self.process:
            process=self.process;process.kill();process.waitForFinished(5000)
            if self.process:self.process.deleteLater();self.process=None
        self.cleanup();super().done(result)
