import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest
from copy import deepcopy
from PySide6.QtCore import Qt,QPoint,QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from tests import test_timeline_focus as focus_tests
from tests.test_gap_snap import example
from app.features.timeline_actions import gap_at,close_gap
from app.features.silence.sequence import sequence_clips


class SubtitleGapTests(unittest.TestCase):
    def test_unlinked_gap_moves_only_captions_preserving_lengths(self):
        seq=example();seq['linked']=False;before=deepcopy(seq)
        a,b=gap_at(seq,1,'subtitle')
        result=close_gap(seq,a,b,'subtitle')
        self.assertEqual(sequence_clips(result),sequence_clips(seq))
        self.assertEqual(result['timeline_captions'][1]['start'],.5)
        self.assertAlmostEqual(result['timeline_captions'][1]['end']-result['timeline_captions'][1]['start'],.3)
        self.assertTrue(result['timeline_captions'][1]['detached'])
        self.assertEqual(seq,before)

    def test_linked_subtitle_gap_requires_common_empty_interval(self):
        seq=example()
        self.assertIsNone(gap_at(seq,.7,'subtitle'))
        self.assertEqual(gap_at(seq,2.5,'subtitle'),(2,3))
        result=close_gap(seq,2,3,'subtitle')
        self.assertEqual([c['at'] for c in result['clips']],[0,0,1,1,2,2])


class TimelinePolishTests(unittest.TestCase):
    setUpClass=classmethod(focus_tests.TimelineFocusTests.setUpClass.__func__)
    setUp=focus_tests.TimelineFocusTests.setUp
    tearDown=focus_tests.TimelineFocusTests.tearDown
    click_timeline=focus_tests.TimelineFocusTests.click_timeline

    def test_repeat_arrows_keep_step_and_space_does_not_repeat(self):
        w=self.w;c=w.timeline.canvas;self.click_timeline();w.seek_transport(1000)
        for _ in range(2):
            self.app.sendEvent(c,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Right,Qt.KeyboardModifier.NoModifier,'',True,1))
        self.assertEqual(w.transport_position_value(),3000)
        self.app.sendEvent(c,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Left,Qt.KeyboardModifier.ShiftModifier,'',True,1))
        self.assertEqual(w.transport_position_value(),0)
        from unittest.mock import patch
        with patch.object(w,'toggle_transport') as toggle:
            self.app.sendEvent(c,QKeyEvent(QEvent.Type.KeyPress,Qt.Key.Key_Space,Qt.KeyboardModifier.NoModifier,'',True,1))
            toggle.assert_not_called()

    def test_seek_selects_video_and_its_linked_items_and_clears_at_end(self):
        w=self.w;c=w.timeline.canvas;self.click_timeline()
        w.request_timeline_seek(2500)
        self.assertEqual(c.selected_track,'video');self.assertEqual(c.selected_keys,{0,1})
        w.request_timeline_seek(7000)
        self.assertEqual(c.selected_keys,set());self.assertIsNone(c.selected_clip)

    def test_subtitle_row_gap_click_close_undo_redo(self):
        w=self.w;c=w.timeline.canvas
        seq=example();w.project.edit_sequences=[seq];w.open_edit_sequence(seq['id'])
        x=round(95+2500/c.span*(c.width()-107))
        QTest.mouseClick(c,Qt.MouseButton.LeftButton,pos=QPoint(x,94))
        self.assertEqual(c.selected_gap,('subtitle',2000,3000))
        QTest.keyClick(c,Qt.Key.Key_Backspace)
        self.assertEqual([r['at'] for r in sequence_clips(w.active_sequence())],[0,0,1,1,2,2])
        w.undo_subtitle()
        self.assertEqual([r['at'] for r in sequence_clips(w.active_sequence())],[0,0,1,1,3,3])
        w.redo_subtitle()
        self.assertEqual([r['at'] for r in sequence_clips(w.active_sequence())],[0,0,1,1,2,2])

    def test_video_priority_changes_with_seek_but_not_passive_playback(self):
        w=self.w;c=w.timeline.canvas
        seq=example();w.project.edit_sequences=[seq];w.open_edit_sequence(seq['id'])
        w.request_timeline_seek(1200)
        self.assertEqual(c.selected_clip,2);self.assertEqual(c.selected_keys,{2,3})
        self.assertEqual(c.selected_subtitles,{1})
        c.selected_keys=set();c.selected_subtitles=set()
        c.selection_alt=True;w.select_sequence_clip('subtitle',1);c.selection_alt=False
        self.assertEqual(c.selected_keys,set());self.assertEqual(c.selected_subtitles,{1})
        selection=(set(c.selected_keys),set(c.selected_subtitles))
        w.transport_position(1400)
        self.assertEqual((c.selected_keys,c.selected_subtitles),selection)
        w.request_timeline_seek(2500)
        self.assertFalse(c.selected_keys);self.assertFalse(c.selected_subtitles)
        seq['linked']=False;w.project.edit_sequences=[seq]
        w.request_timeline_seek(3200)
        self.assertEqual(c.selected_keys,{4});self.assertEqual(c.selected_track,'video')

    def test_toolbar_and_track_labels_have_padding_inside_border(self):
        w=self.w;self.click_timeline()
        for size in ((1180,780),(1480,940)):
            w.resize(*size);QTest.qWait(30)
            panel=w.timeline.editing_panel
            button=w.timeline.undo
            self.assertGreaterEqual(button.mapTo(panel,QPoint(0,0)).y(),10)
            self.assertGreaterEqual(w.timeline.canvas.mapTo(panel,QPoint(0,0)).x(),10)
            self.assertGreater(w.timeline.canvas.mapTo(panel,QPoint(0,0)).y(),button.mapTo(panel,QPoint(0,button.height())).y())
        if os.environ.get('STUDIO_POLISH_PREVIEW'):w.grab().save(os.environ['STUDIO_POLISH_PREVIEW'])
