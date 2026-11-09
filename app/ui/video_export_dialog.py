"""Cancellable FFmpeg MP4 output. Existing files and sources are never overwritten."""
from copy import deepcopy
import os,shutil,tempfile,re
from pathlib import Path
from PySide6.QtCore import QProcess,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QCheckBox,QProgressBar,QFileDialog
from app.features.silence.video_export import probe_sources,render_filter,render_dimensions
from app.features.subtitles.export import export_srt
from app.features.subtitles.video_captions import write_video_captions


class VideoExportDialog(QDialog):
    def __init__(self,sequence,captions,parent=None):
        super().__init__(parent)
        self.sequence=deepcopy(sequence);self.captions=deepcopy(captions)
        self.process=None;self.work=None;self.partial=None;self.cancelled=False
        self.destination=None
        self.setWindowTitle('편집본 내보내기');self.resize(560,300)
        layout=QVBoxLayout(self)
        title=QLabel(sequence['name']);title.setWordWrap(True);layout.addWidget(title)
        self.info=QLabel('MP4 영상 · 파일의 회전·비율 반영 · 현재 편집본 시간 기준');self.info.setWordWrap(True);layout.addWidget(self.info)
        self.include=QCheckBox('자막 포함');self.include.setChecked(bool(captions));self.include.setEnabled(bool(captions));layout.addWidget(self.include)
        self.include.setToolTip('체크하면 영상 화면 안에 자막을 넣습니다. 해제하면 자막 없이 출력합니다.')
        self.audio_include=QCheckBox('오디오 포함');self.audio_include.setChecked(True);layout.addWidget(self.audio_include)
        self.audio_include.setToolTip('해제하면 오디오 트랙이 없는 무음 영상으로 저장합니다.')
        self.status=QLabel('새 파일로 출력합니다. 원본은 보존됩니다.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.progress=QProgressBar();self.progress.setRange(0,100);layout.addWidget(self.progress)
        buttons=QHBoxLayout();self.start=QPushButton('영상 저장(MP4)…');self.subtitles_save=QPushButton('자막만 저장(SRT)…')
        self.subtitles_save.setEnabled(bool(captions))
        self.start.clicked.connect(self.choose_output);self.subtitles_save.clicked.connect(self.choose_subtitles)
        buttons.addWidget(self.start);buttons.addWidget(self.subtitles_save);layout.addLayout(buttons)
        completed=QHBoxLayout();self.open_file=QPushButton('저장한 파일 열기');self.open_folder=QPushButton('저장 폴더 열기')
        for button in (self.open_file,self.open_folder):button.setEnabled(False);completed.addWidget(button)
        self.open_file.clicked.connect(lambda:self.open_result(False));self.open_folder.clicked.connect(lambda:self.open_result(True));layout.addLayout(completed)
        close=QPushButton('닫기');close.clicked.connect(self.close);layout.addWidget(close)

    def output_name(self):
        return re.sub(r'[<>:"/\\|?*]','_',self.sequence['name']).strip(' .') or '편집본'

    def choose_subtitles(self):
        path,_=QFileDialog.getSaveFileName(self,'자막만 저장',self.output_name()+'.srt','SRT 자막 (*.srt)')
        if path:self.save_subtitles(path)

    def save_subtitles(self,path):
        if self.process:return False
        target=Path(path).resolve()
        if target.suffix.lower()!='.srt':target=Path(str(target)+'.srt')
        if target.exists():self.status.setText('기존 파일을 보존합니다. 새 파일 이름을 지정하세요.');return False
        try:
            export_srt(self.captions,target)
            self.destination=target;self.progress.setValue(100)
            self.status.setText('자막 저장 완료 · '+str(target));self.enable_result();return True
        except (ValueError,OSError) as exc:self.status.setText(str(exc));return False

    def enable_result(self):
        available=self.destination is not None and self.destination.is_file()
        self.open_file.setEnabled(available);self.open_folder.setEnabled(available)

    def open_result(self,folder):
        if self.destination and self.destination.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.destination.parent if folder else self.destination)))

    def choose_output(self):
        name=self.output_name()
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
            graph,self.duration=render_filter(self.sequence,self.metadata,self.audio_include.isChecked())
            width,height,fps=render_dimensions(self.sequence,self.metadata)
            self.info.setText(f'{width} × {height} · {fps} fps · {self.duration:.3f}초 · 자막 '+('포함' if self.include.isChecked() else '제외')+' · 오디오 '+('포함' if self.audio_include.isChecked() else '제외'))
            self.work=tempfile.TemporaryDirectory(prefix='studio-render-')
            work=Path(self.work.name)
            if self.include.isChecked():
                srt=work/'captions.ass';write_video_captions(self.captions,srt,width,height)
                escaped=srt.as_posix().replace(':',r'\:').replace("'",r"\'")
                graph+=f";[video]ass=filename='{escaped}'[captioned]"
            script=work/'filters.txt';script.write_text(graph,encoding='utf-8')
            fd,partial=tempfile.mkstemp(prefix='.studio-render-',suffix='.mp4',dir=destination.parent);os.close(fd)
            self.partial=Path(partial);self.destination=destination
            args=['-hide_banner','-nostdin','-y']
            for source in self.paths:args+=['-i',source]
            args+=['-filter_complex_threads','1','-/filter_complex',str(script),'-map','[captioned]' if self.include.isChecked() else '[video]']
            if self.audio_include.isChecked():args+=['-map','[audio]','-c:a','aac','-b:a','192k']
            else:args+=['-an']
            args+=['-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-t',f'{self.duration:.3f}','-movflags','+faststart','-map_metadata','-1','-progress','pipe:1',str(self.partial)]
            self.stdout=b'';self.detail='';self.cancelled=False
            self.process=QProcess(self);self.process.setProgram('ffmpeg');self.process.setArguments(args)
            self.process.readyReadStandardOutput.connect(self.read_output);self.process.readyReadStandardError.connect(self.read_output)
            self.process.finished.connect(self.process_finished);self.process.errorOccurred.connect(self.process_error)
            self.process.started.connect(lambda:self.process.kill() if self.process and self.cancelled else None)
            self.start.setEnabled(False);self.include.setEnabled(False);self.audio_include.setEnabled(False);self.subtitles_save.setEnabled(False)
            self.open_file.setEnabled(False);self.open_folder.setEnabled(False)
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
                self.enable_result()
        except Exception as exc:self.status.setText('출력 실패: '+str(exc))
        self.cleanup()

    def cleanup(self):
        if self.process:self.process.deleteLater();self.process=None
        if self.partial:self.partial.unlink(missing_ok=True);self.partial=None
        if self.work:self.work.cleanup();self.work=None
        self.start.setEnabled(True);self.include.setEnabled(bool(self.captions));self.audio_include.setEnabled(True);self.subtitles_save.setEnabled(bool(self.captions))

    def cancel_work(self):
        if self.process:self.cancelled=True;self.process.kill()

    def done(self,result):
        if self.process:
            process=self.process;self.cancel_work();process.waitForFinished(5000)
        self.cleanup();super().done(result)
