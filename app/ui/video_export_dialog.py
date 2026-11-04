"""Cancellable FFmpeg MP4 output. Existing files and sources are never overwritten."""
from copy import deepcopy
import os,shutil,tempfile,re
from pathlib import Path
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QCheckBox,QProgressBar,QFileDialog
from app.features.silence.video_export import probe_sources,render_filter
from app.features.subtitles.export import export_srt


class VideoExportDialog(QDialog):
    def __init__(self,sequence,captions,parent=None):
        super().__init__(parent)
        self.sequence=deepcopy(sequence);self.captions=deepcopy(captions)
        self.process=None;self.work=None;self.partial=None;self.cancelled=False
        self.setWindowTitle('편집본 영상 출력');self.resize(480,220)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel(sequence['name']+' · MP4 / H.264 + AAC'))
        self.include=QCheckBox('자막 포함');self.include.setChecked(bool(captions));self.include.setEnabled(bool(captions));layout.addWidget(self.include)
        self.status=QLabel('새 파일로 출력합니다. 원본은 보존됩니다.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.progress=QProgressBar();self.progress.setRange(0,100);layout.addWidget(self.progress)
        buttons=QHBoxLayout();self.start=QPushButton('MP4로 저장…');self.cancel=QPushButton('작업 취소');self.cancel.setEnabled(False)
        self.start.clicked.connect(self.choose_output);self.cancel.clicked.connect(self.cancel_work)
        buttons.addWidget(self.start);buttons.addWidget(self.cancel);layout.addLayout(buttons)
        close=QPushButton('닫기');close.clicked.connect(self.close);layout.addWidget(close)

    def choose_output(self):
        name=re.sub(r'[<>:"/\\|?*]','_',self.sequence['name']).strip(' .') or '편집본'
        path,_=QFileDialog.getSaveFileName(self,'편집본 영상 출력',name+'.mp4','MP4 영상 (*.mp4)')
        if path:self.start_output(path)

    def start_output(self,path):
        if self.process:return False
        if not shutil.which('ffmpeg'):
            self.status.setText('FFmpeg를 찾을 수 없습니다.');return False
        destination=Path(path).resolve()
        if destination.suffix.lower()!='.mp4':destination=Path(str(destination)+'.mp4')
        if destination.exists():
            self.status.setText('기존 파일을 보존합니다. 새 파일 이름을 지정하세요.');return False
        try:
            self.paths,self.metadata=probe_sources(self.sequence)
            graph,self.duration=render_filter(self.sequence,self.metadata)
            self.work=tempfile.TemporaryDirectory(prefix='studio-render-')
            work=Path(self.work.name)
            if self.include.isChecked():
                srt=work/'captions.srt';export_srt(self.captions,srt)
                escaped=srt.as_posix().replace(':',r'\:').replace("'",r"\'")
                graph+=f";[video]subtitles=filename='{escaped}':force_style='FontName=Malgun Gothic,FontSize=22,Outline=1'[captioned]"
            script=work/'filters.txt';script.write_text(graph,encoding='utf-8')
            fd,partial=tempfile.mkstemp(prefix='.studio-render-',suffix='.mp4',dir=destination.parent);os.close(fd)
            self.partial=Path(partial);self.destination=destination
            args=['-hide_banner','-nostdin','-y']
            for source in self.paths:args+=['-i',source]
            args+=['-filter_complex_threads','1','-/filter_complex',str(script),'-map','[captioned]' if self.include.isChecked() else '[video]','-map','[audio]','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-t',f'{self.duration:.3f}','-movflags','+faststart','-map_metadata','-1','-progress','pipe:1',str(self.partial)]
            self.stdout=b'';self.detail='';self.cancelled=False
            self.process=QProcess(self);self.process.setProgram('ffmpeg');self.process.setArguments(args)
            self.process.readyReadStandardOutput.connect(self.read_output);self.process.readyReadStandardError.connect(self.read_output)
            self.process.finished.connect(self.process_finished);self.process.errorOccurred.connect(self.process_error)
            self.process.started.connect(lambda:self.process.kill() if self.process and self.cancelled else None)
            self.start.setEnabled(False);self.include.setEnabled(False);self.cancel.setEnabled(True)
            self.status.setText('영상 출력 중…');self.progress.setValue(0);self.process.start();return True
        except Exception as exc:
            self.status.setText('출력 준비 실패: '+str(exc));self.cleanup();return False

    def read_output(self):
        if not self.process:return
        self.stdout+=bytes(self.process.readAllStandardOutput())
        self.detail=(self.detail+bytes(self.process.readAllStandardError()).decode('utf-8',errors='replace'))[-12000:]
        while b'\n' in self.stdout:
            line,self.stdout=self.stdout.split(b'\n',1)
            if line.startswith(b'out_time_us='):
                try:self.progress.setValue(min(99,round(float(line.split(b'=')[1])/1000000/self.duration*100)))
                except ValueError:pass

    def process_error(self,error):
        if error==QProcess.ProcessError.FailedToStart:
            self.status.setText('FFmpeg를 실행하지 못했습니다.');self.cleanup()

    def process_finished(self,code,status):
        self.read_output()
        old,self.process=self.process,None
        if old:old.deleteLater()
        try:
            if self.cancelled:self.status.setText('출력을 취소했습니다.')
            elif code!=0:raise ValueError(self.detail[-1600:])
            else:
                for path,metadata in self.metadata.items():
                    stat=Path(path).stat()
                    if (stat.st_size,stat.st_mtime_ns)!=metadata['stamp']:raise ValueError('출력 중 원본이 변경되었습니다.')
                self.partial.rename(self.destination);self.partial=None
                self.progress.setValue(100);self.status.setText('출력 완료 · '+str(self.destination))
        except Exception as exc:self.status.setText('출력 실패: '+str(exc))
        self.cleanup()

    def cleanup(self):
        if self.process:self.process.deleteLater();self.process=None
        if self.partial:self.partial.unlink(missing_ok=True);self.partial=None
        if self.work:self.work.cleanup();self.work=None
        self.start.setEnabled(True);self.include.setEnabled(bool(self.captions));self.cancel.setEnabled(False)

    def cancel_work(self):
        if self.process:self.cancelled=True;self.process.kill()

    def done(self,result):
        if self.process:
            self.cancel_work();self.process.waitForFinished(5000)
        self.cleanup();super().done(result)
