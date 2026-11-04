import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import time
import unittest
import tempfile
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtMultimedia import QMediaPlayer
from app.core.media import validate_video, timecode
from app.ui.main_window import MainWindow


class MediaValidationTests(unittest.TestCase):
    def test_reject_missing_empty_and_wrong_type(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "비어 있음.mp4"
            p.touch()
            for path in (p, p.with_name("missing.mov"), p.with_suffix(".txt")):
                with self.assertRaises(ValueError):
                    validate_video(path)
        self.assertEqual(timecode(3661000), "01:01:01")

    def test_duplicate_and_cancel_import(self):
        app = QApplication.instance() or QApplication([])
        window = MainWindow()
        with tempfile.TemporaryDirectory() as folder:
            # Library-level import accepts a local file; decoding verifies its contents separately.
            source = Path(folder) / "invalid.mp4"
            source.write_bytes(b"not a video")
            window.media.add_files([])
            self.assertEqual(window.media.listing.count(), 0)
            window.media.add_files([source, source])
            self.assertEqual(window.media.listing.count(), 1)
            self.assertTrue(window.media.import_button.isEnabled())
        window.dirty = False
        window.close()


FIXTURES = Path(os.environ.get("STUDIO_TEST_MEDIA_DIR", Path(__file__).parent / "fixtures"))

@unittest.skipUnless((FIXTURES / "테스트 영상.mp4").exists(), "Decoder fixtures unavailable")
class DecoderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.preview = self.window.preview
        self.preview.audio.setMuted(True)

    def tearDown(self):
        self.window.dirty = False
        self.window.project_name.setText(self.window.project.name)
        self.window.close()
        QTest.qWait(50)

    def wait_for(self, predicate, timeout=8000):
        deadline = time.monotonic() + timeout / 1000
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(30)
        self.assertTrue(predicate(), self.preview.status.text())

    def test_mp4_mov_frames_controls_switch_and_original_preserved(self):
        import hashlib
        folder = FIXTURES
        for suffix in ("mp4", "mov"):
            path = folder / f"테스트 영상.{suffix}"
            before = hashlib.sha256(path.read_bytes()).digest()
            frames = QSignalSpy(self.preview.video.videoSink().videoFrameChanged)
            self.window.media.add_files([path])
            self.wait_for(lambda: self.preview.ready)
            self.assertGreater(self.preview.player.duration(), 2000)
            self.assertTrue(self.preview.play_button.isEnabled())
            self.preview.play_button.click()
            self.wait_for(lambda: self.preview.player.position() > 150)
            self.wait_for(lambda: frames.count() > 0)
            self.preview.play_button.click()
            self.assertEqual(self.preview.player.playbackState(), QMediaPlayer.PlaybackState.PausedState)
            self.preview.seek.sliderMoved.emit(1500)
            self.wait_for(lambda: abs(self.preview.player.position() - 1500) < 250)
            self.preview.volume.setValue(25)
            self.assertAlmostEqual(self.preview.audio.volume(), .25, places=2)
            self.preview.stop_button.click()
            self.assertEqual(self.preview.player.position(), 0)
            self.assertEqual(hashlib.sha256(path.read_bytes()).digest(), before)
        self.assertEqual(self.window.media.listing.count(), 2)

    def test_corrupt_file_disables_playback_and_recovers(self):
        failed = QSignalSpy(self.preview.failed)
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "broken.mp4"
            source.write_bytes(b"broken media container")
            self.window.open_media(source)
            self.wait_for(lambda: failed.count() > 0)
            self.assertFalse(self.preview.play_button.isEnabled())
            self.assertFalse(self.preview.seek.isEnabled())
            self.window.open_media(FIXTURES / "테스트 영상.mp4")
            self.wait_for(lambda: self.preview.ready)
            self.assertTrue(self.preview.play_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
