import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from PySide6.QtCore import QMimeData, QUrl, QPoint, QPointF, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow


class DropImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.a=Path(self.temp.name)/'한글 영상.MP4'
        self.b=Path(self.temp.name)/'two.mov'
        self.a.write_bytes(b'example')
        self.b.write_bytes(b'example')
        self.w=MainWindow()
        self.w.media.selected.disconnect()
        self.w.show()
        self.app.processEvents()
    def tearDown(self):
        self.w.dirty=False
        self.w.close()
        self.temp.cleanup()
    def drop(self,urls,target=None):
        target=target or self.w
        mime=QMimeData()
        mime.setUrls(urls)
        enter=QDragEnterEvent(QPoint(10,10),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(target,enter)
        if enter.isAccepted():
            drop=QDropEvent(QPointF(10,10),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
            QApplication.sendEvent(target,drop)
        return enter.isAccepted()
    def test_multiple_files_and_duplicate_preserve_sources(self):
        urls=[QUrl.fromLocalFile(str(p)) for p in (self.a,self.b,self.a)]
        self.assertTrue(self.drop(urls))
        self.assertEqual(self.w.media.paths(),[str(self.a.resolve()),str(self.b.resolve())])
        self.assertEqual(self.a.read_bytes(),b'example')
    def test_drop_on_subtitle_input_imports_without_inserting_path(self):
        text=self.w.subtitle_panel.editor.text
        before=text.toPlainText()
        self.assertTrue(self.drop([QUrl.fromLocalFile(str(self.a))],text.viewport()))
        self.assertEqual(len(self.w.media.paths()),1)
        self.assertEqual(text.toPlainText(),before)
    def test_mixed_files_skip_unsupported_and_remote(self):
        urls=[QUrl.fromLocalFile(str(self.a)),QUrl.fromLocalFile(str(Path(self.temp.name))),QUrl('https://example.com/a.mp4')]
        self.assertTrue(self.drop(urls))
        self.assertEqual(self.w.media.paths(),[str(self.a.resolve())])
        self.assertFalse(self.drop(urls[1:]))
    def test_pending_edit_cancellation_preserves_library(self):
        self.w.media.before_change=lambda:False
        self.assertTrue(self.drop([QUrl.fromLocalFile(str(self.a))]))
        self.assertEqual(self.w.media.paths(),[])
    def test_busy_job_rejects_drop(self):
        original=self.w.subtitle_job
        self.w.subtitle_job=SimpleNamespace(busy=True)
        try:
            self.assertFalse(self.drop([QUrl.fromLocalFile(str(self.a))]))
            self.assertEqual(self.w.media.paths(),[])
        finally:
            self.w.subtitle_job=original

if __name__=='__main__':
    unittest.main()
