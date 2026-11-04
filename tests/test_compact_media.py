import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication,QLabel
from app.ui.media_panel import MediaPanel

SOURCE=str((Path(__file__).parent/'fixtures'/'테스트 영상.mp4').resolve())
OTHER=str(Path(SOURCE).with_suffix('.mov'))
MISSING=str(Path(SOURCE).with_name('찾을수없는영상.mp4'))

class CompactMediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self): self.panel=MediaPanel(); self.panel.show(); self.app.processEvents()
    def tearDown(self): self.panel.close(); self.panel.deleteLater(); self.app.processEvents()
    def test_count_and_normal_file_controls(self):
        p=self.panel
        self.assertEqual(p.count_label.text(),'영상 0개')
        self.assertTrue(p.relink_button.isHidden())
        p.restore([SOURCE,OTHER],SOURCE)
        self.assertEqual(p.count_label.text(),'영상 2개')
        self.assertTrue(p.relink_button.isHidden())
        p.remove_selected()
        self.assertEqual(p.count_label.text(),'영상 1개')
        p.remove_selected()
        self.assertEqual(p.count_label.text(),'영상 0개')
        self.assertTrue(p.relink_button.isHidden())
        self.assertFalse(any('원본 보존' in label.text() for label in p.findChildren(QLabel)))
    def test_file_finder_only_for_missing_selected_source(self):
        p=self.panel
        p.restore([MISSING,SOURCE],MISSING)
        self.assertTrue(p.relink_button.isVisible())
        self.assertEqual(p.relink_button.text(),'파일 찾기')
        p.listing.setCurrentRow(1)
        self.assertTrue(p.relink_button.isHidden())
        p.restore([MISSING],MISSING, {MISSING:'내 영상'})
        self.assertTrue(p.replace_selected(OTHER))
        self.assertTrue(p.relink_button.isHidden())
        self.assertEqual(p.count_label.text(),'영상 1개')
        self.assertEqual(p.display_name(OTHER),'내 영상')

if __name__=='__main__': unittest.main()
