import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import hashlib,time,unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPointF,QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow
from app.features.silence.sequence import sequence_clips
A=str((Path(__file__).parent/'fixtures/speech-test.mp4').resolve())


class RawTimelineEditingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.w=MainWindow();self.w.show();self.w.activateWindow();self.w.preview.audio.setMuted(True)
        self.before=hashlib.sha256(Path(A).read_bytes()).digest()
        self.w.media.add_files([A])
        end=time.monotonic()+8
        while not self.w.preview.ready and time.monotonic()<end:QTest.qWait(20)
        self.assertTrue(self.w.preview.ready)
    def tearDown(self):
        self.assertEqual(hashlib.sha256(Path(A).read_bytes()).digest(),self.before)
        self.w.project_name.setText(self.w.project.name)
        self.w.dirty=False
        for d in self.w.documents:d['dirty']=False
        self.w.close();QTest.qWait(20)
    def x(self,ms):
        c=self.w.timeline.canvas
        return 95+(ms-c.offset)/c.span*(c.width()-107)
    def drag(self,start,end,release_shift=False):
        c=self.w.timeline.canvas
        for kind,pos,button,buttons,mods in ((QEvent.Type.MouseButtonPress,start,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier),
          (QEvent.Type.MouseMove,end,Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.ShiftModifier),
          (QEvent.Type.MouseButtonRelease,end,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier if release_shift else Qt.KeyboardModifier.ShiftModifier)):
            QApplication.sendEvent(c,QMouseEvent(kind,QPointF(*pos),button,buttons,mods))
    def test_ctrl_k_from_original_creates_edit_and_splits_at_playhead(self):
        w=self.w;c=w.timeline.canvas
        self.assertIsNone(w.active_sequence())
        QTest.mouseClick(c,Qt.MouseButton.LeftButton,pos=QPointF(self.x(500),47).toPoint())
        QTest.keyClick(c,Qt.Key.Key_K,Qt.KeyboardModifier.ControlModifier)
        self.assertIsNotNone(w.active_sequence())
        self.assertEqual(len(sequence_clips(w.active_sequence())),4)
        self.assertAlmostEqual(sequence_clips(w.active_sequence())[0]['end'],.5,delta=.03)
        self.assertTrue(c.sequence_view)
    def test_shift_from_original_promotes_and_holds_modifier_until_release(self):
        w=self.w
        self.drag((self.x(500),47),(self.x(1000),47),True)
        self.assertIsNotNone(w.active_sequence())
        clips=sequence_clips(w.active_sequence())
        self.assertAlmostEqual(clips[0]['at'],.5,delta=.03)
        self.assertAlmostEqual(clips[1]['at'],.5,delta=.03)
    def test_shift_after_split_moves_all_following_and_ctrl_k_uses_playhead(self):
        w=self.w;w.preview.seek_timeline(1000)
        w.timeline.canvas.setFocus();QTest.keyClick(w.timeline.canvas,Qt.Key.Key_K,Qt.KeyboardModifier.ControlModifier)
        self.drag((self.x(500),47),(self.x(1000),47),True)
        clips=sequence_clips(w.active_sequence())
        self.assertAlmostEqual(clips[0]['at'],.5,delta=.03)
        self.assertAlmostEqual(next(c['at'] for c in clips if c['track']=='video' and c['start']>0),1.5,delta=.03)
        w.preview.seek_timeline(2000)
        QTest.keyClick(w.timeline.canvas,Qt.Key.Key_K,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(sequence_clips(w.active_sequence())),6)
    def test_header_and_explicit_edit_button(self):
        w=self.w
        w.project_name.setText('무음편집확인')
        self.assertEqual(w.project_name.height(),30)
        self.assertEqual(w.project_picker.height(),30)
        self.assertEqual(w.project_name.text()[0],'무')
        w.timeline.begin_edit.click()
        self.assertIsNotNone(w.active_sequence())
        self.assertTrue(w.timeline.begin_edit.isHidden())

    def box(self,start,end):
        c=self.w.timeline.canvas
        for kind,pos,button,buttons in ((QEvent.Type.MouseButtonPress,start,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton),
            (QEvent.Type.MouseMove,end,Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton),
            (QEvent.Type.MouseButtonRelease,end,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)):
            QApplication.sendEvent(c,QMouseEvent(kind,QPointF(*pos),button,buttons,Qt.KeyboardModifier.NoModifier))
    def test_box_selects_multiple_linked_cuts_delete_and_undo(self):
        w=self.w;w.create_edit_sequence(A,[(0,1),(2,3),(4,5)],7.188)
        self.box((self.x(1900),175),(self.x(100),35))
        self.assertEqual(len(w.timeline.canvas.selected_keys),4)
        QTest.keyClick(w.timeline.canvas,Qt.Key.Key_Delete)
        self.assertEqual(len(sequence_clips(w.active_sequence())),2)
        self.assertEqual(w.preview.timeline_duration(),1000)
        w.undo_subtitle()
        self.assertEqual(len(sequence_clips(w.active_sequence())),6)
        self.assertEqual(len(w.timeline.canvas.selected_keys),4)
    def test_box_selected_cuts_shift_move_and_keep_selection(self):
        w=self.w;w.create_edit_sequence(A,[(0,1),(2,3),(4,5)],7.188)
        self.box((self.x(1900),175),(self.x(100),35))
        self.drag((self.x(500),47),(self.x(1000),47),True)
        rows=[c for c in sequence_clips(w.active_sequence()) if c['track']=='video']
        self.assertEqual([round(c['at'],1) for c in rows],[.5,1.5,2.5])
        self.assertEqual(len(w.timeline.canvas.selected_keys),4)
    def test_box_on_original_promotes_video_selection(self):
        self.box((self.x(1500),175),(self.x(100),35))
        self.assertIsNotNone(self.w.active_sequence())
        self.assertEqual(len(self.w.timeline.canvas.selected_keys),2)
    def test_original_subtitle_box_delete_and_undo(self):
        w=self.w
        rows=[dict(start=1,end=1.4,text='첫 문장'),dict(start=2,end=2.4,text='두 문장')]
        w.project.subtitles[A]=rows;w.show_source_subtitles(force=True)
        self.box((self.x(500),74),(self.x(2800),111))
        self.assertEqual(w.timeline.canvas.selected_subtitles,{0,1})
        self.assertIsNone(w.active_sequence())
        QTest.keyClick(w.timeline.canvas,Qt.Key.Key_Delete)
        self.assertEqual(w.project.subtitles[A],[])
        w.undo_subtitle();self.assertEqual(w.project.subtitles[A],rows)
    def test_escape_discards_box(self):
        w=self.w;c=w.timeline.canvas
        QTest.mousePress(c,Qt.MouseButton.LeftButton,pos=QPointF(self.x(1500),175).toPoint())
        QTest.mouseMove(c,QPointF(self.x(100),35).toPoint())
        QTest.keyClick(c,Qt.Key.Key_Escape)
        QTest.mouseRelease(c,Qt.MouseButton.LeftButton,pos=QPointF(self.x(100),35).toPoint())
        self.assertIsNone(c.selection_origin)
        self.assertIsNone(w.active_sequence())

if __name__=='__main__':unittest.main()
