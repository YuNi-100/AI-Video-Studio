import os
os.environ['QT_QPA_PLATFORM']='offscreen'
import unittest,tempfile
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from tests import test_timeline_focus as focus_tests
from tests.test_gap_snap import SOURCE
from app.features.edit_groups import asset_key,visible_edit
from app.features.silence.sequence import sequence_clips
from app.storage.project_store import load_project


class EditGroupTests(unittest.TestCase):
    setUpClass=classmethod(focus_tests.TimelineFocusTests.setUpClass.__func__)
    setUp=focus_tests.TimelineFocusTests.setUp
    tearDown=focus_tests.TimelineFocusTests.tearDown

    def item(self,key,kind='sequence'):
        tree=self.w.timeline.sequence_tree
        return next(i for i in tree.findItems('',Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive) if i.data(0,Qt.ItemDataRole.UserRole)==(kind,self.w.active_document_id,key))

    def click_asset(self,record):
        tree=self.w.timeline.sequence_tree;item=self.item(record['id'],'asset')
        QTest.mouseClick(tree.viewport(),Qt.MouseButton.LeftButton,pos=tree.visualItemRect(item).center())

    def asset(self):
        record=dict(id='repeated-asset',name='같은 영상',source=SOURCE,folder=None)
        self.w.project.edit_assets.append(record);self.w.mark_dirty()
        return record

    def test_actual_repeated_icon_click_after_edit_does_not_add_visible_edits(self):
        w=self.w;record=self.asset();count=sum(visible_edit(s) for s in w.project.edit_sequences)
        for _ in range(4):self.click_asset(record)
        self.assertEqual(w.active_edit_id,asset_key(record))
        w.request_timeline_seek(2000);w.split_sequence_clip()
        w.commit_work_subtitles([dict(start=.2,end=.8,text='수정 상태 유지')])
        clips=sequence_clips(w.active_sequence());total=len(w.project.edit_sequences)
        for _ in range(5):self.click_asset(record)
        self.assertEqual(sum(visible_edit(s) for s in w.project.edit_sequences),count)
        self.assertEqual(len(w.project.edit_sequences),total)
        self.assertEqual(sequence_clips(w.active_sequence()),clips)
        self.assertEqual(w.timeline.canvas.segments[0]['text'],'수정 상태 유지')
        self.assertFalse(any(i.data(0,Qt.ItemDataRole.UserRole)==('sequence',w.active_document_id,asset_key(record)) for i in w.timeline.sequence_tree.findItems('',Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive)))

    def test_explicit_group_uses_edited_asset_and_child_updates_parent(self):
        w=self.w;record=self.asset();self.click_asset(record)
        w.request_timeline_seek(2000);w.split_sequence_clip()
        w.commit_work_subtitles([dict(start=.2,end=.8,text='묶음에 가져갈 수정 자막')])
        tree=w.timeline.sequence_tree;tree.clearSelection();tree.setCurrentItem(self.item(record['id'],'asset'))
        w.edit_from_selected_assets();parent=w.active_edit_id
        self.assertNotEqual(parent,asset_key(record))
        node=self.item(parent);self.assertEqual(node.childCount(),1)
        child=node.child(0).data(0,Qt.ItemDataRole.UserRole)[2]
        w.open_edit_sequence(child)
        self.assertEqual(len(sequence_clips(w.active_sequence())),4)
        w.commit_work_subtitles([dict(start=.2,end=.8,text='하위 수정본의 자막')])
        w.open_edit_sequence(parent)
        self.assertEqual(w.timeline.canvas.segments[0]['text'],'하위 수정본의 자막')
        w.open_asset_work(record)
        self.assertEqual(w.timeline.canvas.segments[0]['text'],'묶음에 가져갈 수정 자막')
        w.open_edit_sequence(parent);w.request_timeline_seek(1000);w.split_sequence_clip()
        w.open_edit_sequence(child);self.assertEqual(len(sequence_clips(w.active_sequence())),6)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'groups.avsp';self.assertTrue(w.save_current(path=path))
            loaded=load_project(path)
            self.assertEqual(next(s for s in loaded.edit_sequences if s['id']==child)['parent_id'],parent)
        w.undo_subtitle();w.redo_subtitle()
        self.assertEqual(len(sequence_clips(w.active_sequence())),6)

    def test_menu_enablement_and_copy_preserve_independent_asset_state(self):
        w=self.w;record=self.asset();self.click_asset(record)
        w.commit_work_subtitles([dict(start=.2,end=.8,text='복사할 수정 상태')])
        tree=w.timeline.sequence_tree;tree.clearSelection();item=self.item(record['id'],'asset');tree.setCurrentItem(item)
        menu=w.build_organizer_menu(tree,'edit',item);actions={a.text():a for a in menu.actions()}
        self.assertTrue(actions['선택 자료로 새 편집본'].isEnabled())
        self.assertFalse(actions['선택 편집본 조합'].isEnabled())
        self.assertFalse(actions['복사한 컷으로 새 편집본'].isEnabled())
        actions['복사'].trigger();w.paste_organized('edit')
        copied=next(r for r in w.project.edit_assets if r['id']!=record['id'])
        w.open_asset_work(copied);self.assertEqual(w.timeline.canvas.segments[0]['text'],'복사할 수정 상태')
        w.commit_work_subtitles([dict(start=.2,end=.8,text='복사본만 변경')])
        w.open_asset_work(record);self.assertEqual(w.timeline.canvas.segments[0]['text'],'복사할 수정 상태')

    def test_two_file_child_ripple_updates_parent_and_other_child_with_history(self):
        w=self.w
        other=str(Path(SOURCE).with_name('테스트 영상.mov'))
        w.create_labeled_edit([SOURCE,other],['첫 영상','뒤 영상'])
        parent=w.active_edit_id;node=self.item(parent)
        self.assertEqual(node.childCount(),2)
        child=node.child(0).data(0,Qt.ItemDataRole.UserRole)[2]
        w.open_edit_sequence(child);w.request_timeline_seek(1000);w.split_sequence_clip()
        w.request_timeline_seek(500);w.delete_sequence_clip(True)
        w.open_edit_sequence(parent)
        following=next(c for c in sequence_clips(w.active_sequence()) if c.get('source')==other)
        self.assertAlmostEqual(following['at'],6.188,places=3)
        w.undo_subtitle();w.open_edit_sequence(parent)
        following=next(c for c in sequence_clips(w.active_sequence()) if c.get('source')==other)
        self.assertAlmostEqual(following['at'],7.188,places=3)
        w.redo_subtitle();w.open_edit_sequence(parent)
        self.assertAlmostEqual(next(c for c in sequence_clips(w.active_sequence()) if c.get('source')==other)['at'],6.188,places=3)

    def test_child_rename_and_removal_menu_update_parent_and_undo(self):
        w=self.w;parent=w.active_edit_id;node=self.item(parent)
        child=node.child(0).data(0,Qt.ItemDataRole.UserRole)[2]
        tree=w.timeline.sequence_tree;tree.clearSelection();tree.setCurrentItem(self.item(child))
        self.assertTrue(w.rename_organized('edit',name='영상 수정본'))
        self.assertIn('영상 수정본',self.item(child).text(0))
        menu=w.build_organizer_menu(tree,'edit',self.item(child));actions={a.text():a for a in menu.actions()}
        self.assertFalse(actions['위로 이동'].isEnabled())
        actions['목록에서 제거'].trigger()
        w.open_edit_sequence(parent);self.assertEqual(sequence_clips(w.active_sequence()),[])
        w.undo_subtitle();w.open_edit_sequence(parent)
        self.assertEqual(len(sequence_clips(w.active_sequence())),2)
