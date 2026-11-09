import os,time,unittest
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest,QSignalSpy
from PySide6.QtWidgets import QApplication
from app.ui.seek_slider import SeekSlider
from app.ui.video_player import VideoPlayer

class SeekSliderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        from app.ui.theme import STYLE
        cls.app.setStyle('Fusion');cls.app.setStyleSheet(STYLE)

    def test_click_endpoints_drag_and_disabled(self):
        slider=SeekSlider();slider.setRange(0,24000);slider.show();QTest.qWait(20);slider.resize(600,40);QTest.qWait(20)
        try:
            moved=QSignalSpy(slider.sliderMoved)
            def point(f):return QPoint(round((slider.width()-1)*f),slider.height()//2)
            QTest.mouseClick(slider,Qt.MouseButton.LeftButton,pos=point(.75))
            self.assertAlmostEqual(slider.value(),18000,delta=450);self.assertGreater(moved.count(),0)
            QTest.mousePress(slider,Qt.MouseButton.LeftButton,pos=point(.25))
            QTest.mouseMove(slider,point(.6));QTest.mouseRelease(slider,Qt.MouseButton.LeftButton,pos=point(.6))
            self.assertAlmostEqual(slider.value(),14400,delta=450);self.assertFalse(slider.isSliderDown())
            QTest.mouseClick(slider,Qt.MouseButton.LeftButton,pos=point(0));self.assertEqual(slider.value(),0)
            QTest.mouseClick(slider,Qt.MouseButton.LeftButton,pos=point(1));self.assertEqual(slider.value(),24000)
            slider.setEnabled(False);QTest.mouseClick(slider,Qt.MouseButton.LeftButton,pos=point(.3));self.assertEqual(slider.value(),24000)
        finally:slider.close();slider.deleteLater();QTest.qWait(30)

    def test_player_seek_click_while_paused_and_playing(self):
        player=VideoPlayer();player.show();QTest.qWait(20);player.resize(900,500);QTest.qWait(20);player.audio.setMuted(True)
        try:
            player.open_video(str((Path(__file__).parent/'fixtures/speech-test.mp4').resolve()))
            until=time.monotonic()+8
            while not player.ready and time.monotonic()<until:QTest.qWait(20)
            self.assertTrue(player.ready)
            def click(f):QTest.mouseClick(player.seek,Qt.MouseButton.LeftButton,pos=QPoint(round(player.seek.width()*f),player.seek.height()//2))
            click(.7);self.assertAlmostEqual(player.timeline_position(),player.timeline_duration()*.7,delta=200);self.assertFalse(player._playing)
            player.toggle_play();click(.3);self.assertTrue(player._playing)
            self.assertAlmostEqual(player.timeline_position(),player.timeline_duration()*.3,delta=200)
            before=player.timeline_position();QTest.qWait(150);self.assertGreater(player.timeline_position(),before)
        finally:player.shutdown();player.close();player.deleteLater();QTest.qWait(50)
