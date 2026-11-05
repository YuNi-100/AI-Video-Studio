import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from copy import deepcopy
from pathlib import Path
import tempfile,time,unittest,json,subprocess
from unittest.mock import patch
from PySide6.QtCore import Qt,QPointF,QMimeData,QPoint
from PySide6.QtWidgets import QApplication,QInputDialog
from PySide6.QtGui import QDragEnterEvent,QDropEvent
from PySide6.QtTest import QTest
from app.ui.main_window import MainWindow
from app.ui.video_export_dialog import VideoExportDialog
from app.core.project import Project
from app.storage.project_store import load_project,save_project
from app.features.silence.sequence import combine_sequences,sequence_clips,sequence_layout,edit_clip

A=str((Path(__file__).parent/'fixtures/speech-test.mp4').resolve())
B=str((Path(__file__).parent/'fixtures/테스트 영상.mp4').resolve())


class OrganizationModelTests(unittest.TestCase):
    def test_folder_records_portable_roundtrip_and_legacy(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=str(root/'a.mp4')
            p=Project(media_paths=[path],library_folders=[dict(id='f',name='경기',parent=None)],library_items=[dict(id='m',name='보관함 이름',source=path,folder='f')],edit_folders=[dict(id='e',name='편집',parent=None)],edit_assets=[dict(id='a',name='독립 이름',source=path,folder='e')])
            dest=root/'x.avsp';save_project(p,dest)
            self.assertEqual(load_project(dest),p)
            raw=json.loads(dest.read_text(encoding='utf-8'));self.assertEqual(raw['edit_assets'][0]['source'],'a.mp4')
            for key in ('library_folders','library_items','edit_folders','edit_assets','edit_locations'):raw.pop(key)
            dest.write_text(json.dumps(raw),encoding='utf-8');self.assertIsNone(load_project(dest).library_items)
    def test_invalid_cycles_and_missing_asset_sources_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Project(library_folders=[dict(id='x',name='cycle',parent='x')])
            with self.assertRaises(ValueError):save_project(p,Path(folder)/'x.avsp')
            p=Project(edit_assets=[dict(id='a',name='missing',source=A,folder=None)])
            with self.assertRaises(ValueError):save_project(p,Path(folder)/'x.avsp')
    def test_composition_is_independent_and_captions_snapshot(self):
        s=dict(id='a',name='전반',source=A,duration=7.188,ranges=[[0,1]])
        rows={A:[dict(start=.1,end=.7,text='원래 자막')]}
        c=combine_sequences([s,s],rows,name='조합')
        before=deepcopy(c)
        s['ranges'][0][1]=2;rows[A][0]['text']='바뀐 자막'
        self.assertEqual(c,before)
        self.assertEqual(c['kind'],'composition')
        self.assertEqual(sequence_layout(c)[2],2000)
        self.assertEqual(sequence_layout(c,rows)[1][0]['text'],'원래 자막')
        self.assertEqual(sequence_layout(edit_clip(c,0,'end',-200,True))[2],1800)


class OrganizationUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.w=MainWindow();self.w.show();self.w.preview.audio.setMuted(True)
        self.w.media.add_files([A]);self.wait(lambda:self.w.preview.ready)
    def tearDown(self):
        for doc in self.w.documents:doc['dirty']=False
        self.w.dirty=False;self.w.close();QTest.qWait(20)
    def wait(self,p,timeout=8):
        end=time.monotonic()+timeout
        while not p() and time.monotonic()<end:QTest.qWait(20)
        self.assertTrue(p())
    def find(self,kind,key=None):
        tree=self.w.media.project_tree if kind=='media' else self.w.timeline.sequence_tree
        return next(item for item in tree.findItems('',Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive) if item.data(0,Qt.ItemDataRole.UserRole)[0]==kind and (key is None or key in item.data(0,Qt.ItemDataRole.UserRole)))
    def select(self,item,tree):
        tree.clearSelection();tree.setCurrentItem(item)
    def test_library_and_edit_names_independent_and_double_click_rename(self):
        w=self.w
        self.assertTrue(w.handle_media_drop([A],w.timeline.sequence_tree.viewport(),QPointF(10,400)))
        item=self.find('asset')
        self.assertTrue(w.rename_organized('edit',item,'경기 요약 자료'))
        self.assertNotEqual(w.project.library_items[0]['name'],w.project.edit_assets[0]['name'])
        item=self.find('media')
        with patch.object(QInputDialog,'getText',return_value=('원본 자료 이름',True)):
            w.media.project_tree.itemDoubleClicked.emit(item,0)
        self.assertEqual(w.project.edit_assets[0]['name'],'경기 요약 자료')
        self.assertEqual(w.project.library_items[0]['name'],'원본 자료 이름')
        self.assertEqual(Path(A).name,'speech-test.mp4')
    def test_folders_group_many_edits_tab_close_reopen_no_duplicate(self):
        w=self.w
        folder=w.new_organized_folder('edit','경기 묶음')
        w.create_edit_sequence(A,[(0,1)],7.188);one=w.active_edit_id
        w.project.edit_locations[one]=folder
        w.create_edit_sequence(A,[(1,2)],7.188);two=w.active_edit_id
        w.project.edit_locations[two]=folder;w.mark_dirty()
        self.assertEqual(len([s for s in w.project.edit_sequences if not s.get("parent_id")]),2)
        w.close_edit_sequence(w.timeline.sequence_tabs.currentIndex())
        self.assertEqual(len([s for s in w.project.edit_sequences if not s.get("parent_id")]),2)
        self.assertIn(two,w.closed_sequence_ids)
        w.organized_clicked(self.find('sequence',two),'edit')
        self.assertEqual(w.active_edit_id,two)
        self.assertEqual(len([s for s in w.project.edit_sequences if not s.get("parent_id")]),2)
        self.assertTrue(w.rename_organized('edit',self.find('sequence',two),'후반 편집본'))
        self.assertEqual(w.timeline.sequence_tabs.tabText(w.timeline.sequence_tabs.currentIndex()),'후반 편집본')
    def test_asset_drop_to_existing_tab_appends_and_blank_tab_creates(self):
        w=self.w;w.create_edit_sequence(A,[(0,1)],7.188)
        tabs=w.timeline.sequence_tabs
        rect=tabs.tabRect(tabs.currentIndex())
        self.assertTrue(w.handle_media_drop([B],tabs,QPointF(rect.center())))
        self.assertEqual(w.preview.timeline_duration(),4000)
        self.assertEqual(len([s for s in w.project.edit_sequences if not s.get("parent_id")]),1)
        self.assertTrue(w.handle_media_drop([B],tabs,QPointF(tabs.width()-2,rect.center().y())))
        self.assertEqual(len([s for s in w.project.edit_sequences if not s.get("parent_id")]),2)
        self.assertEqual(w.preview.timeline_duration(),3000)
    def test_copy_paste_folder_and_remove_folder_retains_contents(self):
        w=self.w;folder=w.new_organized_folder('edit','작업')
        w.handle_media_drop([A],w.timeline.sequence_tree.viewport(),QPointF(10,400))
        w.project.edit_assets[0]['folder']=folder;w.mark_dirty()
        tree=w.timeline.sequence_tree
        self.select(self.find('folder',folder),tree);w.copy_organized('edit')
        tree.clearSelection();tree.setCurrentItem(None);w.paste_organized('edit')
        self.assertEqual(len(w.project.edit_folders),2)
        self.assertEqual(len(w.project.edit_assets),2)
        self.select(self.find('folder',folder),tree);w.delete_organized('edit')
        self.assertEqual(len(w.project.edit_assets),2)
        self.assertEqual(len(w.project.edit_folders),1)
    def test_combination_creates_kind_and_save_restores_names_folders(self):
        w=self.w
        w.create_edit_sequence(A,[(0,1)],7.188);first=w.active_edit_id
        w.create_edit_sequence(A,[(2,3)],7.188);second=w.active_edit_id
        tree=w.timeline.sequence_tree;tree.clearSelection()
        self.find('sequence',first).setSelected(True);self.find('sequence',second).setSelected(True)
        w.compose_selected();combined=w.active_sequence()
        self.assertEqual(combined['kind'],'composition')
        self.assertEqual(w.preview.timeline_duration(),2000)
        self.assertEqual(len([s for s in w.project.edit_sequences if not s.get("parent_id")]),3)
        w.project.edit_sequences[0]['ranges'][0][1]=2
        self.assertEqual(sequence_layout(combined)[2],2000)
        group=w.new_organized_folder('edit','조합 묶음')
        w.project.edit_locations[combined['id']]=group;w.mark_dirty()
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder)/'x.avsp';self.assertTrue(w.save_current(path=dest))
            loaded=load_project(dest)
            self.assertEqual(loaded.edit_sequences,w.project.edit_sequences)
            self.assertEqual(loaded.library_items,w.project.library_items)
            w.apply_project(loaded,dest)
            self.assertIsNotNone(self.find("folder",group))
            w.open_edit_sequence(combined["id"])
            self.wait(lambda:w.preview.ready)
            self.assertEqual(w.preview.timeline_duration(),2000)
    def test_native_custom_mime_library_to_bin_and_bin_to_tab(self):
        w=self.w
        source=self.find('media').data(0,Qt.ItemDataRole.UserRole)
        mime=QMimeData();mime.setData('application/x-studio-organizer',json.dumps([source]).encode())
        view=w.timeline.sequence_tree.viewport();pos=QPoint(10,view.height()-4)
        for event in (QDragEnterEvent(pos,Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier),QDropEvent(QPointF(pos),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)):
            QApplication.sendEvent(view,event)
            self.assertTrue(event.isAccepted())
        self.assertEqual(len(w.project.edit_assets),1)
        self.assertEqual(w.project.edit_sequences,[])
        asset=self.find('asset').data(0,Qt.ItemDataRole.UserRole)
        tabs=w.timeline.sequence_tabs
        self.assertTrue(w.handle_organization_drop([asset],tabs,QPointF(400,10)))
        self.assertEqual(len([s for s in w.project.edit_sequences if not s.get("parent_id")]),1)
        self.assertEqual(w.preview.timeline_duration(),7188)
        rect=tabs.tabRect(tabs.currentIndex())
        self.assertTrue(w.handle_organization_drop([asset],tabs,QPointF(rect.center())))
        self.assertEqual(w.preview.timeline_duration(),14376)
        self.assertNotEqual(w.active_sequence().get("kind"),"composition")
    def test_library_delete_keeps_edit_source_and_original(self):
        w=self.w;before=Path(A).read_bytes()
        w.create_edit_sequence(A,[(0,1)],7.188)
        self.select(self.find('media'),w.media.project_tree);w.delete_organized('library')
        self.assertEqual(w.project.library_items,[])
        self.assertEqual(len([s for s in w.project.edit_sequences if not s.get("parent_id")]),1)
        self.assertEqual(Path(A).read_bytes(),before)
    def test_folder_cycle_drag_rejected(self):
        w=self.w
        parent=w.new_organized_folder('edit','parent');child=w.new_organized_folder('edit','child',parent)
        target=self.find('folder',child)
        point=w.timeline.sequence_tree.visualItemRect(target).center()
        self.assertFalse(w.handle_organization_drop([('folder',w.active_document_id,'edit',parent)],w.timeline.sequence_tree.viewport(),QPointF(point)))
        self.assertIsNone(w.project.edit_folders[0]['parent'])


class VideoOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        seq=dict(id='out',name='시험 출력',source=A,duration=7.188,ranges=[],clips=[dict(track=t,source=p,source_duration=d,start=0,end=length,at=at,group=str(i)) for i,(p,d,length,at) in enumerate([(A,7.188,.5,0),(B,3,1,1)]) for t in ('video','audio')])
        self.d=VideoExportDialog(seq,[dict(start=.1,end=.4,text='한글 자막')])
    def tearDown(self):self.d.reject();self.temp.cleanup()
    def wait(self):
        end=time.monotonic()+30
        while self.d.process and time.monotonic()<end:QTest.qWait(20)
        self.assertIsNone(self.d.process,self.d.status.text())
    def test_actual_mixed_gaps_captions_mp4(self):
        output=Path(self.temp.name)/'결과.mp4'
        before=Path(A).read_bytes()
        self.assertTrue(self.d.start_output(output));self.wait()
        self.assertTrue(output.exists(),self.d.status.text())
        raw=subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(output)])
        info=json.loads(raw);self.assertAlmostEqual(float(info['format']['duration']),2,delta=.1)
        self.assertEqual({s['codec_type'] for s in info['streams']},{'video','audio'})
        subprocess.run(['ffmpeg','-v','error','-i',str(output),'-f','null','-'],check=True)
        self.assertEqual(before,Path(A).read_bytes())
        self.assertEqual(self.d.progress.value(),100)
    def test_cancel_and_existing_files_protected(self):
        path=Path(self.temp.name)/'existing.mp4';path.write_bytes(b'keep')
        self.assertFalse(self.d.start_output(path));self.assertEqual(path.read_bytes(),b'keep')
        path=Path(self.temp.name)/'cancel.mp4'
        self.assertTrue(self.d.start_output(path));partial=self.d.partial
        self.d.cancel_work();self.wait()
        self.assertFalse(path.exists());self.assertFalse(partial.exists())

if __name__=='__main__':unittest.main()
