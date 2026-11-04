import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QMessageBox
from app.core.project import Project
from app.storage.project_store import load_project, save_project
from app.ui.main_window import MainWindow


class StoreTests(unittest.TestCase):
    def test_unicode_roundtrip_relative_and_missing_paths(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            video = str(root / "없는 영상.mp4")
            path = root / "프로젝트.avsp"
            project = Project("한글 프로젝트", [video], video)
            save_project(project, path)
            self.assertEqual(load_project(path), project)
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(raw["media_paths"], ["없는 영상.mp4"])
            save_project(Project(), path)
            self.assertEqual(load_project(path), Project())

    def test_bad_schema_and_future_version_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.avsp"
            for data in ("not json", "[]", '{"format":"ai-video-studio","version":99}',
                         '{"format":"ai-video-studio","version":1,"name":"OK","media_paths":[5]}',
                         '{"format":"ai-video-studio","version":1,"name":"OK","media_paths":[],"active_path":"x.mp4"}'):
                path.write_text(data, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_project(path)

    def test_legacy_project_and_invalid_aliases(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "legacy.avsp"
            media = str(Path(folder) / "one.mp4")
            save_project(Project("legacy", [media], media), path)
            data = json.loads(path.read_text(encoding="utf-8"))
            data.pop("media_names")
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(load_project(path).media_names, {})
            for names in ({"one.mp4": ""}, {"one.mp4": "a\nb"}, {"one.mp4": 3}, {"other.mp4": "이름"}, []):
                data["media_names"] = names
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_project(path)

    def test_failed_replace_keeps_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "work.avsp"
            save_project(Project("원래 프로젝트"), path)
            before = path.read_bytes()
            with patch("app.storage.project_store.os.replace", side_effect=OSError("disk unavailable")):
                with self.assertRaises(ValueError):
                    save_project(Project("변경"), path)
            self.assertEqual(before, path.read_bytes())
            self.assertEqual(list(Path(folder).glob(".avs-*.tmp")), [])
            with self.assertRaises(ValueError):
                save_project(Project(), Path(folder) / "original.mp4")


class ProjectUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow()

    def tearDown(self):
        for doc in self.window.documents:
            doc["dirty"] = False
        self.window.dirty = False
        self.window.project_name.setText(self.window.project.name)
        self.window.close()

    def test_save_open_missing_relink_and_save_again(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = str(root / "moved.mp4")
            project_path = root / "saved.avsp"
            save_project(Project("복원할 이름", [old], old), project_path)
            self.assertTrue(self.window.open_project_path(project_path))
            self.assertEqual(self.window.project_name.text(), "복원할 이름")
            self.assertIn("찾을 수 없음", self.window.media.listing.item(0).text())
            self.assertFalse(self.window.dirty)
            fixture = Path(__file__).parent / "fixtures" / "테스트 영상.mp4"
            self.assertTrue(self.window.media.replace_selected(fixture))
            self.assertTrue(self.window.dirty)
            self.assertTrue(self.window.save_current())
            saved = load_project(project_path)
            self.assertEqual(saved.media_paths, [str(fixture.resolve())])
            self.assertEqual(saved.active_path, str(fixture.resolve()))
            self.assertFalse(self.window.dirty)
            self.window.new_project()
            self.assertEqual(self.window.media.listing.count(), 0)
            self.assertIsNone(self.window.project_path)
            self.assertTrue(self.window.open_project_path(project_path))
            from PySide6.QtTest import QTest
            import time
            deadline = time.monotonic() + 8
            while not self.window.preview.ready and time.monotonic() < deadline:
                QTest.qWait(30)
            self.assertTrue(self.window.preview.ready)
            self.assertFalse(self.window.dirty)
            self.assertEqual(self.window.media.selected_path(), str(fixture.resolve()))

    def test_open_preserves_dirty_project_and_failed_load_keeps_active(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'other.avsp'
            save_project(Project('다른 프로젝트'), path)
            self.window.project_name.setText('작업 중')
            self.window.rename_project()
            first=self.window.active_document_id
            with patch.object(QMessageBox,'question',side_effect=AssertionError('No discard on open')):
                self.assertTrue(self.window.open_project_path(path))
            self.assertEqual(len(self.window.documents),2)
            self.assertTrue(self.window.activate_document(first))
            with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel):
                self.assertFalse(self.window.close())
            self.assertEqual(self.window.project.name,'작업 중')
            bad=Path(folder)/'bad.avsp';bad.write_text('broken',encoding='utf-8')
            with patch.object(QMessageBox,'warning'):
                self.assertFalse(self.window.open_project_path(bad))
            self.assertEqual(self.window.project.name,'작업 중')
            self.assertTrue(self.window.dirty)

    def test_remove_from_list_preserves_original_and_saved_state(self):
        fixture = (Path(__file__).parent / "fixtures" / "테스트 영상.mp4").resolve()
        other = (fixture.parent / "테스트 영상.mov").resolve()
        import hashlib
        before = hashlib.sha256(fixture.read_bytes()).digest()
        self.window.media.restore([str(fixture), str(other)], str(fixture))
        self.window.media.remove_button.click()
        self.assertEqual(self.window.media.paths(), [str(other)])
        self.assertEqual(self.window.project.active_path, str(other))
        self.assertTrue(self.window.dirty)
        self.assertEqual(before, hashlib.sha256(fixture.read_bytes()).digest())
        self.window.media.remove_button.click()
        self.assertEqual(self.window.media.paths(), [])
        self.assertIsNone(self.window.project.active_path)
        self.assertTrue(self.window.preview.player.source().isEmpty())
        self.assertFalse(self.window.preview.play_button.isEnabled())
        self.assertFalse(self.window.media.remove_button.isEnabled())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "removed.avsp"
            self.assertTrue(self.window.save_current(path=path))
            self.assertEqual(load_project(path).media_paths, [])
            self.assertTrue(self.window.open_project_path(path))
            self.assertEqual(self.window.media.listing.count(), 0)

    def test_display_name_persists_without_changing_original_and_cancels(self):
        from PySide6.QtWidgets import QInputDialog
        import hashlib
        fixture = (Path(__file__).parent / "fixtures" / "테스트 영상.mp4").resolve()
        original = hashlib.sha256(fixture.read_bytes()).digest()
        self.window.media.restore([str(fixture)], str(fixture))
        self.assertTrue(self.window.media.rename_button.isEnabled())
        self.assertTrue(self.window.media.rename_selected("  인트로 영상  "))
        self.assertEqual(self.window.media.listing.item(0).text(), "인트로 영상")
        self.assertEqual(self.window.media.selected_path(), str(fixture))
        self.assertTrue(self.window.dirty)
        with patch.object(QInputDialog, "getText", return_value=("취소한 이름", False)):
            self.window.media.rename_dialog()
        self.assertEqual(self.window.media.listing.item(0).text(), "인트로 영상")
        self.assertFalse(self.window.media.rename_selected("   "))
        self.assertFalse(self.window.media.rename_selected("a" * 121))
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).digest(), original)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "named.avsp"
            self.assertTrue(self.window.save_current(path=path))
            self.assertEqual(load_project(path).media_names, {str(fixture): "인트로 영상"})
            self.assertTrue(self.window.open_project_path(path))
            self.assertEqual(self.window.media.listing.item(0).text(), "인트로 영상")
            self.assertFalse(self.window.dirty)

    def test_alias_survives_relink_and_is_removed_with_item(self):
        fixture = (Path(__file__).parent / "fixtures" / "테스트 영상.mp4").resolve()
        missing = str(fixture.parent / "missing.mp4")
        self.window.media.restore([missing], missing, {missing: "장면 A"})
        self.assertIn("장면 A", self.window.media.listing.item(0).text())
        self.assertTrue(self.window.media.replace_selected(fixture))
        self.assertEqual(self.window.media.listing.item(0).text(), "장면 A")
        self.assertEqual(self.window.media.names(), {str(fixture): "장면 A"})
        self.window.media.remove_selected()
        self.assertEqual(self.window.media.names(), {})
        self.assertFalse(self.window.media.rename_button.isEnabled())

    def test_save_failure_retains_dirty_and_path(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "saved.avsp"
            self.window.project_name.setText("작업")
            self.window.rename_project()
            with patch("app.ui.main_window.save_project", side_effect=ValueError("permission denied")), patch.object(QMessageBox, "warning"):
                self.assertFalse(self.window.save_current(path=path))
            self.assertIsNone(self.window.project_path)
            self.assertTrue(self.window.dirty)


if __name__ == "__main__":
    unittest.main()
