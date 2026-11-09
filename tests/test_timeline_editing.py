import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest,tempfile,time
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest,QSignalSpy
from PySide6.QtWidgets import QApplication
from app.ui.main_window import MainWindow
from app.storage.project_store import load_project
from app.core.project import validate_placement
from app.features.subtitles.worker import transcribe
from types import SimpleNamespace

ROOT=Path(__file__).parent/'fixtures'
A=str((ROOT/'테스트 영상.mp4').resolve())
B=str((ROOT/'테스트 영상.mov').resolve())

class TimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        from app.ui.theme import STYLE
        cls.app.setStyle("Fusion");cls.app.setStyleSheet(STYLE)
    def setUp(self):
        self.w=MainWindow(); self.w.show(); self.w.activateWindow();QTest.qWait(30); self.w.preview.audio.setMuted(True)
        self.w.media.add_files([A,B]); self.wait(lambda:self.w.preview.ready)
        self.w.project.subtitles[A]=[dict(start=.5,end=1.5,text='첫 영상',reviewed=True)]
        self.w.project.subtitles[B]=[dict(start=.2,end=1.2,text='둘째 영상',reviewed=True)]
        self.w.show_source_subtitles(force=True)
    def tearDown(self):
        self.w.dirty=False; self.w.close(); QTest.qWait(30)
    def wait(self,p):
        until=time.monotonic()+7
        while not p() and time.monotonic()<until: QTest.qWait(20)
        self.assertTrue(p(),f"source={Path(str(self.w.preview.source)).name}, position={self.w.preview.timeline_position()}, playing={self.w.preview._playing}, ready={self.w.preview.ready}, pending={self.w.pending_seek}")
    def test_link_unlink_actual_player_offsets_and_undo(self):
        w=self.w
        w.move_timeline_block('video',0,1000)
        self.assertEqual(w.placement(A),dict(video=1.,audio=1.,linked=True))
        w.preview.seek_timeline(1500)
        self.assertAlmostEqual(w.preview.player.position(),500,delta=150)
        self.assertAlmostEqual(w.preview.audio_player.position(),500,delta=150)
        w.change_link(False); w.move_timeline_block('audio',0,2000)
        w.preview.seek_timeline(2500)
        self.assertAlmostEqual(w.preview.player.position(),1500,delta=150)
        self.assertAlmostEqual(w.preview.audio_player.position(),500,delta=150)
        w.undo_subtitle(); self.assertEqual(w.placement(A)['audio'],1.)
        w.change_link(True); self.assertEqual(w.placement(A)['audio'],w.placement(A)['video'])
    def test_caption_drag_actual_mouse_and_saved_offsets(self):
        w=self.w; c=w.timeline.canvas; spy=QSignalSpy(c.block_moved)
        def x(ms): return round(95+(ms-c.offset)/c.span*(c.width()-107))
        QTest.mousePress(c,Qt.MouseButton.LeftButton,pos=QPoint(x(900),90))
        QTest.mouseMove(c,QPoint(x(1400),90),30)
        QTest.mouseRelease(c,Qt.MouseButton.LeftButton,pos=QPoint(x(1400),90))
        self.assertEqual(spy.count(),1)
        row=w.project.subtitles[A][0]
        self.assertAlmostEqual(row['end']-row['start'],1.,places=3)
        self.assertGreater(row['start'],.8)
        self.assertFalse(row['reviewed'])
        w.undo_subtitle(); self.assertEqual(w.project.subtitles[A][0]['start'],.5)
        w.move_timeline_block('video',0,1000)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'test.avsp'; self.assertTrue(w.save_current(path=path))
            saved=load_project(path); self.assertEqual(saved.media_placements[A]['video'],1.)
    def test_combined_seek_cue_mapping_reorder_and_srt(self):
        w=self.w; w.timeline.scope.setCurrentIndex(1)
        self.assertEqual(len(w.sequence_items),2)
        self.assertEqual(w.timeline.canvas.duration,6000)
        self.assertEqual(w.timeline.canvas.segments[1]['start'],3.2)
        w.seek_transport(3500); w.seek_transport(3800)
        self.wait(lambda:w.preview.ready and str(w.preview.source)==B)
        self.assertAlmostEqual(w.preview.timeline_position(),800,delta=100)
        w.timeline_select(1); self.assertEqual(w.subtitle_panel.editor.selected_index,0)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'all.srt'; self.assertTrue(w.export_current_subtitles(path))
            self.assertIn('00:00:03,200',path.read_text('utf-8-sig'))
        w.reorder_media(-1)
        self.assertEqual(w.sequence_items[0][0],B)
        self.assertEqual(w.timeline.canvas.segments[1]['start'],3.5)
    @unittest.skipUnless(os.environ.get("STUDIO_NATIVE_MEDIA_TEST"),"validated separately using a native Windows video sink")
    def test_combined_continuous_play_crosses_clip_boundary(self):
        w=self.w; w.timeline.scope.setCurrentIndex(1)
        w.seek_transport(2800); w.preview.toggle_play()
        self.wait(lambda:w.preview.ready and str(w.preview.source)==B and w.preview.timeline_position()>100)
        self.assertTrue(w.preview._playing)
        self.assertGreater(w.timeline.canvas.position,3000)
    def test_generation_locks_cross_source_transport(self):
        w=self.w; w.timeline.scope.setCurrentIndex(1)
        with patch.object(type(w.subtitle_job),"busy",new_callable=__import__('unittest.mock',fromlist=['PropertyMock']).PropertyMock,return_value=True):
            w.seek_transport(3500)
            self.assertEqual(w.media.selected_path(),A)
            self.assertEqual(str(w.preview.source),A)
            w.transport_finished()
            self.assertFalse(w.switch_queued)

    def test_numeric_timing_edits_apply_without_extra_controls(self):
        w=self.w; w.select_subtitle(0); e=w.subtitle_panel.editor
        e.start.setValue(.75); e.end.setValue(1.1)
        self.assertEqual(w.project.subtitles[A][0]['start'],.5)
        self.assertTrue(w.apply_subtitle_edit())
        self.assertEqual(w.project.subtitles[A][0]['start'],.75)
        from PySide6.QtWidgets import QPushButton
        texts=[button.text() for button in w.findChildren(QPushButton)]
        for removed in ('열기','프로젝트 저장','SRT 내보내기 ↗','현재 위치','−0.1초','+0.1초'):
            self.assertNotIn(removed,texts)
        self.assertFalse(any('반복 듣기' in text for text in texts))
        self.assertTrue(w.export_action.isEnabled())
        from unittest.mock import patch
        with patch.object(w,'export_current_subtitles') as export:
            w.export_action.trigger()
            export.assert_called_once()

    def drag_edge(self,start,end):
        c=self.w.timeline.canvas
        def x(ms):return round(95+(ms-c.offset)/c.span*(c.width()-107))
        QTest.mousePress(c,Qt.MouseButton.LeftButton,pos=QPoint(x(start),90))
        QTest.mouseMove(c,QPoint(x(end),90),25)
        QTest.mouseRelease(c,Qt.MouseButton.LeftButton,pos=QPoint(x(end),90))

    def test_resize_edges_updates_overlay_editor_save_and_redo(self):
        w=self.w
        self.drag_edge(500,800)
        row=w.project.subtitles[A][0]
        self.assertAlmostEqual(row['start'],.8,delta=.02)
        self.assertEqual(row['end'],1.5)
        self.assertFalse(row['reviewed'])
        self.assertEqual(w.subtitle_panel.editor.start.value(),row['start'])
        self.drag_edge(1500,2200)
        row=w.project.subtitles[A][0]
        self.assertAlmostEqual(row['end'],2.2,delta=.02)
        w.preview.seek_timeline(2000)
        from app.features.subtitles.editing import active_text
        self.assertEqual(active_text(w.preview.subtitles,2000),'첫 영상')
        c=w.timeline.canvas; c.setFocus()
        QTest.keyClick(c,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(w.project.subtitles[A][0]['end'],1.5)
        QTest.keyClick(c,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier)
        self.assertAlmostEqual(w.project.subtitles[A][0]['end'],2.2,delta=.02)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'resize.avsp'; self.assertTrue(w.save_current(path=path))
            self.assertEqual(load_project(path).subtitles[A],w.project.subtitles[A])

    def test_resize_limits_and_escape_cancels_without_history(self):
        w=self.w; c=w.timeline.canvas
        self.drag_edge(500,1900)
        row=w.project.subtitles[A][0]
        self.assertEqual(round((row['end']-row['start'])*1000),100)
        w.undo_subtitle()
        self.drag_edge(1500,100)
        row=w.project.subtitles[A][0]
        self.assertEqual(round((row['end']-row['start'])*1000),100)
        w.undo_subtitle()
        count=len(w.project_undo)
        def x(ms):return round(95+ms/c.span*(c.width()-107))
        QTest.mousePress(c,Qt.MouseButton.LeftButton,pos=QPoint(x(500),90))
        QTest.mouseMove(c,QPoint(x(800),90),25)
        QTest.keyClick(c,Qt.Key.Key_Escape)
        QTest.mouseRelease(c,Qt.MouseButton.LeftButton,pos=QPoint(x(800),90))
        self.assertEqual(w.project.subtitles[A][0]['start'],.5)
        self.assertEqual(len(w.project_undo),count)

    def test_resize_combined_maps_to_source_and_keeps_other_clip(self):
        w=self.w; w.timeline.scope.setCurrentIndex(1)
        self.drag_edge(3200,3400)
        self.wait(lambda:w.preview.ready and str(w.preview.source)==B)
        self.assertAlmostEqual(w.project.subtitles[B][0]['start'],.4,delta=.02)
        self.assertEqual(w.project.subtitles[A][0]['start'],.5)
        self.assertEqual(w.subtitle_panel.editor.selected_index,0)
        w.undo_subtitle()
        self.assertEqual(w.project.subtitles[B][0]['start'],.2)

    def test_short_blocks_keep_center_move_and_zoom_exposes_handles(self):
        w=self.w; c=w.timeline.canvas
        w.project.subtitles[A]=[dict(start=1.,end=1.08,text='짧은 자막')]
        w.show_source_subtitles(force=True)
        def x(ms):return 95+(ms-c.offset)/c.span*(c.width()-107)
        self.assertEqual(c.subtitle_hit(x(1040),90)[1],'move')
        w.timeline.zoom.setValue(10000)
        w.timeline.scroll.setValue(500)
        self.assertEqual(c.subtitle_hit(x(1000),90)[1],'start')
        self.assertEqual(c.subtitle_hit(x(1080),90)[1],'end')
        self.assertIsNone(c.subtitle_hit(x(1080),20))

    def test_invalid_placement_and_source_time_srt(self):
        for v in (dict(video=-1),dict(audio=float('nan')),dict(linked='yes')):
            with self.assertRaises(ValueError): validate_placement(v)
        w=self.w; w.move_timeline_block('video',0,1000)
        w.project.subtitles[A]=[dict(start=1.5,end=2.5,text='원본 기준',reviewed=True)]
        w.show_source_subtitles(force=True); w.subtitle_panel.editor.export_basis.setCurrentIndex(1)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.srt'; self.assertTrue(w.export_current_subtitles(path))
            self.assertIn('00:00:00,500',path.read_text('utf-8-sig'))

class WordBoundaryTests(unittest.TestCase):
    def test_word_boundaries_override_coarse_segment(self):
        options={}
        class Model:
            def __init__(self,*a,**kw): pass
            def transcribe(self,*a,**kw):
                options.update(kw)
                word=lambda start,end,text:SimpleNamespace(start=start,end=end,word=text)
                row=SimpleNamespace(text=' 테스트 ',start=0,end=3,words=[word(.4,.8,'테'),word(.9,1.2,'스트')])
                return iter([row]),SimpleNamespace(duration=3.,language='ko')
        events=[]; transcribe(A,'tiny','ko','unused',events.append,model_factory=Model)
        self.assertTrue(options['word_timestamps'])
        row=events[-1]['segments'][0]
        self.assertEqual((row['start'],row['end']),(.4,1.2))

if __name__=='__main__': unittest.main()
