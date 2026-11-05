import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow
from app.features.silence.sequence import validate_sequence,sequence_clips

SOURCE=str((Path(__file__).parent/'fixtures/speech-test.mp4').resolve())


class ActiveEditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.w=MainWindow();self.w.show();self.w.activateWindow();self.w.preview.audio.setMuted(True)
        self.w.media.add_files([SOURCE])
        end=time.monotonic()+8
        while not self.w.preview.ready and time.monotonic()<end:QTest.qWait(20)
        self.assertTrue(self.w.preview.ready)
        self.w.project.edit_sequences=[validate_sequence(dict(id=key,name=name,source=SOURCE,duration=7.188,ranges=ranges))
            for key,name,ranges in [('a','편집본 1',[[0,1]]),('b','편집본 2',[[2,3],[4,5]])]]
        self.w.mark_dirty();self.w.open_edit_sequence('a')

    def tearDown(self):
        self.w.dirty=False
        for d in self.w.documents:d['dirty']=False
        self.w.close();QTest.qWait(20)

    def item(self,key):
        tree=self.w.timeline.sequence_tree
        return next(r for r in tree.findItems('',Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive)
            if r.data(0,Qt.ItemDataRole.UserRole)==('sequence',self.w.active_document_id,key))

    def tab(self,index):
        tabs=self.w.timeline.sequence_tabs
        QTest.mouseClick(tabs,Qt.MouseButton.LeftButton,pos=tabs.tabRect(index).center())

    def click_item(self,key,mod=Qt.KeyboardModifier.NoModifier):
        tree=self.w.timeline.sequence_tree
        QTest.mouseClick(tree.viewport(),Qt.MouseButton.LeftButton,mod,pos=tree.visualItemRect(self.item(key)).center())

    def assert_active(self,key,index,cuts):
        w=self.w
        self.assertEqual(w.active_edit_id,key)
        self.assertEqual(w.timeline.sequence_tabs.currentIndex(),index)
        self.assertEqual([r.data(0,Qt.ItemDataRole.UserRole)[2] for r in w.timeline.sequence_tree.selectedItems()],[key])
        self.assertEqual(sum(b[0]=='video' for b in w.timeline.canvas.blocks),cuts)
        self.assertIn('편집본 '+str(index),w.timeline.current_edit.text())
        self.assertTrue(self.item(key).font(0).bold())

    def test_tabs_and_list_switch_same_timeline_and_selection(self):
        self.tab(2);self.assert_active('b',2,2)
        self.assertFalse(self.item('a').font(0).bold())
        self.tab(1);self.assert_active('a',1,1)
        self.click_item('b');self.assert_active('b',2,2)
        self.click_item('a');self.assert_active('a',1,1)

    def test_paste_and_both_delete_scopes_use_expected_edit(self):
        w=self.w;c=w.timeline.canvas
        QTest.mouseClick(c,Qt.MouseButton.LeftButton,pos=QPoint(110,47))
        c.selected_clip=0;c.selected_keys={0,1}
        QTest.keyClick(c,Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier)
        self.tab(2)
        QTest.mouseClick(c,Qt.MouseButton.LeftButton,pos=QPoint(110,47))
        w.preview.seek_timeline(2000)
        QTest.keyClick(c,Qt.Key.Key_V,Qt.KeyboardModifier.ControlModifier)
        self.assert_active('b',2,3)
        self.assertEqual(len(sequence_clips(w.project.edit_sequences[0])),2)
        c.selected_clip=4;c.selected_keys={4,5};c.selected_subtitles=set()
        QTest.keyClick(c,Qt.Key.Key_Delete)
        self.assert_active('b',2,2)
        tree=w.timeline.sequence_tree;tree.setFocus()
        QTest.keyClick(tree,Qt.Key.Key_Delete)
        self.assertEqual([s['id'] for s in w.project.edit_sequences],['a'])
        self.assertEqual(len(sequence_clips(w.project.edit_sequences[0])),2)

    def test_original_tab_clears_edit_selection(self):
        self.tab(0)
        self.assertIsNone(self.w.active_sequence())
        self.assertEqual(self.w.timeline.sequence_tree.selectedItems(),[])
        self.assertIn('원본 보기',self.w.timeline.current_edit.text())

    def test_ctrl_multi_selection_does_not_change_opened_edit(self):
        self.click_item('b',Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(self.w.timeline.sequence_tree.selectedItems()),2)
        self.assertEqual(self.w.active_edit_id,'a')
        self.tab(2);self.assert_active('b',2,2)
        self.click_item('a',Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(len(self.w.timeline.sequence_tree.selectedItems()),2)
        self.tab(2);self.assert_active('b',2,2)

    def test_cancelled_switch_restores_actual_selection(self):
        with patch.object(self.w,'resolve_subtitle_edit',return_value=False):
            self.click_item('b')
        self.assert_active('a',1,1)

    def test_missing_source_keeps_actual_timeline_and_selection(self):
        self.w.project.edit_sequences[1]['source']=str(Path(SOURCE).with_name('not-found.mp4'))
        self.click_item('b')
        self.assert_active('a',1,1)
        self.w.project.edit_sequences[1]['source']=SOURCE

    def test_tab_reveals_active_edit_inside_collapsed_folder(self):
        w=self.w
        w.project.edit_folders=[dict(id='folder',name='완성 편집',parent=None)]
        w.project.edit_locations['b']='folder';w.mark_dirty()
        folder=self.item('b').parent();folder.setExpanded(False)
        self.tab(2);self.assert_active('b',2,2)
        self.assertTrue(self.item('b').parent().isExpanded())
