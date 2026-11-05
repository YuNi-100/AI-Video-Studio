import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from copy import deepcopy
from pathlib import Path
import tempfile
import time
import unittest
from PySide6.QtCore import Qt,QPointF,QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QToolButton
from app.features.silence.sequence import (validate_sequence,sequence_clips,edit_clip,delete_clip,split_clip,sequence_layout,track_source_ms)
from app.ui.main_window import MainWindow
from app.storage.project_store import load_project


def sample():
    return dict(id='s',name='연습',source='test.mp4',duration=12.,ranges=[[1.,3.],[5.,7.],[9.,11.]])


class ClipModelTests(unittest.TestCase):
    def test_normal_trim_keeps_following_positions(self):
        before=sample()
        result=edit_clip(before,0,'end',-500)
        clips=sequence_clips(result)
        self.assertEqual([c['at'] for c in clips],[0,0,2,2,4,4])
        self.assertEqual(clips[0]['end'],2.5)
        self.assertEqual(clips[1]['end'],2.5)
        self.assertNotIn('clips',before)
    def test_shift_trim_moves_following_tracks(self):
        result=edit_clip(sample(),0,'end',-500,True)
        self.assertEqual([c['at'] for c in result['clips']],[0,0,1.5,1.5,3.5,3.5])
        result=edit_clip(sample(),2,'start',500,True)
        self.assertEqual(result['clips'][2]['start'],5.5)
        self.assertEqual(result['clips'][2]['at'],2)
        self.assertEqual(result['clips'][4]['at'],3.5)
    def test_move_and_shift_move(self):
        result=edit_clip(sample(),4,'move',1000)
        self.assertEqual([c['at'] for c in result['clips']],[0,0,2,2,5,5])
        result=edit_clip(sample(),2,'move',1000,True)
        self.assertEqual([c['at'] for c in result['clips']],[0,0,3,3,5,5])
    def test_clamp_source_and_overlap(self):
        a=edit_clip(sample(),0,'start',-5000,True)
        self.assertEqual(a['clips'][0]['start'],0)
        a=edit_clip(sample(),0,'end',5000)
        self.assertEqual(a['clips'][0]['end'],3)
        a=edit_clip(sample(),0,'end',-5000,True)
        self.assertAlmostEqual(a['clips'][0]['end']-a['clips'][0]['start'],.1)
    def test_ripple_delete_and_empty(self):
        a=delete_clip(sample(),2)
        self.assertEqual([c['at'] for c in a['clips']],[0,0,2,2])
        a=delete_clip(delete_clip(a,0),0)
        self.assertEqual(a['clips'],[])
        self.assertEqual(sequence_layout(a)[2],0)
        self.assertIsNone(track_source_ms([], 'video',0)[0])
    def test_unlinked_track_edits(self):
        a=validate_sequence(dict(sample(),clips=sequence_clips(sample()),linked=False))
        b=edit_clip(a,0,'end',-500,True)
        self.assertEqual([c['at'] for c in b['clips']],[0,0,1.5,2,3.5,4])
        b=delete_clip(a,0)
        self.assertEqual(len(b['clips']),5)
        self.assertEqual(b['clips'][0]['track'],'audio')
        self.assertEqual(b['clips'][0]['at'],0)
    def test_split_selected_linked_and_boundaries(self):
        a=split_clip(sample(),0,1000)
        self.assertEqual(len(a['clips']),8)
        self.assertEqual(a['clips'][1]['at'],1)
        self.assertEqual(a['clips'][1]['group'],a['clips'][3]['group'])
        for position in (0,2000,4000):
            with self.assertRaises(ValueError): split_clip(sample(),0,position)
    def test_gaps_and_out_of_order_source_are_supported(self):
        a=edit_clip(sample(),4,'move',1000)
        self.assertIsNone(track_source_ms(a['clips'],'video',4500)[0])
        self.assertEqual(track_source_ms(a['clips'],'video',5500)[0],9500)
        c=sequence_clips(sample())
        c[0].update(start=9,end=11)
        a=validate_sequence(dict(sample(),clips=c))
        self.assertEqual(a['ranges'][0],[9,11])
    def test_overlap_and_invalid_clip_schema_rejected(self):
        for change in (dict(at=-1),dict(start=-1),dict(end=13),dict(track='other'),dict(at=True)):
            c=sequence_clips(sample()); c[0].update(change)
            with self.assertRaises(ValueError): validate_sequence(dict(sample(),clips=c))
        c=sequence_clips(sample()); c[2]['at']=1
        with self.assertRaises(ValueError): validate_sequence(dict(sample(),clips=c))


class ClipUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.w=MainWindow(); self.w.show(); self.w.preview.audio.setMuted(True)
        self.source=str((Path(__file__).parent/'fixtures/speech-test.mp4').resolve())
        self.w.media.add_files([self.source])
        self.wait(lambda:self.w.preview.ready)
        self.w.create_edit_sequence(self.source,[(0,1),(3,4),(5,6)],7.188)
        self.app.processEvents()
    def tearDown(self):
        self.w.dirty=False; self.w.close(); QTest.qWait(30)
    def wait(self,p):
        deadline=time.monotonic()+8
        while not p() and time.monotonic()<deadline: QTest.qWait(20)
        self.assertTrue(p())
    def drag(self,start,end,shift=False):
        c=self.w.timeline.canvas
        modifier=Qt.KeyboardModifier.ShiftModifier if shift else Qt.KeyboardModifier.NoModifier
        for kind,pos,button,buttons in ((QEvent.Type.MouseButtonPress,start,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton),
                                      (QEvent.Type.MouseMove,end,Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton),
                                      (QEvent.Type.MouseButtonRelease,end,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)):
            event=QMouseEvent(kind,QPointF(*pos),button,buttons,modifier)
            QApplication.sendEvent(c,event)
    def x(self,ms):
        c=self.w.timeline.canvas
        return 95+(ms-c.offset)/c.span*(c.width()-107)
    def test_mouse_trim_shift_move_and_history(self):
        w=self.w
        self.drag((self.x(1000)-2,47),(self.x(750)-2,47),True)
        c=sequence_clips(w.active_sequence())
        self.assertAlmostEqual(c[0]['end'],.75,delta=.03)
        self.assertAlmostEqual(c[2]['at'],.75,delta=.03)
        self.assertAlmostEqual(c[4]['at'],1.75,delta=.03)
        self.assertEqual(w.preview.sequence_tracks,c)
        w.activateWindow()
        QTest.qWait(20)
        QTest.keyClick(w.timeline.canvas,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(sequence_clips(w.active_sequence())[2]['at'],1)
        w.redo_subtitle()
        self.assertAlmostEqual(sequence_clips(w.active_sequence())[2]['at'],.75,delta=.03)
        w.undo_subtitle()
        self.drag((self.x(1500),47),(self.x(2000),47),True)
        c=sequence_clips(w.active_sequence())
        self.assertAlmostEqual(c[2]['at'],1.5,delta=.03)
        self.assertAlmostEqual(c[4]['at'],2.5,delta=.03)
        w.seek_transport(1200)
        self.assertFalse(w.preview.video.video_item.isVisible())
    def test_split_delete_keyboard_save_and_original_preserved(self):
        w=self.w; c=w.timeline.canvas
        before=Path(self.source).read_bytes()
        QTest.mouseClick(c,Qt.MouseButton.LeftButton,pos=QPointF(self.x(500),47).toPoint())
        w.seek_transport(500)
        QTest.keyClick(c,Qt.Key.Key_K,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(sequence_clips(w.active_sequence())),8)
        QTest.keyClick(c,Qt.Key.Key_Delete)
        self.assertEqual(len(sequence_clips(w.active_sequence())),6)
        self.assertAlmostEqual(sequence_clips(w.active_sequence())[0]['at'],.5)
        self.assertAlmostEqual(w.preview.timeline_duration(),3000)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'edited.avsp'
            self.assertTrue(w.save_current(path=path))
            self.assertEqual(load_project(path).edit_sequences[0],w.active_sequence())
        self.assertEqual(Path(self.source).read_bytes(),before)
        w.undo_subtitle(); w.undo_subtitle()
        self.assertEqual(len(sequence_clips(w.active_sequence())),6)
        self.assertEqual(w.preview.timeline_duration(),3000)
    def test_sidebar_tab_close_design_and_unlinked_delete(self):
        w=self.w; t=w.timeline
        self.assertEqual(t.sequence_list.count(),2)
        button=t.sequence_tabs.tabButton(1,t.sequence_tabs.ButtonPosition.RightSide)
        self.assertIsInstance(button,QToolButton)
        self.assertEqual(button.text(),'×')
        self.assertTrue(t.scope.isHidden())
        w.change_link(False)
        w.select_sequence_clip('video',0)
        t.delete_button.click()
        clips=sequence_clips(w.active_sequence())
        self.assertEqual(len(clips),5)
        self.assertEqual(sum(c['track']=='audio' for c in clips),3)
        t.sequence_list.setCurrentRow(0)
        self.assertIsNone(w.active_sequence())
        self.assertTrue(t.scope.isHidden())
        t.sequence_list.setCurrentRow(1)
        self.assertFalse(w.active_sequence()['linked'])
        button.click()
        self.assertEqual(len([s for s in w.project.edit_sequences if not s.get("parent_id")]),1)
        self.assertIn(w.project.edit_sequences[0]["id"],w.closed_sequence_ids)
        self.assertEqual(t.sequence_list.count(),2)
    def test_audio_selection_survives_linked_split(self):
        w=self.w
        w.select_sequence_clip('audio',1)
        w.seek_transport(500)
        w.split_sequence_clip()
        index=w.timeline.canvas.selected_clip
        self.assertEqual(sequence_clips(w.active_sequence())[index]['track'],'audio')
        self.assertEqual(w.timeline.canvas.selected_track,'audio')
    def test_cancel_drag_and_delete_all_undo(self):
        w=self.w; c=w.timeline.canvas
        QTest.mousePress(c,Qt.MouseButton.LeftButton,pos=QPointF(self.x(500),47).toPoint())
        QTest.mouseMove(c,QPointF(self.x(1000),47).toPoint())
        QTest.keyClick(c,Qt.Key.Key_Escape)
        QTest.mouseRelease(c,Qt.MouseButton.LeftButton,pos=QPointF(self.x(1000),47).toPoint())
        self.assertNotIn('clips',w.active_sequence())
        for _ in range(3):
            w.select_sequence_clip('video',0)
            w.delete_sequence_clip()
        self.assertEqual(sequence_clips(w.active_sequence()),[])
        self.assertEqual(w.preview.timeline_duration(),0)
        self.assertFalse(w.preview.video.video_item.isVisible())
        w.undo_subtitle()
        self.assertEqual(w.preview.timeline_duration(),3000)
        self.assertEqual(sequence_clips(w.active_sequence())[0]["at"],2)

if __name__=='__main__': unittest.main()
