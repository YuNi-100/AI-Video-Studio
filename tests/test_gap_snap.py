import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest,time,tempfile
from copy import deepcopy
from pathlib import Path
from PySide6.QtCore import Qt,QPointF,QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from app.features.silence.sequence import validate_sequence,sequence_clips,sequence_layout,move_clips
from app.features.timeline_actions import delete_items,gap_at,close_gap,snap_move,safe_move
from app.storage.project_store import load_project

SOURCE=str((Path(__file__).parent/'fixtures/speech-test.mp4').resolve())


def example(positions=(0,1,3)):
    seq=validate_sequence(dict(id='test',name='편집 테스트',source=SOURCE,duration=7.188,ranges=[[0,1],[2,3],[4,5]]))
    clips=sequence_clips(seq)
    for i,c in enumerate(clips):c['at']=positions[i//2]
    seq=validate_sequence(dict(seq,clips=clips))
    rows={SOURCE:[dict(start=.2,end=.5,text='A'),dict(start=2.2,end=2.5,text='B'),dict(start=4.2,end=4.5,text='C')]}
    return validate_sequence(dict(seq,timeline_captions=sequence_layout(seq,rows)[1]))


class GapSnapModelTests(unittest.TestCase):
    def test_normal_delete_leaves_all_other_positions_and_source_ranges(self):
        seq=example();before=deepcopy(seq)
        result=delete_items(seq,{2})
        self.assertEqual([(c['at'],c['start'],c['end']) for c in result['clips'] if c['track']=='video'],[(0,0,1),(3,4,5)])
        self.assertEqual([r['text'] for r in result['timeline_captions']],['A','C'])
        self.assertEqual(seq,before)

    def test_ripple_delete_removes_selected_duration_preserving_other_gaps(self):
        result=delete_items(example(),{2},ripple=True)
        self.assertEqual([c['at'] for c in result['clips'] if c['track']=='video'],[0,2])
        self.assertEqual([r['start'] for r in result['timeline_captions']],[.2,2.2])

    def test_gap_closing_preserves_every_clip_and_caption_length(self):
        seq=example();self.assertEqual(gap_at(seq,2.5,'video'),(2,3))
        result=close_gap(seq,2,3,'video')
        self.assertEqual([c['at'] for c in result['clips']],[0,0,1,1,2,2])
        self.assertEqual([(c['start'],c['end']) for c in result['clips']],[(c['start'],c['end']) for c in seq['clips']])
        self.assertEqual([round(r['end']-r['start'],3) for r in result['timeline_captions']],[.3,.3,.3])

    def test_gap_does_not_cross_audio_or_independent_caption(self):
        seq=example();seq['clips'][3]['end']=4
        seq=validate_sequence(seq)
        self.assertIsNone(gap_at(seq,2.5,'video'))
        seq=example();seq['timeline_captions'].append(dict(id='free',start=2.2,end=2.8,text='독립',detached=True))
        seq['timeline_captions'].sort(key=lambda r:r['start'])
        self.assertIsNone(gap_at(seq,2.5,'video'))
        with self.assertRaises(ValueError):close_gap(seq,2,3,'video')

    def test_leading_gap_and_unlinked_audio_gap(self):
        seq=example((1,3,5));self.assertEqual(gap_at(seq,.5,'video'),(0,1))
        result=close_gap(seq,0,1,'video');self.assertEqual(result['clips'][0]['at'],0)
        seq=example();seq['linked']=False;seq['clips'][3]['at']=2
        seq=validate_sequence(seq)
        self.assertEqual(gap_at(seq,1.5,'audio'),(1,2))
        result=close_gap(seq,1,2,'audio')
        self.assertEqual([c['at'] for c in result['clips'] if c['track']=='video'],[0,1,3])

    def test_snap_has_pixel_tolerance_and_no_snap_deep_inside(self):
        seq=example()
        self.assertEqual(snap_move(seq,{4,5},-1970,80),(-2000,1000))
        self.assertIsNone(snap_move(seq,{4,5},-3000,80))

    def test_safe_snap_pushes_without_trimming_and_moves_owned_captions(self):
        seq=example();before=deepcopy(seq)
        result=safe_move(seq,{4},{2},-2000)
        self.assertEqual([c['at'] for c in result['clips']],[0,0,2,2,1,1])
        self.assertEqual([(c['start'],c['end']) for c in result['clips']],[(c['start'],c['end']) for c in seq['clips']])
        cues={r['text']:r['start'] for r in result['timeline_captions']}
        self.assertEqual(cues,{'A':.2,'C':1.2,'B':2.2})
        self.assertEqual(seq,before)

    def test_safe_move_rejects_crossing_track_instead_of_trimming(self):
        seq=example();seq['clips'][1]['end']=1.5;seq['clips'][3]['at']=1.5
        seq=validate_sequence(seq)
        with self.assertRaises(ValueError):safe_move(seq,{4,5},{2},-2000)

    def test_existing_overwrite_still_removes_overlapped_destination(self):
        seq=example();result=move_clips(seq,{4,5},-3000)
        self.assertEqual(len(result['clips']),4)
        self.assertTrue(all(c['group']!='pair-0' for c in result['clips']))

    def test_multiple_deleted_sets_do_not_double_count_time(self):
        result=delete_items(example((0,1,2)),{0,1,2,3},ripple=True)
        self.assertEqual([c['at'] for c in result['clips']],[0,0])
        self.assertEqual(result['timeline_captions'][0]['start'],.2)


class GapSnapUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        from app.ui.theme import STYLE
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        from app.ui.main_window import MainWindow
        self.w=MainWindow();self.w.show();self.w.preview.audio.setMuted(True)
        self.w.media.add_files([SOURCE]);end=time.monotonic()+8
        while not self.w.preview.ready and time.monotonic()<end:QTest.qWait(20)
        self.assertTrue(self.w.preview.ready)
        self.w.project.edit_sequences=[example()];self.w.mark_dirty();self.w.open_edit_sequence('test')
        self.before=Path(SOURCE).read_bytes()

    def tearDown(self):
        self.assertEqual(Path(SOURCE).read_bytes(),self.before)
        self.w.dirty=False
        for doc in self.w.documents:doc['dirty']=False
        self.w.close();QTest.qWait(20)

    def x(self,ms):
        c=self.w.timeline.canvas;return 95+(ms-c.offset)/c.span*(c.width()-107)

    def event(self,kind,ms,y,mod=Qt.KeyboardModifier.NoModifier):
        c=self.w.timeline.canvas
        press=kind==QEvent.Type.MouseButtonPress
        release=kind==QEvent.Type.MouseButtonRelease
        QApplication.sendEvent(c,QMouseEvent(kind,QPointF(self.x(ms),y),Qt.MouseButton.LeftButton if press or release else Qt.MouseButton.NoButton,
            Qt.MouseButton.NoButton if release else Qt.MouseButton.LeftButton,mod))

    def click(self,ms,y=47,mod=Qt.KeyboardModifier.NoModifier):
        self.event(QEvent.Type.MouseButtonPress,ms,y,mod);self.event(QEvent.Type.MouseButtonRelease,ms,y,mod)

    def test_delete_and_backspace_keep_position_alt_backspace_ripples(self):
        c=self.w.timeline.canvas
        for key in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace):
            self.click(1500);QTest.keyClick(c,key)
            self.assertEqual([x['at'] for x in self.w.active_sequence()['clips']],[0,0,3,3])
            self.w.undo_subtitle()
        self.click(1500);QTest.keyClick(c,Qt.Key.Key_Backspace,Qt.KeyboardModifier.AltModifier)
        self.assertEqual([x['at'] for x in self.w.active_sequence()['clips']],[0,0,2,2])
        self.w.undo_subtitle();self.w.redo_subtitle()
        self.assertEqual([r['start'] for r in self.w.active_sequence()['timeline_captions']],[.2,2.2])

    def test_gap_click_highlight_close_undo_and_escape(self):
        c=self.w.timeline.canvas
        self.click(2500);self.assertEqual(c.selected_gap,('video',2000,3000))
        QTest.keyClick(c,Qt.Key.Key_Delete)
        self.assertEqual(self.w.active_sequence()['clips'][4]['at'],3)
        c.grab()
        QTest.keyClick(c,Qt.Key.Key_Backspace)
        self.assertEqual(self.w.active_sequence()['clips'][4]['at'],2)
        self.assertIsNone(c.selected_gap)
        self.w.undo_subtitle();self.assertEqual(self.w.active_sequence()['clips'][4]['at'],3)
        self.click(2500);QTest.keyClick(c,Qt.Key.Key_Escape);self.assertIsNone(c.selected_gap)

    def test_drag_near_boundary_previews_safe_insert_and_preserves_lengths(self):
        w=self.w;c=w.timeline.canvas
        self.event(QEvent.Type.MouseButtonPress,3500,47)
        self.event(QEvent.Type.MouseMove,1530,47)
        self.assertTrue(c.snap_insert);self.assertEqual(c.snap_guide,1000)
        c.grab()
        if os.environ.get('STUDIO_SNAP_PREVIEW'):c.grab().save(os.environ['STUDIO_SNAP_PREVIEW'])
        self.event(QEvent.Type.MouseButtonRelease,1530,47)
        self.assertEqual([r['at'] for r in w.active_sequence()['clips']],[0,0,2,2,1,1])
        self.assertTrue(all(r['end']-r['start']==1 for r in w.active_sequence()['clips']))
        self.assertEqual([r['text'] for r in w.active_sequence()['timeline_captions']],['A','C','B'])
        w.undo_subtitle();self.assertEqual(w.active_sequence()['clips'][4]['at'],3)
        w.redo_subtitle();self.assertEqual(w.active_sequence()['clips'][4]['at'],1)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'snap.avsp';self.assertTrue(w.save_current(path=path))
            self.assertEqual([s for s in load_project(path).edit_sequences if not s.get("parent_id")],[w.active_sequence()])

    def test_deep_drag_keeps_overwrite_preview_and_undo(self):
        c=self.w.timeline.canvas
        self.event(QEvent.Type.MouseButtonPress,3500,47);self.event(QEvent.Type.MouseMove,500,47)
        self.assertFalse(c.snap_insert);c.grab()
        self.event(QEvent.Type.MouseButtonRelease,500,47)
        self.assertEqual(len(self.w.active_sequence()['clips']),4)
        self.w.undo_subtitle();self.assertEqual(len(self.w.active_sequence()['clips']),6)

    def test_alt_individual_video_delete_preserves_audio_and_unselected_caption(self):
        c=self.w.timeline.canvas
        self.click(1500,47,Qt.KeyboardModifier.AltModifier)
        QTest.keyClick(c,Qt.Key.Key_Delete)
        seq=self.w.active_sequence()
        self.assertEqual(sum(x['track']=='audio' for x in seq['clips']),3)
        self.assertEqual([r['text'] for r in seq['timeline_captions']],['A','B','C'])
        self.assertTrue(next(r for r in seq['timeline_captions'] if r['text']=='B')['detached'])

    def test_shift_drag_and_box_selection_are_preserved(self):
        c=self.w.timeline.canvas
        self.event(QEvent.Type.MouseButtonPress,1500,47,Qt.KeyboardModifier.ShiftModifier)
        self.event(QEvent.Type.MouseMove,2000,47,Qt.KeyboardModifier.ShiftModifier)
        self.assertFalse(c.snap_insert)
        self.event(QEvent.Type.MouseButtonRelease,2000,47,Qt.KeyboardModifier.ShiftModifier)
        self.assertAlmostEqual(self.w.active_sequence()['clips'][4]['at'],3.5,delta=.02)
        self.w.undo_subtitle()
        self.click(2500);self.assertIsNotNone(c.selected_gap)
        c.start_range_selection(QMouseEvent(QEvent.Type.MouseButtonPress,QPointF(self.x(2100),-5),Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier))
        self.event(QEvent.Type.MouseMove,3600,151)
        self.event(QEvent.Type.MouseButtonRelease,3600,151)
        self.assertIsNone(c.selected_gap)
        self.assertTrue(c.selected_keys)
