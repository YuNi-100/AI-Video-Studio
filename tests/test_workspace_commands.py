import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import json,time,unittest,tempfile
from copy import deepcopy
from pathlib import Path
from PySide6.QtWidgets import QApplication,QDialog,QVBoxLayout,QPushButton,QLineEdit
from PySide6.QtCore import Qt,QPointF,QPoint,QMimeData
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow
from app.storage.project_store import load_project
from app.features.silence.sequence import sequence_clips

A=str((Path(__file__).parent/'fixtures/speech-test.mp4').resolve())
B=str((Path(__file__).parent/'fixtures/테스트 영상.mp4').resolve())
CTRL=Qt.KeyboardModifier.ControlModifier
REDO=CTRL|Qt.KeyboardModifier.ShiftModifier


class WorkspaceCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.w=MainWindow();self.w.show();self.w.activateWindow();self.w.preview.audio.setMuted(True)
        self.w.media.add_files([A,B]);self.wait(lambda:self.w.preview.ready)
        self.original=[Path(p).read_bytes() for p in (A,B)]

    def wait(self,predicate):
        end=time.monotonic()+8
        while not predicate() and time.monotonic()<end:QTest.qWait(20)
        self.assertTrue(predicate())

    def tearDown(self):
        self.assertEqual([Path(p).read_bytes() for p in (A,B)],self.original)
        self.w.dirty=False
        for d in self.w.documents:d['dirty']=False
        self.w.close();QTest.qWait(20)

    def key(self,widget,redo=False):
        widget.setFocus();QTest.keyClick(widget,Qt.Key.Key_Z,REDO if redo else CTRL)

    def item(self,kind,key=None):
        tree=self.w.timeline.sequence_tree
        return next(r for r in tree.findItems('',Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive)
            if r.data(0,Qt.ItemDataRole.UserRole)[0]==kind and (key is None or r.data(0,Qt.ItemDataRole.UserRole)[-1]==key))

    def select(self,item,tree=None):
        tree=tree or self.w.timeline.sequence_tree
        tree.clearSelection();tree.setCurrentItem(item)

    def drop(self,payload,widget,pos):
        mime=QMimeData();mime.setData('application/x-studio-organizer',json.dumps(payload).encode())
        for event in (QDragEnterEvent(pos,Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier),
                      QDropEvent(QPointF(pos),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)):
            QApplication.sendEvent(widget,event)
            self.assertTrue(event.isAccepted())

    def setup_edit(self):
        w=self.w
        w.project.subtitles[A]=[dict(start=.1,end=.7,text='기존 자막',reviewed=True)]
        w.create_edit_sequence(A,[(0,1)],7.188)
        w.project.edit_assets.append(dict(id='asset',name='공모전 자료',source=B,folder=None));w.mark_dirty()
        return ('asset',w.active_document_id,'asset')

    def test_bin_and_canvas_drops_append_without_duplicate_originals(self):
        w=self.w;payload=self.setup_edit();seq_id=w.active_edit_id
        originals=deepcopy(w.project.library_items)
        self.drop([payload],w.timeline.canvas,QPoint(105,47))
        video=[c for c in sequence_clips(w.active_sequence()) if c['track']=='video']
        self.assertEqual([(r['at'],r.get('source',A)) for r in video],[(0,A),(1,B)])
        self.assertEqual(w.project.library_items,originals)
        w.undo_subtitle();self.assertEqual(len(sequence_clips(w.active_sequence())),2)
        target=self.item('sequence',seq_id)
        self.drop([payload],w.timeline.sequence_tree.viewport(),w.timeline.sequence_tree.visualItemRect(target).center())
        self.assertEqual([(c['at'],c.get('source',A)) for c in sequence_clips(w.active_sequence()) if c['track']=='video'],[(0,A),(1,B)])
        self.assertEqual(w.project.library_items,originals)

    def test_timeline_margin_routes_to_append_and_upper_library_stays_unique(self):
        w=self.w;payload=self.setup_edit()
        self.drop([payload],w.timeline.hint,QPoint(10,5))
        self.assertEqual(len(w.project.library_items),2)
        self.assertEqual(len(w.project.edit_sequences),1)
        self.assertEqual(w.preview.timeline_duration(),4000)
        self.drop([payload],w.media.project_tree.viewport(),QPoint(10,w.media.project_tree.viewport().height()-5))
        self.assertEqual(len(w.project.library_items),2)

    def test_old_duplicate_library_records_collapse_without_touching_edit_assets(self):
        w=self.w
        row=deepcopy(w.project.library_items[0]);row['id']='duplicate'
        w.project.library_items.append(row)
        w.project.edit_assets=[dict(id='one',source=A,name='첫 자료',folder=None),dict(id='two',source=A,name='다른 자료',folder=None)]
        w.sync_workspace_ui()
        self.assertEqual(len(w.project.library_items),2)
        self.assertEqual(len(w.project.edit_assets),2)

    def test_delete_edit_undo_redo_restores_full_content_folder_and_save(self):
        w=self.w;self.setup_edit();key=w.active_edit_id
        folder=w.new_organized_folder('edit','완성본')
        w.project.edit_locations[key]=folder;w.mark_dirty()
        before=deepcopy(w.active_sequence())
        self.select(self.item('sequence',key))
        tree=w.timeline.sequence_tree;tree.setFocus();QTest.keyClick(tree,Qt.Key.Key_Delete)
        self.assertEqual(w.project.edit_sequences,[])
        self.key(tree)
        self.assertEqual(w.active_sequence(),before)
        self.assertEqual(w.project.edit_locations[key],folder)
        self.key(tree,True);self.assertEqual(w.project.edit_sequences,[])
        self.key(tree)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'restored.avsp';self.assertTrue(w.save_current(path=path))
            self.assertEqual(load_project(path).edit_sequences,[before])

    def test_folder_delete_undo_restores_nested_structure(self):
        w=self.w
        parent=w.new_organized_folder('edit','부모')
        child=w.new_organized_folder('edit','자식',parent)
        w.project.edit_assets=[dict(id='asset',source=B,name='자료',folder=parent)];w.mark_dirty()
        self.select(self.item('folder',parent));w.delete_organized('edit')
        self.assertEqual(w.project.edit_assets[0]['folder'],None)
        self.key(w.timeline.sequence_tree)
        self.assertEqual(w.project.edit_assets[0]['folder'],parent)
        self.assertEqual(next(r for r in w.project.edit_folders if r['id']==child)['parent'],parent)

    def test_chronological_history_across_bins_and_timeline(self):
        w=self.w;self.setup_edit();key=w.active_edit_id
        self.select(self.item('sequence',key));w.rename_organized('edit',name='이름 변경')
        w.timeline.canvas.selected_clip=0;w.timeline.canvas.selected_keys={0,1};w.delete_sequence_clip()
        w.new_organized_folder('edit','마지막 작업')
        self.key(w.media.project_tree)
        self.assertEqual(w.project.edit_folders,[])
        self.key(w.media.project_tree);self.assertEqual(len(sequence_clips(w.active_sequence())),2)
        self.key(w.media.project_tree);self.assertNotEqual(w.active_sequence()['name'],'이름 변경')
        self.key(w.media.project_tree,True);self.assertEqual(w.active_sequence()['name'],'이름 변경')
        w.new_organized_folder('edit','새 작업');self.assertEqual(w.project_redo,[])

    def test_history_is_project_scoped_and_creation_can_be_undone(self):
        w=self.w;first=w.active_document_id
        w.new_organized_folder('edit','첫 프로젝트 폴더')
        w.new_project();second=w.active_document_id
        w.new_organized_folder('edit','둘째 폴더');w.undo_subtitle()
        self.assertEqual(w.project.edit_folders,[])
        w.activate_document(first);w.undo_subtitle()
        self.assertEqual(w.project.edit_folders,[])
        w.redo_subtitle();self.assertEqual(w.project.edit_folders[0]['name'],'첫 프로젝트 폴더')
        w.activate_document(second);w.redo_subtitle()
        self.assertEqual(w.project.edit_folders[0]['name'],'둘째 폴더')

    def test_owned_dialog_shortcuts_and_native_text_undo(self):
        w=self.w;w.new_organized_folder('edit','되돌릴 폴더')
        dialog=QDialog(w);layout=QVBoxLayout(dialog);button=QPushButton('비교',dialog);edit=QLineEdit(dialog)
        layout.addWidget(button);layout.addWidget(edit);dialog.show();dialog.activateWindow();QTest.qWait(20)
        self.key(button);self.assertEqual(w.project.edit_folders,[])
        self.key(button,True);self.assertEqual(len(w.project.edit_folders),1)
        edit.setFocus();QTest.keyClicks(edit,'text');self.key(edit)
        self.assertEqual(edit.text(),'');self.assertEqual(len(w.project.edit_folders),1)
        dialog.close();w.activateWindow()

    def test_library_delete_and_import_undo_preserve_physical_files(self):
        w=self.w;self.setup_edit()
        tree=w.media.project_tree;item=tree.topLevelItem(0)
        self.select(item,tree);w.delete_organized('library')
        self.assertEqual(len(w.project.library_items),1)
        self.key(tree);self.assertEqual(len(w.project.library_items),2)
        self.assertTrue(Path(A).is_file())

    def test_edit_creation_is_reversible_and_browsing_keeps_redo(self):
        w=self.w
        w.create_edit_sequence(A,[(0,1)],7.188)
        self.assertEqual(len(w.project.edit_sequences),1)
        w.undo_subtitle();self.assertEqual(w.project.edit_sequences,[])
        self.assertIsNone(w.active_edit_id)
        w.open_media(B)
        self.wait(lambda:w.preview.ready)
        self.assertTrue(w.project_redo)
        w.redo_subtitle();self.assertEqual(len(w.project.edit_sequences),1)

    def test_history_limit_and_no_op_commands(self):
        w=self.w
        for i in range(32):w.new_organized_folder('edit',f'폴더 {i}')
        self.assertEqual(len(w.project_undo),30)
        before=len(w.project_undo)
        w.rename_project()
        self.assertEqual(len(w.project_undo),before)
        for _ in range(30):w.undo_subtitle()
        self.assertEqual(len(w.project.edit_folders),2)
        self.assertFalse(w.project_undo)
