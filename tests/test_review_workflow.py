import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import tempfile
import time
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication, QMessageBox
from app.features.subtitles.editing import edit_segment, active_text, review_reasons
from app.features.subtitles.export import make_srt, export_srt
from app.features.subtitles.model import validate_segments
from app.ui.main_window import MainWindow
from app.storage.project_store import load_project
from app.ui.theme import STYLE

ROWS = [{"start": 1., "end": 2., "text": "라겸 앞에 봐"}, {"start": 3., "end": 4., "text": "잘하고 있어"}]
SOURCE = str((Path(__file__).parent / "fixtures" / "speech-test.mp4").resolve())


class ReviewCoreTests(unittest.TestCase):
    def test_edit_reorders_validates_and_preserves_original(self):
        original = deepcopy(ROWS)
        result, index = edit_segment(ROWS, 0, 4.5, 5.5, "수정한 문장", 7)
        self.assertEqual(index, 1)
        self.assertTrue(result[index]["reviewed"])
        self.assertEqual(ROWS, original)
        for start, end, text in ((-1, 1, "x"), (1, 1, "x"), (1, 2, " "), (1, 8, "x")):
            with self.assertRaises(ValueError):
                edit_segment(ROWS, 0, start, end, text, 7)

    def test_caption_half_open_boundaries_and_overlap(self):
        self.assertEqual(active_text(ROWS, 999), "")
        self.assertEqual(active_text(ROWS, 1000), "라겸 앞에 봐")
        self.assertEqual(active_text(ROWS, 2000), "")
        self.assertEqual(active_text(ROWS, 3000), "잘하고 있어")
        overlap = [ROWS[0], {"start": 1.5, "end": 2.5, "text": "겹침"}]
        self.assertIn("\n", active_text(overlap, 1600))

    def test_review_flags_do_not_replace_or_delete_text(self):
        rows = [{"start": i*2., "end": i*2.+1, "text": "나와라 나와"} for i in range(3)]
        rows += [{"start": 10., "end": 25., "text": "Episode МУЗЫКА"}]
        before = deepcopy(rows)
        flags = review_reasons(rows, "ko")
        self.assertTrue(all("연속 반복" in f for f in flags[:3]))
        self.assertIn("외국어 확인", flags[3])
        self.assertIn("긴 표시 시간", flags[3])
        self.assertEqual(rows, before)
        self.assertNotIn("외국어 확인", review_reasons(rows, "en")[3])

    def test_srt_standard_format_rounding_unicode_and_multiline(self):
        text = make_srt([{"start": 3599.9996, "end": 3601.123, "text": "라겸\n\n경희"}])
        self.assertEqual(text, "1\n01:00:00,000 --> 01:00:01,123\n라겸\n경희\n")
        with self.assertRaises(ValueError):
            make_srt([])

    def test_srt_atomic_failure_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "caption.srt"
            export_srt(ROWS, path)
            before = path.read_bytes()
            self.assertTrue(before.startswith(b"\xef\xbb\xbf"))
            with patch("app.features.subtitles.export.os.replace", side_effect=OSError("unavailable")):
                with self.assertRaises(ValueError):
                    export_srt(ROWS[:1], path)
            self.assertEqual(before, path.read_bytes())
            self.assertEqual(list(Path(folder).glob(".avs-srt-*")), [])


class ReviewUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")
        cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.window = MainWindow()
        self.window.show()
        self.window.media.restore([SOURCE], SOURCE)
        self.window.project.subtitles[SOURCE] = deepcopy(ROWS)
        self.window.open_media(SOURCE)
        self.window.preview.audio.setMuted(True)
        deadline=time.monotonic()+8
        while not self.window.preview.ready and time.monotonic()<deadline:QTest.qWait(20)
        self.assertTrue(self.window.preview.ready)
        self.window.create_edit_sequence(SOURCE,[(0,7)],7.188)
        self.window.select_subtitle(0)
        self.editor = self.window.subtitle_panel.editor
        self.app.processEvents()

    def tearDown(self):
        self.editor.set_selection(-1)
        self.window.subtitle_job.shutdown()
        self.window.dirty = False
        self.window.project_name.setText(self.window.project.name)
        self.window.close()

    def test_edit_add_remove_undo_and_export_saved_project(self):
        self.editor.text.setPlainText("라겸, 앞에 봐!")
        self.editor.start.setValue(.5)
        self.assertTrue(self.window.apply_subtitle_edit())
        rows = self.window.active_sequence()["timeline_captions"]
        self.assertEqual(rows[0]["text"], "라겸, 앞에 봐!")
        self.assertTrue(rows[0]["reviewed"])
        self.window.remove_subtitle()
        self.assertEqual(len(self.window.active_sequence()["timeline_captions"]), 1)
        self.window.undo_subtitle()
        self.assertEqual(len(self.window.active_sequence()["timeline_captions"]), 2)
        self.window.add_subtitle()
        self.assertEqual(len(self.window.active_sequence()["timeline_captions"]), 3)
        self.window.undo_subtitle()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "edited.avsp"
            self.window.project.subtitle_runs[SOURCE] = {"model": "large-v3-turbo", "language": "ko", "skip_silence": False}
            self.assertTrue(self.window.save_current(path=path))
            self.assertEqual(load_project(path).subtitle_runs[SOURCE]["model"], "large-v3-turbo")
            self.assertTrue(load_project(path).edit_sequences[0]["timeline_captions"][0]["reviewed"])
            self.assertEqual(load_project(path).edit_sequences[0]["timeline_captions"][0]["text"], "라겸, 앞에 봐!")
            target = Path(folder) / "edited.srt"
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                self.assertTrue(self.window.export_current_subtitles(target))
            self.assertIn("00:00:00,500 --> 00:00:02,000", target.read_text(encoding="utf-8-sig"))

    def test_invalid_edit_and_cancel_preserve_pending_buffer(self):
        self.editor.end.setValue(0)
        with patch.object(QMessageBox, "warning"):
            self.assertFalse(self.window.apply_subtitle_edit())
        self.assertEqual(self.window.project.subtitles[SOURCE], ROWS)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(self.window.close())
            self.window.media.remove_selected()
            self.assertEqual(self.window.media.listing.count(), 1)
        self.assertTrue(self.editor.pending)

    def test_pending_cancel_keeps_row_source_and_buffer(self):
        other = str((Path(SOURCE).parent / "테스트 영상.mp4").resolve())
        self.window.media.restore([SOURCE, other], SOURCE)
        self.editor.text.setPlainText("아직 적용하지 않은 수정")
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            self.editor.table.setCurrentCell(1, 0)
            self.assertEqual(self.editor.selected_index, 0)
            self.assertEqual(self.editor.table.currentRow(), 0)
            self.window.media.listing.setCurrentRow(1)
            self.assertEqual(self.window.media.selected_path(), other)
            self.assertEqual(self.editor.text.toPlainText(), "아직 적용하지 않은 수정")
        self.assertEqual(self.window.project.subtitles[SOURCE], ROWS)

    def test_timeline_selection_seek_and_zoom(self):
        canvas = self.window.timeline.canvas
        self.window.timeline.set_source(10000, ROWS, "test")
        selected = QSignalSpy(canvas.clip_selected)
        x = round(95 + (canvas.width()-107)*.15)
        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, 90))
        self.assertEqual(selected.count(), 1)
        seek = QSignalSpy(canvas.clip_seek_requested)
        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=QPoint(x, 45))
        self.assertEqual(seek.count(), 1)
        self.window.timeline.zoom.setValue(200)
        self.assertGreater(self.window.timeline.scroll.maximum(), 0)

    def test_real_video_overlay_on_seek_and_toggle(self):
        self.window.open_media(SOURCE)
        self.window.preview.audio.setMuted(True)
        deadline = time.monotonic()+8
        while not self.window.preview.ready and time.monotonic() < deadline:
            QTest.qWait(25)
        self.assertTrue(self.window.preview.ready)
        self.window.preview.player.setPosition(1500)
        deadline = time.monotonic()+5
        while not self.window.preview.video.caption.isVisible() and time.monotonic() < deadline:
            QTest.qWait(25)
        self.assertEqual(self.window.preview.video.caption.toPlainText(), "라겸 앞에 봐")
        self.assertTrue(self.window.preview.video.caption.isVisible())
        self.editor.overlay.setChecked(False)
        self.assertFalse(self.window.preview.video.caption.isVisible())
        self.editor.overlay.setChecked(True)
        self.assertTrue(self.window.preview.video.caption.isVisible())
        self.window.seek_transport(2000)
        self.assertFalse(self.window.preview.video.caption.isVisible())


if __name__ == "__main__":
    unittest.main()
