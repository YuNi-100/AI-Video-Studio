import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QApplication,QInputDialog
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow
from app.ui.scene_search import SceneSearch
from app.features.scene_search import search_edits
from app.features.silence.sequence import sequence_clips,sequence_layout
from app.storage.project_store import save_project,load_project

SOURCE=str((Path(__file__).parent/'fixtures/speech-test.mp4').resolve())

class WorkspaceSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        from app.ui.theme import STYLE
        cls.app.setStyle('Fusion');cls.app.setStyleSheet(STYLE)

    def setUp(self):
        self.w=MainWindow();self.w.show();self.w.activateWindow();QTest.qWait(30)

    def tearDown(self):
        self.w.project_name.setText(self.w.project.name)
        for doc in self.w.documents:doc['dirty']=False
        self.w.dirty=False;self.w.close();QTest.qWait(10)

    def empty(self,name='모음'):
        with patch.object(QInputDialog,'getText',return_value=(name,True)):self.w.new_empty_edit()
        return self.w.active_sequence()

    def media_edit(self):
        w=self.w;w.media.add_files([SOURCE]);deadline=time.monotonic()+8
        while not w.preview.ready and time.monotonic()<deadline:QTest.qWait(20)
        self.assertTrue(w.preview.ready)
        w.project.subtitles[SOURCE]=[dict(start=2.2,end=2.5,text='대사 하나'),dict(start=2.6,end=2.9,text='대사 둘')]
        w.create_edit_sequence(SOURCE,[(2,3)],7.188)
        return w.active_sequence()

    def test_empty_without_media_save_reopen_and_undo(self):
        seq=self.empty();self.assertEqual(sequence_clips(seq),[])
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'empty.avsp';save_project(self.w.project,path)
            p=load_project(path);self.assertEqual(p.edit_sequences[0]['source'],'')
        self.w.change_project_history(False);self.assertEqual(self.w.project.edit_sequences,[])
        self.w.change_project_history(True);self.assertEqual(self.w.active_sequence()['name'],'모음')

    def test_paste_into_blank_after_reopen_keeps_captions(self):
        w=self.w;self.media_edit();c=w.timeline.canvas
        c.selected_keys={0,1};c.selected_clip=0;w.copy_timeline_sets()
        seq=self.empty();key=seq['id'];w.paste_timeline_sets();QTest.qWait(100)
        self.assertEqual(len(sequence_clips(w.active_sequence())),2)
        self.assertEqual(len(w.active_sequence()['timeline_captions']),2)
        self.assertEqual(w.active_sequence()['source'],SOURCE)
        self.assertIs(w.preview.stack.currentWidget(),w.preview.video)
        w.change_project_history(False);self.assertEqual(sequence_clips(w.active_sequence()),[])
        w.change_project_history(True);self.assertEqual(len(sequence_clips(w.active_sequence())),2)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'full.avsp';save_project(w.project,path);p=load_project(path)
            self.assertEqual(len(sequence_clips(next(s for s in p.edit_sequences if s['id']==key))),2)

    def test_filter_classify_delete_undo_and_roundtrip(self):
        w=self.w;seq=self.media_edit();key=seq['id'];d=SceneSearch(w);d.refresh()
        try:
            d.edit_filter.setCurrentIndex(d.edit_filter.findData(key));self.assertEqual(d.results.topLevelItemCount(),2)
            with patch.object(QInputDialog,'getText',return_value=('사용할 장면',True)):d.new_folder()
            d.results.topLevelItem(0).setCheckState(0,Qt.CheckState.Checked)
            before=sequence_layout(w.active_sequence())[1]
            with patch.object(QInputDialog,'getItem',return_value=('사용할 장면',True)):d.move_checked()
            self.assertEqual(sequence_layout(w.active_sequence())[1],before)
            folder=w.project.search_folders[0]['id'];d.folder_filter.setCurrentIndex(d.folder_filter.findData(folder))
            self.assertEqual(d.results.topLevelItemCount(),1)
            with tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/'folders.avsp';save_project(w.project,path);p=load_project(path)
                self.assertEqual(len([r for r in search_edits(p) if r['folder']==folder]),1)
            d.check_all(True);d.delete_checked();self.assertEqual(len(w.active_sequence()['timeline_captions']),1)
            w.change_project_history(False);d.refresh();self.assertEqual(len(w.active_sequence()['timeline_captions']),2)
            self.assertEqual(d.results.topLevelItemCount(),1)
            w.change_project_history(True);d.refresh();self.assertEqual(d.results.topLevelItemCount(),0)
        finally:d.close()

    def test_checked_tags_across_edits_and_dialog_save(self):
        w=self.w;first=self.media_edit();first['scene_tags']=[dict(name='골',start=.1,end=.3)]
        second=self.empty('두번째');second['scene_tags']=[dict(name='키퍼',start=.1,end=.3)]
        d=SceneSearch(w);d.show();d.activateWindow();QTest.qWait(30)
        try:
            d.kind.setCurrentIndex(2);self.assertEqual(d.results.topLevelItemCount(),2)
            d.check_all(True);d.delete_checked()
            self.assertEqual(search_edits(w.project,kind='tags'),[])
            d.results.setFocus();QTest.keyClick(d.results,Qt.Key.Key_Z,Qt.KeyboardModifier.ControlModifier)
            self.assertEqual(len(search_edits(w.project,kind='tags')),2)
            with patch.object(w,'save_current') as save:
                QTest.keyClick(d.results,Qt.Key.Key_S,Qt.KeyboardModifier.ControlModifier)
                self.assertEqual(save.call_count,1)
        finally:d.close()

    def test_child_filter_and_delete_update_parent_without_duplicates(self):
        w=self.w;parent=self.media_edit()
        child=next(s for s in w.project.edit_sequences if s.get('parent_id')==parent['id'])
        w.open_edit_sequence(child['id']);d=SceneSearch(w);d.refresh()
        try:
            self.assertEqual(len(search_edits(w.project)),2)
            d.edit_filter.setCurrentIndex(d.edit_filter.findData('@current'))
            self.assertEqual(d.results.topLevelItemCount(),2)
            with patch.object(QInputDialog,'getText',return_value=('하위 분류',True)):d.new_folder()
            d.results.topLevelItem(0).setCheckState(0,Qt.CheckState.Checked)
            with patch.object(QInputDialog,'getItem',return_value=('하위 분류',True)):d.move_checked()
            self.assertEqual(len([r for r in search_edits(w.project) if r['folder']]),1)
            d.delete_checked()
            self.assertEqual(len(next(s for s in w.project.edit_sequences if s['id']==parent['id'])['timeline_captions']),1)
            w.change_project_history(False);d.refresh();self.assertEqual(d.results.topLevelItemCount(),2)
        finally:d.close()

    def test_collect_two_sources_into_empty_edit(self):
        w=self.w;first=self.media_edit();c=w.timeline.canvas
        c.selected_keys={0,1};c.selected_clip=0;w.copy_timeline_sets()
        target=self.empty('완성본');key=target['id'];w.paste_timeline_sets()
        other=str((Path(__file__).parent/'fixtures/테스트 영상.mov').resolve())
        w.media.add_files([other]);w.project.subtitles[other]=[dict(start=.2,end=.5,text='다른 영상 대사')]
        w.create_edit_sequence(other,[(.1,.8)],3)
        c.selected_keys={0,1};c.selected_clip=0;w.copy_timeline_sets()
        w.open_edit_sequence(key)
        deadline=time.monotonic()+8
        while not w.preview.ready and time.monotonic()<deadline:QTest.qWait(20)
        w.seek_transport(1000);w.paste_timeline_sets()
        seq=w.active_sequence();clips=sequence_clips(seq)
        self.assertEqual({r.get('source',seq['source']) for r in clips},{SOURCE,other})
        self.assertEqual(sorted({r['at'] for r in clips}),[0,1])
        self.assertEqual(len(seq['timeline_captions']),3)
        self.assertEqual(len(w.project.subtitles[SOURCE]),2)
        self.assertEqual(len(next(s for s in w.project.edit_sequences if s['id']==first['id'])['timeline_captions']),2)

    def test_preview_click_keys_and_other_area_isolation(self):
        w=self.w;self.media_edit()
        QTest.mouseClick(w.preview.video.viewport(),Qt.MouseButton.LeftButton)
        self.assertTrue(w.playback_keys.preview_active);self.assertFalse(w.timeline_focus.active)
        with patch.object(w,'toggle_transport') as play,patch.object(w.preview.player,'isSeekable',return_value=True),patch.object(w,'transport_duration_value',return_value=20000),patch.object(w,'transport_position_value',return_value=8000),patch.object(w,'seek_transport') as seek:
            QTest.keyClick(QApplication.focusWidget(),Qt.Key.Key_Right);seek.assert_called_with(9000)
            QTest.keyClick(QApplication.focusWidget(),Qt.Key.Key_Left,Qt.KeyboardModifier.ShiftModifier);seek.assert_called_with(3000)
            QTest.keyClick(QApplication.focusWidget(),Qt.Key.Key_Space);self.assertEqual(play.call_count,1)
            QTest.mouseMove(w.media);self.assertTrue(w.playback_keys.preview_active)
            QTest.mouseClick(w.project_name,Qt.MouseButton.LeftButton);self.assertFalse(w.playback_keys.preview_active)
            QTest.keyClick(w.project_name,Qt.Key.Key_Space);self.assertEqual(play.call_count,1)

    def test_splitter_handles_can_move_both_directions(self):
        w=self.w;w.resize(1680,1000);QTest.qWait(40)
        for splitter in (w.workspace_horizontal,w.workspace_vertical):
            before=splitter.sizes();handle=splitter.handle(1)
            delta=70
            point=handle.rect().center()
            QTest.mousePress(handle,Qt.MouseButton.LeftButton,pos=point)
            QTest.mouseMove(handle,point+(QPoint(delta,0) if splitter.orientation()==Qt.Orientation.Horizontal else QPoint(0,delta)),delay=30)
            QTest.mouseRelease(handle,Qt.MouseButton.LeftButton)
            QTest.qWait(30)
            self.assertNotEqual(splitter.sizes(),before,(splitter.orientation(),before,splitter.minimumSizeHint()))

