"""Import local videos dropped anywhere in the main workspace."""
import json
from pathlib import Path
import weakref
from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtWidgets import QApplication, QWidget


class VideoDropImport(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = weakref.ref(window)
        window.setAcceptDrops(True)
        QApplication.instance().installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() not in (QEvent.Type.DragEnter,QEvent.Type.DragMove,QEvent.Type.Drop):
            return False
        window=self.window()
        if window is None or not isinstance(watched,QWidget) or watched.window() is not window:
            return False
        custom=event.mimeData().hasFormat('application/x-studio-organizer')
        if QApplication.activeModalWidget() is not None or not (event.mimeData().hasUrls() or custom):
            return False
        urls=event.mimeData().urls()
        paths=[url.toLocalFile() for url in urls if url.isLocalFile()
               and Path(url.toLocalFile()).suffix.lower() in ('.mp4','.mov')
               and Path(url.toLocalFile()).is_file()]
        if window.subtitle_job.busy or not window.media.isEnabled() or not (paths or custom):
            event.ignore()
            if event.type()==QEvent.Type.Drop:
                window.statusBar().showMessage('먼저 진행 중인 작업을 마치거나 로컬 MP4/MOV 영상을 놓아 주세요.')
            return True
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        if event.type()==QEvent.Type.Drop:
            if custom:
                try:
                    payload=json.loads(bytes(event.mimeData().data('application/x-studio-organizer')))
                    accepted=window.handle_organization_drop(payload,watched,event.position()) if isinstance(payload,list) and len(payload)<=10000 else False
                except (ValueError,TypeError):accepted=False
            else:accepted=window.handle_media_drop(paths,watched,event.position())
            if accepted and len(paths)!=len(urls):
                window.statusBar().showMessage('MP4/MOV 영상만 불러왔습니다. 다른 파일과 폴더는 제외했습니다.')
        return True
