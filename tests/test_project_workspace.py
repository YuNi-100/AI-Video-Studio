import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from copy import deepcopy
from pathlib import Path
import tempfile,time,unittest
from unittest.mock import patch
from PySide6.QtCore import Qt,QPointF,QPoint,QMimeData,QUrl
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow
from app.features.silence.sequence import sequence_clips,sequence_layout,insert_sources,validate_sequence
from app.storage.project_store import load_project,save_project
from app.core.project import Project

A=str((Path(__file__).parent/'fixtures/speech-test.mp4').resolve())
B=str((Path(__file__).parent/'fixtures/테스트 영상.mp4').resolve())


class MixedSequenceModelTests(unittest.TestCase):
    def test_insertion_splits_and_ripples_both_tracks(self):
        original=dict(id='one',name='원본',source=A,duration=7.188,ranges=[[0,4],[5,7]])
        result=insert_sources(original,[(B,3)],1500)
        clips=sequence_clips(result)
        for track in ('video','audio'):
            rows=sorted((c for c in clips if c['track']==track),key=lambda c:c['at'])
            self.assertEqual([r['at'] for r in rows],[0,1.5,4.5,7])
            self.assertEqual(rows[1]['source'],B)
            self.assertEqual(rows[2]['start'],1.5)
        self.assertEqual(sequence_layout(result)[2],9000)
        self.assertNotIn('clips',original)
    def test_mixed_portable_storage_and_invalid_reference(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);a=str(root/'a.mp4');b=str(root/'sub/b.mov')
            seq=insert_sources(dict(id='one',name='mix',source=a,duration=5,clips=[],ranges=[]),[(a,5),(b,9)],0)
            project=Project(media_paths=[a,b],active_path=a,edit_sequences=[seq])
            file=root/'mixed.avsp';save_project(project,file)
            self.assertEqual(load_project(file),project)
            self.assertIn('sub',file.read_text(encoding='utf-8'))
            project.media_paths=[a]
            with self.assertRaises(ValueError):save_project(project,file)
            bad=deepcopy(seq);bad['clips'][0]['end']=6
            with self.assertRaises(ValueError):validate_sequence(bad)


class WorkspaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.w=MainWindow();self.w.show();self.w.preview.audio.setMuted(True)
        self.w.media.add_files([A]);self.wait(lambda:self.w.preview.ready)
        self.first=self.w.active_document_id
    def tearDown(self):
        for d in self.w.documents:d['dirty']=False
        self.w.dirty=False;self.w.close();QTest.qWait(30)
    def wait(self,p):
        end=time.monotonic()+8
        while not p() and time.monotonic()<end:QTest.qWait(20)
        self.assertTrue(p())
    def item(self,tree,kind,uid,key=None):
        for item in tree.findItems('',Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive):
            d=item.data(0,Qt.ItemDataRole.UserRole)
            if d and d[0]==kind and d[1]==uid and (key is None or len(d)>2 and d[2]==key):return item
        self.fail('tree item missing')
    def drop(self,tree,item,paths,blank=False):
        if blank:
            tree.collapseAll()
            self.app.processEvents()
        pos=tree.viewport().rect().bottomRight()-QPoint(5,5) if blank else tree.visualItemRect(item).center()
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(p) for p in paths])
        enter=QDragEnterEvent(pos,Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(tree.viewport(),enter)
        self.assertTrue(enter.isAccepted())
        event=QDropEvent(QPointF(pos),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(tree.viewport(),event)
        self.assertTrue(event.isAccepted())
    def test_disclosure_click_toggles_without_switching_project(self):
        w=self.w;tree=w.media.project_tree
        w.new_organized_folder('library','자료 정리')
        root=tree.topLevelItem(0);point=tree.visualItemRect(root).topLeft()+QPoint(8,10)
        self.assertTrue(root.isExpanded())
        QTest.mouseClick(tree.viewport(),Qt.MouseButton.LeftButton,pos=point)
        self.assertFalse(root.isExpanded());self.assertTrue(root.text(0).startswith('▸'))
        w.mark_dirty();root=tree.topLevelItem(0);self.assertFalse(root.isExpanded())
        QTest.mouseClick(tree.viewport(),Qt.MouseButton.LeftButton,pos=point)
        self.assertTrue(root.isExpanded())
        w.new_project();self.assertEqual(w.project_picker.currentData(),w.active_document_id)
        self.assertTrue(w.activate_document(self.first))
        self.assertEqual(w.project.library_folders[0]['name'],'자료 정리')
    def test_media_drag_has_local_urls_and_copy_action(self):
        w=self.w;w.media.add_files([B])
        tree=w.media.project_tree
        for item in tree.selectedItems():item.setSelected(False)
        for item in tree.findItems('',Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive):
            if item.data(0,Qt.ItemDataRole.UserRole)[0]=='media':item.setSelected(True)
        with patch('app.ui.project_tree.QDrag') as drag:
            tree.startDrag(Qt.DropAction.CopyAction)
            mime=drag.return_value.setMimeData.call_args.args[0]
            self.assertEqual([str(Path(u.toLocalFile())) for u in mime.urls()],[A,B])
            drag.return_value.exec.assert_called_once_with(Qt.DropAction.CopyAction)
    def test_open_dialog_multiple_and_duplicate_focus(self):
        w=self.w
        with tempfile.TemporaryDirectory() as folder:
            a=Path(folder)/'a.avsp';b=Path(folder)/'b.avsp'
            save_project(Project(name='A'),a);save_project(Project(name='B'),b)
            with patch('app.ui.main_window.QFileDialog.getOpenFileNames',return_value=([str(a),str(b)],'')):
                w.open_project_dialog()
            self.assertEqual(len(w.documents),3)
            self.assertEqual(w.project.name,'B')
            self.assertTrue(w.open_project_path(a))
            self.assertEqual(len(w.documents),3)
            self.assertEqual(w.project.name,'A')
    def test_failed_drop_keeps_media_and_sequences(self):
        w=self.w;before=w.media.paths()
        with tempfile.TemporaryDirectory() as folder:
            bad=Path(folder)/'bad.mp4';bad.write_bytes(b'not a video')
            self.assertFalse(w.handle_media_drop([B,str(bad)],w.timeline.sequence_tree.viewport(),QPointF(10,500)))
        self.assertEqual(w.media.paths(),before)
        self.assertEqual(w.project.edit_sequences,[])
    def test_documents_isolate_dirty_sequences_history_and_save(self):
        w=self.w
        w.create_edit_sequence(A,[(0,1),(3,4)],7.188)
        w.select_sequence_clip('video',0);w.delete_sequence_clip()
        first_seq=deepcopy(w.active_sequence())
        w.project_name.setText('첫 프로젝트');w.rename_project()
        w.new_project();second=w.active_document_id
        self.assertEqual(len(w.documents),2)
        self.assertEqual(w.media.paths(),[])
        w.media.add_files([B]);self.wait(lambda:w.preview.ready)
        w.project_name.setText('둘째 프로젝트');w.rename_project()
        w.create_edit_sequence(B,[(0,1)],3)
        second_seq=deepcopy(w.active_sequence())
        self.assertTrue(w.activate_document(self.first));self.wait(lambda:w.preview.ready)
        self.assertEqual(w.active_sequence(),first_seq)
        w.undo_subtitle();self.assertEqual(len(sequence_clips(w.active_sequence())),4)
        self.assertTrue(w.dirty)
        self.assertTrue(w.activate_document(second));self.wait(lambda:w.preview.ready)
        self.assertEqual(w.active_sequence(),second_seq)
        self.assertFalse(w.sequence_history.get(second_seq['id']))
        with tempfile.TemporaryDirectory() as folder:
            b=Path(folder)/'b.avsp';a=Path(folder)/'a.avsp'
            self.assertTrue(w.save_current(path=b))
            self.assertTrue(w.activate_document(self.first))
            self.assertTrue(w.save_current(path=a))
            self.assertNotEqual(load_project(a).name,load_project(b).name)
            with patch.object(QMessageBox,'warning'):
                self.assertFalse(w.save_current(path=b))
    def test_collapsed_trees_survive_updates_and_no_fixed_view_rows(self):
        w=self.w;tree=w.media.project_tree;lower=w.timeline.sequence_tree
        w.new_organized_folder('library','원본');w.new_organized_folder('edit','편집')
        tree.topLevelItem(0).setExpanded(False);lower.topLevelItem(0).setExpanded(False)
        w.mark_dirty()
        self.assertFalse(tree.topLevelItem(0).isExpanded());self.assertFalse(lower.topLevelItem(0).isExpanded())
        self.assertFalse(any(item.data(0,Qt.ItemDataRole.UserRole)[0]=='view' for item in lower.findItems('',Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive)))
        self.assertTrue(w.timeline.scope.isHidden())
    def test_drop_blank_creates_and_sequence_appends_cross_project(self):
        w=self.w
        w.new_project();second=w.active_document_id
        w.media.add_files([B]);self.wait(lambda:w.preview.ready)
        w.create_edit_sequence(B,[(0,1)],3)
        target_seq=w.active_edit_id
        w.activate_document(self.first);self.wait(lambda:w.preview.ready)
        self.assertTrue(w.activate_document(second))
        lower=w.timeline.sequence_tree
        item=self.item(lower,'sequence',second,target_seq)
        self.drop(lower,item,[A])
        self.assertEqual(w.active_document_id,second)
        self.assertIn(A,w.media.paths())
        self.assertEqual(len(sequence_clips(w.active_sequence())),4)
        self.assertEqual(w.active_sequence()['source'],B)
        self.assertEqual(w.preview.timeline_duration(),8188)
        self.drop(lower,None,[B,A],blank=True)
        self.assertEqual(len(w.project.edit_assets),2)
        lower.clearSelection()
        for item in lower.findItems('',Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive):
            if item.data(0,Qt.ItemDataRole.UserRole)[0]=='asset':item.setSelected(True)
        w.edit_from_selected_assets()
        self.assertEqual(len(w.project.edit_sequences),2)
        self.assertEqual(w.preview.timeline_duration(),10188)
        self.assertEqual(w.documents[0]['project'].media_paths,[A])
    def test_timeline_drop_inserts_at_position_and_undo(self):
        w=self.w;w.create_edit_sequence(A,[(0,4),(5,7)],7.188)
        c=w.timeline.canvas
        x=95+1500/c.span*(c.width()-107)
        self.assertTrue(w.handle_media_drop([B],c,QPointF(x,45)))
        self.assertEqual(w.preview.timeline_duration(),9000)
        selected=w.timeline.sequence_tree.selectedItems()
        self.assertEqual(len(selected),1)
        self.assertEqual(selected[0].data(0,Qt.ItemDataRole.UserRole),("sequence",w.active_document_id,w.active_edit_id))
        self.assertEqual(len(sequence_clips(w.active_sequence())),8)
        w.undo_subtitle()
        self.assertEqual(w.preview.timeline_duration(),6000)
        self.assertIn(B,w.media.paths())
    def test_mixed_source_playback_switch_and_original_return(self):
        w=self.w
        self.assertTrue(w.handle_media_drop([B,A],w.timeline.sequence_tabs,QPointF(w.timeline.sequence_tabs.width()-2,10)))
        self.wait(lambda:w.preview.ready)
        self.assertEqual(w.preview.timeline_duration(),10188)
        w.seek_transport(3200)
        self.wait(lambda:Path(w.preview.player.source().toLocalFile())==Path(A) and not w.preview._sequence_pending)
        self.assertAlmostEqual(w.preview.player.position(),200,delta=120)
        w.seek_transport(2850);w.toggle_transport()
        self.wait(lambda:w.preview.timeline_position()>3300)
        self.assertEqual(Path(w.preview.player.source().toLocalFile()),Path(A))
        w.toggle_transport()
        w.timeline.sequence_tabs.setCurrentIndex(0)
        self.wait(lambda:w.preview.ready and Path(w.preview.player.source().toLocalFile())==Path(w.media.selected_path()))
        self.assertIsNone(w.preview.sequence_tracks)
    def test_pending_edit_blocks_switch_close_and_open_keeps_unsaved(self):
        w=self.w
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'other.avsp';save_project(Project(name='other'),file)
            with patch.object(QMessageBox,'question',side_effect=AssertionError('Dirty project must stay open')):
                self.assertTrue(w.open_project_path(file))
            second=w.active_document_id
            self.assertEqual(len(w.documents),2)
            w.activate_document(self.first);self.wait(lambda:w.preview.ready)
            w.project.subtitles[A]=[dict(start=0,end=1,text='원본')]
            w.show_source_subtitles(select=0,force=True)
            w.subtitle_panel.editor.text.setPlainText('입력 중')
            with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel):
                self.assertFalse(w.activate_document(second))
                self.assertFalse(w.close_current_project())
            self.assertEqual(w.active_document_id,self.first)
            self.assertEqual(w.subtitle_panel.editor.text.toPlainText(),'입력 중')
            w.subtitle_panel.editor.set_selection(0)
    def test_close_one_and_all_dirty_prompts(self):
        w=self.w;w.new_project();second=w.active_document_id
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Cancel):
            self.assertFalse(w.confirm_all_projects())
        w.activate_document(second)
        self.assertTrue(w.close_current_project())
        self.assertEqual(len(w.documents),1)
        self.assertEqual(w.active_document_id,self.first)

if __name__=='__main__':unittest.main()
