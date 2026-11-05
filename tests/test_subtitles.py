from copy import deepcopy
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication, QMessageBox
from app.core.project import Project
from app.features.subtitles.model import validate_segments, validate_hotwords
from app.features.subtitles.worker import transcribe
from app.storage.project_store import load_project, save_project
from app.ui.main_window import MainWindow

SEGMENTS = [{"start": 0.1, "end": 1.5, "text": "테스트 자막"}]
FIXTURE = Path(__file__).parent / "fixtures" / "speech-test.mp4"


class SubtitleUnitTests(unittest.TestCase):
    def test_timestamps_and_text_validation(self):
        self.assertEqual(validate_segments(SEGMENTS), SEGMENTS)
        for data in ([{"start": 2, "end": 1, "text": "x"}],
                     [{"start": float("nan"), "end": 1, "text": "x"}],
                     [{"start": 0, "end": 1, "text": ""}],
                     [{"start": 0, "end": float("inf"), "text": "x"}]):
            with self.assertRaises(ValueError):
                validate_segments(data)

    def test_worker_emits_only_actual_segments_with_injected_backend(self):
        events = []
        observed = {}
        class FakeModel:
            def __init__(self, *args, **kwargs):
                pass
            def transcribe(self, *args, **kwargs):
                observed.update(kwargs)
                return iter([SimpleNamespace(start=.1, end=1.5, text="테스트 자막")]), SimpleNamespace(language="ko", duration=1.0)
        transcribe(FIXTURE, "tiny", "ko", Path("unused"), events.append, FakeModel, hotwords="라겸, 경희")
        self.assertEqual(events[-1]["segments"], [{"start": .1, "end": 1., "text": "테스트 자막"}])
        self.assertEqual(events[-2]["type"], "progress")
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(observed["hotwords"], "라겸, 경희")
        self.assertFalse(observed["vad_filter"])
        transcribe(FIXTURE, "tiny", "ko", Path("unused"), events.append, FakeModel, skip_silence=True)
        self.assertTrue(observed["vad_filter"])

    def test_hotwords_validation_and_project_roundtrip(self):
        self.assertEqual(validate_hotwords(" 라겸, 경희 "), "라겸, 경희")
        for value in ("x" * 401, "a\nb", None):
            with self.assertRaises(ValueError):
                validate_hotwords(value)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "terms.avsp"
            project = Project(subtitle_terms="라겸, 경희")
            save_project(project, path)
            self.assertEqual(load_project(path).subtitle_terms, "라겸, 경희")

    def test_filter_setting_roundtrip_and_legacy_default(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "filter.avsp"
            save_project(Project(subtitle_skip_silence=True), path)
            self.assertTrue(load_project(path).subtitle_skip_silence)
            import json
            data = json.loads(path.read_text(encoding="utf-8"))
            data.pop("subtitle_skip_silence")
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertFalse(load_project(path).subtitle_skip_silence)
            data["subtitle_skip_silence"] = "true"
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_project(path)

    def test_subtitle_storage_roundtrip_and_legacy(self):
        source = str(FIXTURE.resolve())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "subtitles.avsp"
            project = Project("자막", [source], source, {}, {source: SEGMENTS})
            save_project(project, path)
            self.assertEqual(load_project(path), project)
            import json
            data = json.loads(path.read_text(encoding="utf-8"))
            data.pop("subtitles")
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(load_project(path).subtitles, {})


class SubtitleUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        self.window.subtitle_job.shutdown()
        self.window.dirty = False
        self.window.project_name.setText(self.window.project.name)
        self.window.close()

    def test_results_per_source_and_remove_cleanup(self):
        source = str(FIXTURE.resolve())
        other = str((FIXTURE.parent / "테스트 영상.mp4").resolve())
        self.window.media.restore([source, other], source)
        self.window.subtitles_ready(source, SEGMENTS)
        self.assertIn("테스트 자막", self.window.subtitle_panel.results.toPlainText())
        self.assertTrue(self.window.dirty)
        self.window.media.listing.setCurrentRow(1)
        self.assertEqual(self.window.subtitle_panel.results.toPlainText(), "")
        self.window.media.listing.setCurrentRow(0)
        self.assertIn("테스트 자막", self.window.subtitle_panel.results.toPlainText())
        self.window.media.remove_selected()
        self.assertNotIn(source, self.window.project.subtitles)

    def test_turbo_default_and_terms_restore(self):
        self.assertEqual(self.window.subtitle_panel.model.currentData(), "large-v3-turbo")
        self.assertFalse(self.window.subtitle_panel.skip_silence.isChecked())
        self.window.apply_project(Project(subtitle_terms="라겸, 경희"), None)
        self.assertEqual(self.window.subtitle_panel.terms.text(), "라겸, 경희")
        self.window.subtitle_panel.terms.textEdited.emit("라겸, 경희, 촬영")
        self.assertTrue(self.window.dirty)
        self.assertEqual(self.window.project.subtitle_terms, "라겸, 경희, 촬영")
        self.window.subtitle_panel.set_busy(True)
        self.assertFalse(self.window.subtitle_panel.terms.isEnabled())
        self.window.subtitle_panel.set_busy(False)

    def test_missing_dependency_and_failure_keep_results(self):
        source = str(FIXTURE.resolve())
        self.window.media.restore([source], source)
        self.window.project.subtitles[source] = SEGMENTS
        self.window.show_source_subtitles()
        self.window.subtitle_failed("test error")
        self.assertEqual(self.window.project.subtitles[source], SEGMENTS)
        with patch("app.ui.main_window.recognition_installed", return_value=False):
            self.window.update_subtitle_controls()
        self.assertFalse(self.window.subtitle_panel.generate.isEnabled())
        self.assertIn("패키지", self.window.subtitle_panel.status.text())


@unittest.skipUnless(os.environ.get("STUDIO_WHISPER_CACHE"), "Set STUDIO_WHISPER_CACHE for actual offline inference tests")
class RealRecognitionTests(unittest.TestCase):
    setUpClass = SubtitleUITests.__dict__["setUpClass"]
    setUp = SubtitleUITests.setUp
    tearDown = SubtitleUITests.tearDown

    def wait_for(self, predicate, timeout=90000):
        deadline = time.monotonic() + timeout / 1000
        while not predicate() and time.monotonic() < deadline:
            QTest.qWait(30)
        self.assertTrue(predicate(), self.window.subtitle_panel.status.text())

    def prepare(self):
        self.window.whisper_cache = Path(os.environ["STUDIO_WHISPER_CACHE"])
        self.window.media.add_files([FIXTURE])
        self.wait_for(lambda: self.window.preview.ready, 10000)
        self.window.create_edit_sequence(str(FIXTURE.resolve()),[(0,7)],7.188)
        self.window.update_subtitle_controls()
        self.assertTrue(self.window.subtitle_panel.generate.isEnabled())

    def test_real_job_ui_remains_responsive_and_saves(self):
        self.prepare()
        job = self.window.subtitle_job
        completed, failed = QSignalSpy(job.completed), QSignalSpy(job.failed)
        ticks = []
        timer = QTimer()
        timer.setInterval(30)
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start()
        self.window.subtitle_panel.terms.setText("studio, subtitles")
        self.window.generate_subtitles("tiny", "en")
        self.assertFalse(self.window.media.isEnabled())
        self.assertFalse(self.window.allow_project_switch())
        self.wait_for(lambda: not job.busy)
        timer.stop()
        self.assertEqual(failed.count(), 0, self.window.subtitle_panel.status.toolTip())
        self.assertEqual(completed.count(), 1)
        self.assertGreater(len(ticks), 5)
        source = str(FIXTURE.resolve())
        result = self.window.active_sequence()["timeline_captions"]
        self.assertGreater(len(result), 0)
        self.assertIn("subtitles", " ".join(s["text"] for s in result).lower())
        self.assertGreater(result[0]["end"], result[0]["start"])
        self.assertLessEqual(result[-1]["end"], self.window.preview.player.duration() / 1000 + .1)
        self.assertTrue(self.window.media.isEnabled())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "recognized.avsp"
            self.assertTrue(self.window.save_current(path=path))
            self.assertEqual(load_project(path).edit_sequences[0]["timeline_captions"], result)
            self.assertNotIn(source,load_project(path).subtitles)

    def test_no_speech_returns_empty_without_fake_results(self):
        source = FIXTURE.parent / "테스트 영상.mp4"
        # Match production isolation: keep inference native thread pools out of the UI process.
        import subprocess,sys,json
        completed = subprocess.run([sys.executable,"-m","app.features.subtitles.worker",
            "--source",str(source),"--model","tiny","--language","en",
            "--cache",os.environ["STUDIO_WHISPER_CACHE"]],
            capture_output=True,text=True,encoding="utf-8",timeout=90,
            env=dict(os.environ,PYTHONUTF8="1",PYTHONIOENCODING="utf-8"))
        self.assertEqual(completed.returncode,0,completed.stderr)
        events = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[-1]["segments"], [])

    def test_cancel_worker_preserves_previous_subtitles(self):
        self.prepare()
        source = str(FIXTURE.resolve())
        self.window.project.subtitles[source] = SEGMENTS
        self.window.commit_work_subtitles(SEGMENTS)
        before=deepcopy(self.window.active_sequence()["timeline_captions"])
        with patch("app.ui.main_window.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            self.window.generate_subtitles("tiny", "en")
        QTimer.singleShot(100, self.window.subtitle_job.cancel)
        self.wait_for(lambda: not self.window.subtitle_job.busy, 10000)
        self.assertEqual(self.window.project.subtitles[source], SEGMENTS)
        self.assertEqual(self.window.active_sequence()["timeline_captions"],before)
        self.assertTrue(self.window.media.isEnabled())


if __name__ == "__main__":
    unittest.main()
