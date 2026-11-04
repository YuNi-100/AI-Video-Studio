import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtCore import Qt, Signal
from app.features.silence.model import candidates_from_log, retained_ranges
from app.ui.silence_dialog import SilenceDialog, compact_time


class FakePreview(QWidget):
    timelinePositionChanged = Signal(int)
    _playing = False
    def open_video(self, source): pass
    def shutdown(self): pass
    def seek_timeline(self, value): self.position = value
    def toggle_play(self): self._playing = not self._playing


class CutModelTests(unittest.TestCase):
    def test_compact_time(self):
        self.assertEqual(compact_time(241.968), '04:01.97')
        self.assertEqual(compact_time(59.999), '01:00.00')
        self.assertEqual(compact_time(3600), '01:00:00.00')
    def test_boundaries_and_padding(self):
        self.assertEqual(candidates_from_log('silence_start: 0\nsilence_end: 2\nsilence_start: 4', 6),[(.15,1.85),(4.15,5.85)])
    def test_merge_and_complement(self):
        self.assertEqual(retained_ranges(10,[(2,4),(3,5),(7,10)]),[(0,2),(5,7)])
    def test_invalid_and_all_cut(self):
        for cuts in ([(0,10)],[(2,11)],[(float('nan'),3)]):
            with self.assertRaises(ValueError):
                retained_ranges(10,cuts)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class CutIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.temp=tempfile.TemporaryDirectory()
        cls.source=Path(cls.temp.name)/'원본 영상.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=25:duration=6',
            '-f','lavfi','-i',"aevalsrc=if(between(t\\,2\\,4)\\,0\\,0.3*sin(2*PI*440*t)):s=48000:d=6",
            '-c:v','libx264','-c:a','aac','-shortest',str(cls.source)],check=True)
        cls.digest=hashlib.sha256(cls.source.read_bytes()).digest()
    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()
    def setUp(self):
        with patch("app.ui.silence_dialog.VideoPlayer", FakePreview):
            self.dialog=SilenceDialog(self.source)
    def tearDown(self):
        self.dialog.close()
        self.app.processEvents()
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).digest(), self.digest)
    def wait(self):
        deadline=time.monotonic()+30
        while self.dialog.process and time.monotonic()<deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertIsNone(self.dialog.process, self.dialog.status.text())
    def detect(self):
        self.dialog.start_probe()
        self.wait()
        self.assertEqual(len(self.dialog.candidates),1,self.dialog.status.text())
    def test_detect_defaults_and_apply_without_file_output(self):
        self.detect()
        start,end=self.dialog.candidates[0]
        self.assertAlmostEqual(start,2.15,delta=.05)
        self.assertAlmostEqual(end,3.85,delta=.05)
        self.assertEqual(self.dialog.selected_cuts(),[])
        self.assertFalse(self.dialog.export.isEnabled())
        self.dialog.table.item(0,0).setCheckState(Qt.CheckState.Checked)
        with patch('app.ui.silence_dialog.QFileDialog.getSaveFileName',side_effect=AssertionError('No file output')):
            self.dialog.export.click()
        self.assertEqual(self.dialog.applied_ranges,retained_ranges(self.dialog.duration,[(start,end)]))
        self.assertEqual(list(Path(self.temp.name).iterdir()),[self.source])
    def test_click_range_seeks_without_selecting_cut(self):
        from PySide6.QtTest import QTest
        self.detect()
        self.dialog.show()
        self.app.processEvents()
        self.dialog.preview._playing = True
        self.dialog.review_end = 9999
        item = self.dialog.table.item(0,1)
        self.assertIn('00:02.',item.text())
        QTest.mouseClick(self.dialog.table.viewport(), Qt.MouseButton.LeftButton,
                        pos=self.dialog.table.visualItemRect(item).center())
        self.assertEqual(self.dialog.preview.position,round(self.dialog.candidates[0][0]*1000))
        self.assertFalse(self.dialog.preview._playing)
        self.assertIsNone(self.dialog.review_end)
        self.assertEqual(self.dialog.selected_cuts(),[])
    def test_unselected_apply_does_not_create_sequence(self):
        self.detect()
        self.dialog.apply_sequence()
        self.assertIsNone(self.dialog.applied_ranges)
    def test_cancel_analysis(self):
        self.dialog.start_probe()
        self.dialog.cancel_work()
        self.wait()
        self.assertIn('취소',self.dialog.status.text())
    def test_escape_cancels_job(self):
        self.dialog.start_probe()
        self.dialog.reject()
        self.assertIsNone(self.dialog.process)
    def test_source_change_rejected(self):
        self.dialog.stamp=Path(__file__).stat()
        self.dialog.start_probe()
        self.assertIsNone(self.dialog.process)
        self.assertIn('변경',self.dialog.status.text())

if __name__=='__main__':
    unittest.main()
