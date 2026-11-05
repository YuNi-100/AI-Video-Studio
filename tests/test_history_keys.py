import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow

SOURCE=str((Path(__file__).parent/'fixtures'/'speech-test.mp4').resolve())
CTRL=Qt.KeyboardModifier.ControlModifier
REDO=CTRL|Qt.KeyboardModifier.ShiftModifier

class HistoryKeyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.w=MainWindow(); self.w.show(); self.w.activateWindow()
        self.w.media.restore([SOURCE],SOURCE)
        self.w.project.active_path=SOURCE
        self.w.project.subtitles[SOURCE]=[dict(start=1.,end=2.,text='original',reviewed=True)]
        self.w.show_source_subtitles(0,force=True)
        self.app.processEvents()
    def tearDown(self):
        self.w.subtitle_panel.editor.set_selection(-1); self.w.dirty=False; self.w.close()
        QTest.qWait(20)
    def key(self,redo=False):
        self.w.timeline.canvas.setFocus()
        QTest.keyClick(self.w.timeline.canvas,Qt.Key.Key_Z,REDO if redo else CTRL)
    def test_shortcuts_restore_caption_and_placements(self):
        w=self.w; w.subtitle_panel.editor.text.setPlainText('edited'); self.assertTrue(w.apply_subtitle_edit())
        w.move_timeline_block('video',0,1000)
        self.key(); self.assertEqual(w.placement(SOURCE)['video'],0)
        self.key(); self.assertEqual(w.project.subtitles[SOURCE][0]['text'],'original')
        self.key(True); self.assertEqual(w.project.subtitles[SOURCE][0]['text'],'edited')
        self.key(True); self.assertEqual(w.placement(SOURCE)['audio'],1.)
    def test_new_edit_invalidates_redo_and_project_reset_clears_history(self):
        w=self.w; w.move_timeline_block('video',0,1000); self.key()
        w.move_timeline_block('audio',0,2000); self.key(True)
        self.assertEqual(w.placement(SOURCE)['video'],2.)
        self.assertFalse(w.subtitle_redo.get(SOURCE))
        w.dirty=False; w.new_project()
        self.assertEqual(w.subtitle_history,{})
        self.assertEqual(w.subtitle_redo,{})
    def test_text_undo_redo_does_not_change_applied_project(self):
        w=self.w;w.create_edit_sequence(SOURCE,[(0,7)],7.188);w.select_subtitle(0)
        e=w.subtitle_panel.editor
        w.subtitle_panel.tabs.setCurrentIndex(1); e.text.setFocus()
        e.text.moveCursor(__import__('PySide6.QtGui',fromlist=['QTextCursor']).QTextCursor.MoveOperation.End)
        QTest.keyClicks(e.text,' plus')
        QTest.keyClick(e.text,Qt.Key.Key_Z,CTRL)
        self.assertEqual(e.text.toPlainText(),'original')
        QTest.keyClick(e.text,Qt.Key.Key_Z,REDO)
        self.assertEqual(e.text.toPlainText(),'original plus')
        self.assertEqual(w.project.subtitles[SOURCE][0]['text'],'original')
        name=w.project_name; name.setFocus(); name.selectAll(); QTest.keyClicks(name,'test')
        QTest.keyClick(name,Qt.Key.Key_Z,CTRL); self.assertNotEqual(name.text(),'test')
        QTest.keyClick(name,Qt.Key.Key_Z,REDO); self.assertEqual(name.text(),'test')
        name.setText(w.project.name)

if __name__=='__main__': unittest.main()
