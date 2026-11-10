import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest
from copy import deepcopy
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from tests import test_timeline_focus as focus_tests
from tests.test_gap_snap import SOURCE,example
from app.features.silence.sequence import sequence_clips

CTRL=Qt.KeyboardModifier.ControlModifier


class TimelineCommandTests(unittest.TestCase):
    setUpClass=classmethod(focus_tests.TimelineFocusTests.setUpClass.__func__)
    setUp=focus_tests.TimelineFocusTests.setUp
    tearDown=focus_tests.TimelineFocusTests.tearDown
    click_timeline=focus_tests.TimelineFocusTests.click_timeline

    def child(self):
        w=self.w;seq=example();w.project.edit_sequences=[seq];w.open_edit_sequence(seq['id'])
        child=next(s for s in w.project.edit_sequences if s.get('parent_id')==seq['id'])
        w.open_edit_sequence(child['id']);self.click_timeline()
        return w.timeline.canvas

    def test_child_shift_move_keeps_leading_gap_and_then_split_keys(self):
        w=self.w;c=self.child()
        x=lambda ms:95+(ms-c.offset)/c.span*(c.width()-107)
        for kind,ms,button,buttons in ((QEvent.Type.MouseButtonPress,500,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton),(QEvent.Type.MouseMove,1500,Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton),(QEvent.Type.MouseButtonRelease,1500,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)):
            pos=QPointF(x(ms),47)
            self.app.sendEvent(c,QMouseEvent(kind,pos,QPointF(c.mapToGlobal(pos.toPoint())),button,buttons,Qt.KeyboardModifier.ShiftModifier))
        self.assertEqual([r['at'] for r in sequence_clips(w.active_sequence())],[1,1,2,2,4,4])
        self.assertEqual(c.blocks[0][1],1000)
        self.assertTrue(w.timeline_focus.active)
        w.request_timeline_seek(1500);QTest.keyClick(c,Qt.Key.Key_K,CTRL)
        self.assertEqual(len(sequence_clips(w.active_sequence())),8)
        self.assertTrue(w.timeline_focus.active)
        w.request_timeline_seek(1750);QTest.keyClick(c,Qt.Key.Key_K,CTRL)
        self.assertEqual(len(sequence_clips(w.active_sequence())),10)

    def test_cut_paste_undo_redo_in_child_preserves_lengths_and_captions(self):
        w=self.w;c=self.child();w.request_timeline_seek(1500)
        w.select_sequence_clip('video',2)
        before=deepcopy(w.active_sequence());QTest.keyClick(c,Qt.Key.Key_X,CTRL)
        self.assertEqual([r['at'] for r in sequence_clips(w.active_sequence())],[0,0,3,3])
        self.assertEqual([r['text'] for r in c.segments],['A','C'])
        self.assertEqual(len(sequence_clips(w.clip_clipboard)),2)
        w.request_timeline_seek(1000);QTest.keyClick(c,Qt.Key.Key_V,CTRL)
        self.assertEqual(len(sequence_clips(w.active_sequence())),6)
        self.assertEqual([r['text'] for r in c.segments],['A','B','C'])
        w.undo_subtitle();w.undo_subtitle();self.assertEqual(sequence_clips(w.active_sequence()),sequence_clips(before))
        w.redo_subtitle();self.assertEqual(len(sequence_clips(w.active_sequence())),4)

    def test_cut_all_child_then_paste_is_recoverable(self):
        w=self.w;c=self.child();c.selected_keys=set(range(6));c.selected_clip=0;c.selected_subtitles={0,1,2}
        QTest.keyClick(c,Qt.Key.Key_X,CTRL)
        self.assertEqual(sequence_clips(w.active_sequence()),[])
        QTest.keyClick(c,Qt.Key.Key_V,CTRL)
        self.assertEqual(len(sequence_clips(w.active_sequence())),6)

    def test_text_cut_and_list_focus_do_not_cut_timeline(self):
        w=self.w;c=self.child();before=deepcopy(w.active_sequence())
        text=w.project_name;QTest.mouseClick(text,Qt.MouseButton.LeftButton);text.setText('abc');text.selectAll()
        QTest.keyClick(text,Qt.Key.Key_X,CTRL);self.assertEqual(text.text(),'')
        self.assertEqual(w.active_sequence(),before)
        text.setText(w.project.name)
        tree=w.timeline.sequence_tree;tree.setFocus();QTest.keyClick(tree,Qt.Key.Key_X,CTRL)
        self.assertEqual(w.active_sequence(),before)

    def test_alt_video_cut_preserves_unselected_audio_and_caption(self):
        w=self.w;c=self.child();c.selected_keys={0};c.selected_clip=0;c.selected_subtitles=set();c.individual_selection=True
        QTest.keyClick(c,Qt.Key.Key_X,CTRL)
        self.assertEqual(sum(r['track']=='audio' for r in sequence_clips(w.active_sequence())),3)
        self.assertEqual(len(c.segments),3)
        self.assertEqual([r['track'] for r in sequence_clips(w.clip_clipboard)],['video'])

    def test_cut_rejection_preserves_existing_clipboard_and_document(self):
        w=self.w;c=self.child();before=deepcopy(w.active_sequence());w.clip_clipboard={'previous':True}
        with patch.object(w,'commit_sequence',side_effect=ValueError('blocked')):
            QTest.keyClick(c,Qt.Key.Key_X,CTRL)
        self.assertEqual(w.clip_clipboard,{'previous':True});self.assertEqual(w.active_sequence(),before)

    def test_click_panel_padding_after_text_edit_routes_split_to_timeline(self):
        w=self.w;c=self.child();w.request_timeline_seek(500)
        text=w.project_name;QTest.mouseClick(text,Qt.MouseButton.LeftButton)
        original=text.text();self.assertFalse(w.timeline_focus.active)
        QTest.mouseClick(w.timeline.editing_panel,Qt.MouseButton.LeftButton,pos=QPoint(4,4))
        self.assertTrue(w.timeline_focus.active)
        self.assertIs(self.app.focusWidget(),c)
        QTest.keyClick(c,Qt.Key.Key_K,CTRL)
        self.assertEqual(len(sequence_clips(w.active_sequence())),8)
        self.assertEqual(text.text(),original)

    def test_cross_source_paste_in_file_view_routes_to_parent_and_undo_restores_view(self):
        w=self.w;c=self.child();child=w.active_edit_id;parent=w.active_sequence()['parent_id']
        other=str(__import__('pathlib').Path(SOURCE).with_name('테스트 영상.mov'))
        w.media.add_files([other])
        from app.features.silence.sequence import validate_sequence
        from app.features.clip_clipboard import copy_sets
        seq=validate_sequence(dict(id='payload',name='다른 영상',source=other,duration=3,ranges=[[0,1]]))
        w.clip_clipboard=copy_sets(seq,{0,1})
        w.request_timeline_seek(500);before=deepcopy(w.active_sequence())
        QTest.keyClick(c,Qt.Key.Key_V,CTRL)
        self.assertEqual(w.active_edit_id,parent)
        self.assertTrue(any(r.get('source')==other for r in sequence_clips(w.active_sequence())))
        w.undo_subtitle();self.assertEqual(w.active_edit_id,child)
        self.assertEqual(sequence_clips(w.active_sequence()),sequence_clips(before))

    def test_interleaved_child_collision_is_blocked_in_preview_without_data_loss(self):
        w=self.w;other=str(__import__('pathlib').Path(SOURCE).with_name('테스트 영상.mov'))
        w.create_labeled_edit([SOURCE,other,SOURCE]);parent=w.active_edit_id
        child=next(s for s in w.project.edit_sequences if s.get('parent_id')==parent and s['source']==SOURCE)
        w.open_edit_sequence(child['id']);self.click_timeline();before=deepcopy(w.project.edit_sequences)
        w.preview_sequence_edit(0,'move',1000,True)
        self.assertTrue(w.timeline.canvas.edit_blocked)
        w.edit_sequence_clip('video',0,'move',1000,True)
        self.assertEqual(w.project.edit_sequences,before)

    def test_caption_only_cut_paste_keeps_video_audio_positions(self):
        w=self.w;c=self.child()
        positions=lambda:[(r['track'],r['at'],r['start'],r['end'],r['group']) for r in sequence_clips(w.active_sequence())]
        clips=positions()
        c.selected_keys=set();c.selected_clip=None;c.selected_subtitles={0};c.individual_selection=True
        QTest.keyClick(c,Qt.Key.Key_X,CTRL)
        self.assertEqual(positions(),clips)
        self.assertEqual(len(c.segments),2)
        w.seek_transport(2500);QTest.keyClick(c,Qt.Key.Key_V,CTRL)
        self.assertEqual(positions(),clips)
        self.assertEqual(next(r['start'] for r in c.segments if r['text']=='A'),2.5)

