import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest,QSignalSpy
from app.ui.timeline import Timeline

class NavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.t=Timeline(); self.t.resize(1100,300); self.t.show()
        self.t.set_source(120000,[],'video'); self.t.zoom.setValue(1000)
        self.app.processEvents(); self.c=self.t.canvas
    def tearDown(self):self.t.close(); self.t.deleteLater(); self.app.processEvents()
    def test_empty_track_drag_keeps_single_click_seek_without_pan(self):
        c=self.c; seek=QSignalSpy(c.seek_requested); edit=QSignalSpy(c.block_moved)
        QTest.mousePress(c,Qt.MouseButton.LeftButton,pos=QPoint(600,90))
        QTest.mouseMove(c,QPoint(300,90),30)
        QTest.mouseRelease(c,Qt.MouseButton.LeftButton,pos=QPoint(300,90))
        self.assertEqual(c.offset,0)
        self.assertEqual(seek.count(),1); self.assertEqual(edit.count(),0)
    def test_ruler_drag_seeks_and_reenables_follow(self):
        self.t.scroll.setValue(10000); c=self.c; seek=QSignalSpy(c.seek_requested)
        QTest.mousePress(c,Qt.MouseButton.LeftButton,pos=QPoint(200,12))
        QTest.mouseMove(c,QPoint(450,12),30)
        QTest.mouseRelease(c,Qt.MouseButton.LeftButton,pos=QPoint(450,12))
        self.assertGreaterEqual(seek.count(),2)
        self.assertGreater(seek.at(seek.count()-1)[0],seek.at(0)[0])
        self.assertTrue(self.t.follow_playhead)
        self.assertFalse(c.drag)
    def test_ruler_escape_stops_scrub_and_scrollbar_changes_view_only(self):
        c=self.c; seek=QSignalSpy(c.seek_requested)
        self.t.scroll.setValue(5000)
        self.assertEqual(c.offset,5000)
        self.assertEqual(seek.count(),0)
        self.t.set_position(100000)
        self.assertEqual(c.offset,5000)
        QTest.mousePress(c,Qt.MouseButton.LeftButton,pos=QPoint(200,12))
        QTest.keyClick(c,Qt.Key.Key_Escape)
        count=seek.count()
        QTest.mouseMove(c,QPoint(700,12),30)
        QTest.mouseRelease(c,Qt.MouseButton.LeftButton,pos=QPoint(700,12))
        self.assertEqual(seek.count(),count)
        QTest.mouseClick(c,Qt.MouseButton.LeftButton,pos=QPoint(400,90))
        self.assertEqual(seek.count(),count+1)
    def test_ticks_change_with_zoom_and_show_fractional_seconds(self):
        major,minor=self.c.tick_steps()
        self.assertEqual(major%minor,0)
        self.assertGreaterEqual(minor/self.c.span*(self.c.width()-107),8)
        self.t.zoom.setValue(10000)
        fine,_=self.c.tick_steps()
        self.assertLess(fine,major)
        self.assertEqual(self.c.ruler_time(1234,100),'00:01.234')
        self.assertEqual(self.c.ruler_time(61000,1000),'00:01:01')
        self.assertFalse(self.c.grab().isNull())

if __name__=='__main__':unittest.main()


class ScrubTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        from app.ui.main_window import MainWindow
        self.w=MainWindow();self.w.show()
    def tearDown(self):self.w.dirty=False;self.w.close();QTest.qWait(20)
    def test_fast_requests_are_coalesced_and_final_position_flushed(self):
        from unittest.mock import patch
        w=self.w
        with patch.object(w,"seek_transport") as seek:
            w.begin_timeline_scrub()
            for position in range(100):w.request_timeline_seek(position*1000)
            self.assertEqual(seek.call_count,0)
            QTest.qWait(160)
            self.assertEqual(seek.call_count,1)
            seek.assert_called_with(99000,resume=False)
            w.request_timeline_seek(4567);w.end_timeline_scrub()
            self.assertEqual(seek.call_count,2)
            seek.assert_called_with(4567,resume=False)
            self.assertFalse(w._scrub_timer.isActive())
    def test_scrub_pauses_and_resumes_only_if_previously_playing(self):
        from unittest.mock import patch
        w=self.w;w.preview.ready=True;w.preview._playing=True
        with patch.object(w.preview,"toggle_play") as toggle:
            w.begin_timeline_scrub()
            self.assertEqual(toggle.call_count,1)
            w.preview._playing=False
            w.end_timeline_scrub()
            self.assertEqual(toggle.call_count,2)
        w.preview._playing=False
        with patch.object(w.preview,"toggle_play") as toggle:
            w.begin_timeline_scrub();w.end_timeline_scrub()
            toggle.assert_not_called()
    def test_project_switch_discards_delayed_seek_and_friendly_memory_error(self):
        from unittest.mock import patch
        w=self.w
        with patch.object(w,"seek_transport") as seek:
            w.begin_timeline_scrub();w.request_timeline_seek(10000)
            w.abort_timeline_scrub();QTest.qWait(150)
            seek.assert_not_called()
        w.preview.ready=True
        w.preview.on_error(None,"Cannot allocate memory")
        self.assertIn("재생 메모리 오류",w.preview.status.text())
        self.assertNotIn("파일 손상",w.preview.status.text())
        self.assertEqual(w.preview.status.toolTip(),"Cannot allocate memory")
