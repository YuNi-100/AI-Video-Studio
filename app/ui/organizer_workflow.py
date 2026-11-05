"""Folder-based library and edit bin. Names here are independent references."""
from copy import deepcopy
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import Qt,QSignalBlocker,QPointF
from PySide6.QtWidgets import QTreeWidgetItem,QInputDialog,QMenu,QApplication
from PySide6.QtGui import QShortcut,QKeySequence
from app.core.project import validate_display_name
from app.ui.type_icons import type_icon
from app.features.silence.sequence import (sequence_clips,sequence_layout,sequence_sources,combine_sequences,validate_sequence,insert_sources)


class OrganizerWorkflow:
    def init_organizer(self):
        self.organizer_clipboard=[]
        self.media.project_tree.itemDoubleClicked.connect(lambda item,col:self.rename_organized('library',item))
        self.timeline.sequence_tree.itemDoubleClicked.connect(lambda item,col:self.rename_organized('edit',item))
        for tree,area in ((self.media.project_tree,'library'),(self.timeline.sequence_tree,'edit')):
            tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            tree.customContextMenuRequested.connect(lambda point,t=tree,a=area:self.organizer_menu(t,a,point))
            for shortcut,callback in [('F2',lambda a=area:self.rename_organized(a)),('Delete',lambda a=area:self.delete_organized(a)),('Ctrl+C',lambda a=area:self.copy_organized(a)),('Ctrl+V',lambda a=area:self.paste_organized(a))]:
                key=QShortcut(QKeySequence(shortcut),tree);key.setContext(Qt.ShortcutContext.WidgetShortcut);key.activated.connect(callback)
        self.media.tree_rename_shortcut.setEnabled(False);self.media.tree_remove_shortcut.setEnabled(False)
        self.media.rename_button.clicked.disconnect();self.media.rename_button.clicked.connect(lambda:self.rename_organized('library'))
        self.media.remove_button.clicked.disconnect();self.media.remove_button.clicked.connect(lambda:self.delete_organized('library'))
        self.media.new_folder.clicked.connect(lambda:self.new_organized_folder('library'))
        self.timeline.new_folder.clicked.connect(lambda:self.new_organized_folder('edit'))
        self.timeline.sequence_tabs.tabBarDoubleClicked.connect(lambda i:self.rename_edit_tab(i))
        self.media.imported.connect(self.imported_to_library)
        self.media.relinked.connect(self.relink_library_reference)

    def sync_library_records(self,paths,previous):
        p=self.project
        if p.library_items is None:
            p.library_items=[dict(id=uuid4().hex,source=path,name=p.media_names.get(path,Path(path).name),folder=None) for path in paths]
        else:
            present={r['source'] for r in p.library_items}
            for path in paths:
                if path not in previous and path not in present:
                    p.library_items.append(dict(id=uuid4().hex,source=path,name=self.media.names().get(path,Path(path).name),folder=None))
        # The upper library contains one registration per original source.
        unique=[];seen=set()
        for row in p.library_items:
            key=str(Path(row['source']).resolve()).casefold()
            if key not in seen:
                unique.append(row);seen.add(key)
        p.library_items=unique
        new_names=self.media.names()
        for row in p.library_items:
            old=p.media_names.get(row['source'],Path(row['source']).name)
            new=new_names.get(row['source'],Path(row['source']).name)
            if row['name']==old and old!=new:row['name']=new
        p.library_items=[r for r in p.library_items if r['source'] in paths]
        p.edit_assets=[r for r in p.edit_assets if r['source'] in paths]
        p.edit_locations={key:folder for key,folder in p.edit_locations.items() if any(s['id']==key for s in p.edit_sequences)}

    def relink_library_reference(self,old,new):
        for row in self.project.library_items or []:
            if row['source']==old:row['source']=new

    def imported_to_library(self,paths):
        if self.project.library_items is None:self.project.library_items=[]
        for path in paths:
            if not any(r['source']==path for r in self.project.library_items):
                self.project.library_items.append(dict(id=uuid4().hex,source=path,name=self.media.display_name(path),folder=getattr(self,'_drop_library_folder',None)))

    def organized_tree(self,area):return self.media.project_tree if area=='library' else self.timeline.sequence_tree
    def organized_folders(self,area):return self.project.library_folders if area=='library' else self.project.edit_folders
    def organized_references(self,area):return self.project.library_items if area=='library' else self.project.edit_assets

    def record_for(self,data):
        if not data:return None
        kind=data[0]
        if kind=='folder':return next((r for r in self.organized_folders(data[2]) if r['id']==data[3]),None)
        if kind=='media':return next((r for r in self.project.library_items or [] if r['id']==data[3]),None)
        if kind=='asset':return next((r for r in self.project.edit_assets if r['id']==data[2]),None)
        if kind=='sequence':return next((r for r in self.project.edit_sequences if r['id']==data[2]),None)
        return None

    def current_folder(self,area,item=None):
        item=item or self.organized_tree(area).currentItem()
        data=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        if not data:return None
        if data[0]=='folder':return data[3]
        record=self.record_for(data)
        return self.project.edit_locations.get(record['id']) if data[0]=='sequence' and record else record.get('folder') if record else None

    def new_organized_folder(self,area,name=None,parent=None):
        if not self.allow_project_switch():return
        if name is None:
            name,ok=QInputDialog.getText(self,'새 폴더','폴더 이름',text='새 폴더')
            if not ok:return
            parent=self.current_folder(area)
        try:name=validate_display_name(name)
        except ValueError as exc:self.statusBar().showMessage(str(exc));return
        row=dict(id=uuid4().hex,name=name,parent=parent)
        if len(self.organized_folders(area))>=1000:
            self.statusBar().showMessage("폴더는 최대 1000개입니다.");return
        self.organized_folders(area).append(row);self.mark_dirty();return row['id']

    def rename_organized(self,area,item=None,name=None):
        if not self.allow_project_switch():return False
        item=item or self.organized_tree(area).currentItem()
        data=item.data(0,Qt.ItemDataRole.UserRole) if item else None
        record=self.record_for(data)
        if not record:return False
        if name is None:
            name,ok=QInputDialog.getText(self,'이름 변경','표시 이름',text=record['name'])
            if not ok:return False
        try:name=validate_display_name(name)
        except ValueError as exc:self.statusBar().showMessage(str(exc));return False
        record['name']=name
        if data[0]=='media':
            names=self.media.names();names[record['source']]=name
            self.media.restore(self.media.paths(),self.media.selected_path(),names)
        self.mark_dirty();return True

    def rename_edit_tab(self,index):
        key=self.timeline.sequence_tabs.tabData(index)
        item=next((item for item in self.timeline.sequence_tree.findItems('',Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive) if item.data(0,Qt.ItemDataRole.UserRole)==('sequence',self.active_document_id,key)),None)
        if item:self.rename_organized('edit',item)

    def assign_edit_folder(self,key,folder=None):
        if folder is None:folder=self.current_folder('edit')
        self.project.edit_locations[key]=folder

    def open_edit_sequence(self,key):
        self.closed_sequence_ids.discard(key);self.sync_sequence_tabs()
        index=next((i for i in range(self.timeline.sequence_tabs.count()) if self.timeline.sequence_tabs.tabData(i)==key),0)
        if self.active_edit_id==key and self.timeline.sequence_tabs.currentIndex()==index:return
        if self.timeline.sequence_tabs.currentIndex()==index:self.select_edit_sequence(index)
        else:self.timeline.sequence_tabs.setCurrentIndex(index)
        self.focus_active_sequence_in_list()

    def focus_active_sequence_in_list(self):
        """Explicit view changes select the actual opened edit, including refusals."""
        tree=self.timeline.sequence_tree
        item=next((r for r in tree.findItems('',Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive)
                   if r.data(0,Qt.ItemDataRole.UserRole)==('sequence',self.active_document_id,self.active_edit_id)),None)
        with QSignalBlocker(tree):
            tree.clearSelection()
            tree.setCurrentItem(item)
            if item:
                parent=item.parent()
                while parent:
                    parent.setExpanded(True)
                    tree.disclosure(parent,True)
                    parent=parent.parent()
                item.setSelected(True)
                tree.scrollToItem(item)

    def render_organized_trees(self):
        self.snapshot_document()
        role=Qt.ItemDataRole.UserRole
        for tree,area in ((self.media.project_tree,'library'),(self.timeline.sequence_tree,'edit')):
            oldscroll=tree.verticalScrollBar().value()
            current_data=tuple(tree.currentItem().data(0,role)) if tree.currentItem() and tree.currentItem().data(0,role) else None
            expanded={tuple(item.data(0,role)):item.isExpanded() for item in tree.findItems('',Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive) if item.data(0,role) and item.data(0,role)[0]=='folder'}
            selected={tuple(item.data(0,role)) for item in tree.selectedItems() if item.data(0,role)}
            with QSignalBlocker(tree):
                tree.clear();nodes={None:tree};pending=list(self.organized_folders(area))
                while pending:
                    for row in list(pending):
                        if row['parent'] not in nodes:continue
                        item=QTreeWidgetItem(nodes[row['parent']],[row['name'],'폴더'])
                        item.setData(0,role,('folder',self.active_document_id,area,row['id']))
                        nodes[row['id']]=item;pending.remove(row)
                    if pending and not any(r['parent'] in nodes for r in pending):break
                for row in self.organized_references(area) or []:
                    item=QTreeWidgetItem(nodes.get(row.get('folder'),tree),[row['name'],'원본' if area=='library' else '자료'])
                    item.setData(0,role,('media',self.active_document_id,row['source'],row['id']) if area=='library' else ('asset',self.active_document_id,row['id']))
                    item.setIcon(0,type_icon('original' if area=='library' else 'asset'))
                    item.setToolTip(0,row['source'])
                if area=='edit':
                    for seq in self.project.edit_sequences:
                        item=QTreeWidgetItem(nodes.get(self.project.edit_locations.get(seq['id']),tree),[seq['name'],'조합' if seq.get('kind')=='composition' else '편집본'])
                        item.setData(0,role,('sequence',self.active_document_id,seq['id']))
                        item.setIcon(0,type_icon('composition' if seq.get('kind')=='composition' else 'sequence'))
                        item.setToolTip(0,'독립 복사 조합: '+', '.join(seq.get('components',[])) if seq.get('kind')=='composition' else seq['name'])
                        font=item.font(0);font.setBold(seq['id']==self.active_edit_id);item.setFont(0,font)
                        if seq['id']==self.active_edit_id:item.setToolTip(0,'현재 편집 중: '+seq['name'])
                active=None
                for item in tree.findItems('',Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive):
                    data=item.data(0,role)
                    if data[0]=='folder':
                        item.setExpanded(expanded.get(tuple(data),True));tree.disclosure(item,item.isExpanded())
                    if tuple(data) in selected:item.setSelected(True)
                    if tuple(data)==current_data:tree.setCurrentItem(item,0,tree.selectionModel().SelectionFlag.NoUpdate)
                    if data[0]=='media' and data[2]==self.media.selected_path() and active is None:active=item
                    if data[0]=='sequence' and data[2]==self.active_edit_id:active=item
                if not tree.selectedItems() and active:active.setSelected(True);tree.setCurrentItem(active)
                tree.verticalScrollBar().setValue(oldscroll)
        self.media.count_label.setText(f'영상 {len(self.project.library_items or [])}개')
        with QSignalBlocker(self.project_picker):
            self.project_picker.clear()
            for doc in self.documents:self.project_picker.addItem(doc['project'].name+(' *' if doc['dirty'] else ''),doc['id'])
            self.project_picker.setCurrentIndex(next(i for i,d in enumerate(self.documents) if d['id']==self.active_document_id))

    def organized_clicked(self,item,area):
        data=item.data(0,Qt.ItemDataRole.UserRole)
        if area=='edit' and QApplication.keyboardModifiers() & (Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier):
            return
        if data[0]=='sequence':self.open_edit_sequence(data[2])
        elif data[0] in ('media','asset'):
            record=self.record_for(data)
            if record and record['source'] in self.media.paths():
                path=record['source'];row=self.media.paths().index(path)
                if self.media.listing.currentRow()==row:self.open_media(path)
                else:self.media.listing.setCurrentRow(row)

    def delete_organized(self,area):
        if not self.allow_project_switch():return
        data=[item.data(0,Qt.ItemDataRole.UserRole) for item in self.organized_tree(area).selectedItems()]
        for d in data:
            record=self.record_for(d)
            if not record:continue
            if d[0]=='folder':
                key=record['id'];parent=record['parent']
                for row in self.organized_folders(area):
                    if row['parent']==key:row['parent']=parent
                for row in self.organized_references(area) or []:
                    if row.get('folder')==key:row['folder']=parent
                if area=='edit':
                    for sid,fid in list(self.project.edit_locations.items()):
                        if fid==key:self.project.edit_locations[sid]=parent
                self.organized_folders(area).remove(record)
            elif d[0]=='media':self.project.library_items.remove(record)
            elif d[0]=='asset':self.project.edit_assets.remove(record)
            elif d[0]=='sequence':
                if self.active_edit_id==record['id']:self.timeline.sequence_tabs.setCurrentIndex(0)
                self.project.edit_sequences.remove(record);self.project.edit_locations.pop(record['id'],None)
                self.closed_sequence_ids.discard(record['id'])
        used={r['source'] for r in (self.project.library_items or [])+self.project.edit_assets}
        for seq in self.project.edit_sequences:used.update(sequence_sources(seq))
        paths=[p for p in self.media.paths() if p in used]
        selected=self.media.selected_path();selected=selected if selected in paths else (paths[0] if paths else None)
        self.media.restore(paths,selected,self.media.names())
        if not selected:
            self.preview.shutdown();self.preview.source=None;self.preview.ready=False;self.preview.update_controls();self.preview.stack.setCurrentWidget(self.preview.empty)
        self.mark_dirty()
        if selected and not self.active_sequence():self.open_media(selected)
        else:self.show_source_subtitles(force=True)

    def selected_records(self,area):
        return [item.data(0,Qt.ItemDataRole.UserRole) for item in self.organized_tree(area).findItems('',Qt.MatchFlag.MatchContains|Qt.MatchFlag.MatchRecursive) if item.isSelected()]

    def snapshot_organized(self,data):
        row=self.record_for(data)
        if row is None:return None
        if data[0]!='folder':return dict(kind=data[0],row=deepcopy(row))
        area=data[2];key=row['id']
        children=[('folder',self.active_document_id,area,r['id']) for r in self.organized_folders(area) if r['parent']==key]
        children+=[('media',self.active_document_id,r['source'],r['id']) if area=='library' else ('asset',self.active_document_id,r['id']) for r in self.organized_references(area) or [] if r.get('folder')==key]
        if area=='edit':children+=[('sequence',self.active_document_id,s['id']) for s in self.project.edit_sequences if self.project.edit_locations.get(s['id'])==key]
        return dict(kind='folder',row=deepcopy(row),children=[self.snapshot_organized(d) for d in children])

    def copy_organized(self,area):
        self.organizer_clipboard=[self.snapshot_organized(d) for d in self.selected_records(area)]
        self.organizer_clipboard=[p for p in self.organizer_clipboard if p]
        self.statusBar().showMessage('복사했습니다. 원하는 폴더에서 붙여넣기 하세요.')

    def install_organized_copy(self,payload,area,folder=None):
        kind=payload['kind'];row=deepcopy(payload['row'])
        if kind=='folder':
            key=uuid4().hex;self.organized_folders(area).append(dict(id=key,name=row['name']+' 복사',parent=folder))
            for child in payload['children']:self.install_organized_copy(child,area,key)
            return
        if kind=='sequence':
            if len(self.project.edit_sequences)>=1000:raise ValueError('편집본은 최대 1000개입니다.')
            if area=='library':raise ValueError('편집본은 편집본 목록에 붙여넣어 주세요.')
            row['id']=uuid4().hex;row['name']+=' 복사';self.project.edit_sequences.append(row);self.project.edit_locations[row['id']]=folder
            sources=sequence_sources(row)
        else:
            if len(self.organized_references(area))>=10000:raise ValueError("자료는 최대 10000개입니다.")
            if area=='library' and any(str(Path(r['source']).resolve()).casefold()==str(Path(row['source']).resolve()).casefold() for r in self.project.library_items or []):
                return
            row.update(id=uuid4().hex,folder=folder)
            self.organized_references(area).append(row);sources={row['source']}
        paths=list(dict.fromkeys(self.media.paths()+list(sources)))
        self.media.restore(paths,self.media.selected_path() or paths[0],self.media.names())

    def paste_organized(self,area):
        if not self.allow_project_switch():return
        before=deepcopy(self.project)
        try:
            for payload in self.organizer_clipboard:self.install_organized_copy(payload,area,self.current_folder(area))
            self.mark_dirty()
        except ValueError as exc:
            for name,value in before.__dict__.items():setattr(self.project,name,value)
            self.media.restore(before.media_paths,before.active_path,before.media_names)
            self.sync_sequence_tabs();self.statusBar().showMessage(str(exc))

    def compose_selected(self):
        if not self.allow_project_switch():return
        sequences=[self.record_for(d) for d in self.selected_records('edit') if d[0]=='sequence']
        try:
            name='조합 편집본 '+str(1+sum(s.get('kind')=='composition' for s in self.project.edit_sequences))
            seq=combine_sequences(sequences,self.project.subtitles,{p:self.placement(p)['video'] for p in self.media.paths()},name)
            self.project.edit_sequences.append(seq);self.assign_edit_folder(seq['id']);self.mark_dirty();self.open_edit_sequence(seq['id'])
        except ValueError as exc:self.statusBar().showMessage(str(exc))

    def reorder_organized(self,area,direction):
        selected=self.selected_records(area)
        if not selected:return
        data=selected[0];row=self.record_for(data)
        if not row:return
        rows=self.organized_folders(area) if data[0]=='folder' else self.project.edit_sequences if data[0]=='sequence' else self.organized_references(area)
        parent=lambda r:r.get('parent') if data[0]=='folder' else self.project.edit_locations.get(r['id']) if data[0]=='sequence' else r.get('folder')
        siblings=[r for r in rows if parent(r)==parent(row)]
        index=siblings.index(row);target=index+direction
        if 0<=target<len(siblings):
            a,b=rows.index(row),rows.index(siblings[target]);rows[a],rows[b]=rows[b],rows[a];self.mark_dirty()

    def organizer_menu(self,tree,area,point):
        item=tree.itemAt(point)
        if item and not item.isSelected():tree.clearSelection();tree.setCurrentItem(item)
        menu=QMenu(self)
        menu.addAction('새 폴더',lambda:self.new_organized_folder(area))
        menu.addAction('이름 변경',lambda:self.rename_organized(area))
        menu.addAction('위로 이동',lambda:self.reorder_organized(area,-1))
        menu.addAction('아래로 이동',lambda:self.reorder_organized(area,1))
        menu.addAction('복사',lambda:self.copy_organized(area))
        paste=menu.addAction('붙여넣기',lambda:self.paste_organized(area));paste.setEnabled(bool(self.organizer_clipboard))
        menu.addAction('목록에서 삭제' if area=='library' else '목록에서 제거',lambda:self.delete_organized(area))
        if area=='edit':
            menu.addSeparator();menu.addAction('복사한 컷으로 새 편집본',self.new_edit_from_clipboard)
            menu.addAction('선택 자료로 새 편집본',self.edit_from_selected_assets)
            menu.addAction('선택 편집본 조합',self.compose_selected)
            menu.addAction('편집본 열기',lambda:self.organized_clicked(item,area) if item else None)
        else:menu.addAction('미디어 추가…',self.media.choose_files)
        menu.exec(tree.viewport().mapToGlobal(point))

    def edit_from_selected_assets(self):
        records=[self.record_for(d) for d in self.selected_records('edit') if d[0]=='asset']
        if records:self.create_labeled_edit([r['source'] for r in records],[r['name'] for r in records],self.current_folder('edit'))
    def labeled_insert(self,seq,items,position,labels):
        candidate=insert_sources(seq,items,position,self.project.subtitles,{p:self.placement(p)['video'] for p in self.media.paths()})
        start=position/1000;end=start+sum(d for _,d in items)
        groups=list(dict.fromkeys(c['group'] for c in candidate['clips'] if start-.0001<=c['at']<end-.0001 and c['start']==0 and 'source' in c))
        names=dict(zip(groups,labels))
        for c in candidate['clips']:
            if c['group'] in names:c['label']=names[c['group']]
        return validate_sequence(candidate)

    def create_labeled_edit(self,paths,labels=None,folder=None):
        if folder is None:folder=self.current_folder('edit')
        items=self.source_items(paths)
        seq=self.new_drop_sequence(items)
        if labels:
            seq=self.labeled_insert(dict(seq,clips=[],ranges=[]),items,0,labels)
        self.register_drop_media(items)
        self.project.edit_sequences.append(seq);self.project.edit_locations[seq['id']]=folder
        self.closed_sequence_ids.discard(seq['id']);self.mark_dirty();self.open_edit_sequence(seq['id'])
        return seq

    def drop_location(self,watched,position):
        tabs=self.timeline.sequence_tabs
        if watched is tabs or tabs.isAncestorOf(watched):
            point=tabs.mapFrom(watched,position.toPoint());index=tabs.tabAt(point)
            return 'tab',(self.active_document_id,tabs.tabData(index) if index>=0 else None)
        return super().drop_location(watched,position)

    def drop_target_folder(self,kind,target):
        if kind not in ('media','sequence') or not target:return None
        if target[0]=='folder':return target[3]
        record=self.record_for(target)
        if not record:return None
        return self.project.edit_locations.get(record['id']) if target[0]=='sequence' else record.get('folder')

    def handle_media_drop(self,paths,watched,position,labels=None):
        if not self.allow_project_switch():return False
        kind,target=self.drop_location(watched,position)
        uid=target[0] if kind=='tab' else target[1] if kind in ('media','sequence') and target else self.active_document_id
        if not self.activate_document(uid):return False
        try:
            folder=self.drop_target_folder(kind,target)
            if kind=='media':
                self._drop_library_folder=folder
                try:self.media.add_files(paths)
                finally:self._drop_library_folder=None
                self.sync_workspace_ui();return True
            items=self.source_items(paths)
            labels=labels or [self.media.display_name(p) for p,_ in items]
            if kind=='sequence' and (not target or target[0]!='sequence'):
                self.register_drop_media(items)
                for (path,_),name in zip(items,labels):self.project.edit_assets.append(dict(id=uuid4().hex,source=path,name=name,folder=folder))
                self.mark_dirty();return True
            key=target[1] if kind=='tab' else target[2] if kind=='sequence' and target else self.active_edit_id
            seq=next((s for s in self.project.edit_sequences if s['id']==key),None)
            if seq:
                at=target if kind=='timeline' else sequence_layout(seq)[2]
                candidate=self.labeled_insert(seq,items,at,labels)
                self.register_drop_media(items);self.open_edit_sequence(seq['id']);self.commit_sequence(candidate,'영상 추가')
            else:self.create_labeled_edit(paths,labels,folder)
            return True
        except (ValueError,OSError) as exc:self.statusBar().showMessage('자료 추가 실패: '+str(exc));return False

    def handle_organization_drop(self,data,watched,position):
        if not self.allow_project_switch():return False
        kind,target=self.drop_location(watched,position)
        uid=target[0] if kind=='tab' else target[1] if kind in ('media','sequence') and target else self.active_document_id
        payload=[];before=None;before_dirty=self.dirty
        try:
            for row in data:
                if not isinstance(row,(list,tuple)) or len(row)<3:raise ValueError('자료 드래그 정보가 올바르지 않습니다.')
                if not self.activate_document(row[1]):return False
                value=self.snapshot_organized(row)
                if value:payload.append((tuple(row),value))
            if not self.activate_document(uid):return False
            before=deepcopy(self.project);before_dirty=self.dirty
            folder=self.drop_target_folder(kind,target)
            if kind=='media' or kind=='sequence' and (not target or target[0]!='sequence'):
                area='library' if kind=='media' else 'edit'
                for row,value in payload:
                    sourcearea='library' if row[0]=='media' else row[2] if row[0]=='folder' else 'edit'
                    if row[1]==uid and sourcearea==area:
                        record=self.record_for(row)
                        if row[0]=='folder':
                            parent=folder
                            while parent:
                                if parent==record['id']:raise ValueError('폴더를 자기 안으로 옮길 수 없습니다.')
                                parent=next(r['parent'] for r in self.organized_folders(area) if r['id']==parent)
                            record['parent']=folder
                        elif row[0]=='sequence':self.project.edit_locations[record['id']]=folder
                        else:record['folder']=folder
                    else:self.install_organized_copy(value,area,folder)
                self.mark_dirty();return True
            flat=[]
            def flatten(value):
                if value['kind']=='folder':
                    for child in value['children']:flatten(child)
                else:flat.append(value)
            for _,value in payload:flatten(value)
            if len(flat)==1 and flat[0]['kind']=='sequence' and kind=='tab' and target[1] is None and payload[0][0][1]==uid:
                self.open_edit_sequence(flat[0]['row']['id']);return True
            parts=[];allitems=[]
            for value in flat:
                row=value['row']
                if value['kind']=='sequence':
                    parts.append(row);allitems+=self.source_items(list(sequence_sources(row)))
                else:
                    items=self.source_items([row['source']]);allitems+=items
                    part=self.new_drop_sequence(items);part=self.labeled_insert(dict(part,clips=[],ranges=[]),items,0,[row['name']]);part['name']=row['name'];parts.append(part)
            if not parts:return False
            key=target[1] if kind=='tab' else target[2] if kind=='sequence' and target else self.active_edit_id
            seq=next((s for s in self.project.edit_sequences if s['id']==key),None)
            self.register_drop_media(allitems)
            offsets={p:self.placement(p)['video'] for p in self.media.paths()}
            if seq:
                from app.features.silence.sequence import splice_sequence
                at=sequence_layout(seq)[2]
                candidate=splice_sequence(seq,parts,at,self.project.subtitles,offsets)
                if seq.get('kind')!='composition' and all(v['kind']!='sequence' for v in flat):
                    candidate.pop('kind',None);candidate.pop('components',None)
                self.open_edit_sequence(seq['id']);self.commit_sequence(candidate,'편집본 추가 · 독립 복사')
                self.timeline.follow_playhead=True
                if self.preview.ready:self.preview.seek_timeline(at)
                else:self.pending_seek=(at,False)
                self.timeline.set_position(at)
            else:
                seq=combine_sequences(parts,self.project.subtitles,offsets,'조합 편집본' if any(v['kind']=='sequence' for v in flat) else '편집본 '+str(len(self.project.edit_sequences)+1))
                if all(v['kind']!='sequence' for v in flat):seq.pop('kind',None);seq.pop('components',None)
                self.project.edit_sequences.append(seq);self.assign_edit_folder(seq['id']);self.mark_dirty();self.open_edit_sequence(seq['id'])
            return True
        except (ValueError,OSError,KeyError,TypeError) as exc:
            if before is not None:
                for name,value in before.__dict__.items():setattr(self.project,name,value)
                self.dirty=before_dirty
                self.media.restore(before.media_paths,before.active_path,before.media_names)
                self.sync_sequence_tabs()
            self.statusBar().showMessage('자료 추가 실패: '+str(exc));return False


    def begin_timeline_edit(self):
        if self.active_sequence():return True
        if not self.preview.ready or self.subtitle_job.busy or not self.resolve_subtitle_edit():return False
        from app.features.silence.sequence import validate_sequence
        position=self.preview.timeline_position()
        selected_rows=[dict(r) for i,r in enumerate(self.timeline.canvas.segments) if i in self.timeline.canvas.selected_subtitles]
        scope=self.timeline.scope.currentIndex()
        if scope==1:
            self.refresh_sequence()
            sources=[(path,base/1000) for path,base,_ in self.sequence_items]
            position=self.timeline.canvas.position
        else:sources=[(self.media.selected_path(),0)]
        clips=[];durations={};linked=True
        for path,base in sources:
            if not path:continue
            duration=self.source_items([path])[0][1];durations[path]=duration
            placement=self.placement(path);linked=linked and placement['linked'];group=uuid4().hex
            for track in ('video','audio'):
                clips.append(dict(track=track,source=path,source_duration=duration,start=0.,end=duration,at=round(base+placement[track],3),group=group,label=self.media.display_name(path)))
        if not clips:return False
        number=1;names={s['name'] for s in self.project.edit_sequences}
        while f'편집본 {number}' in names:number+=1
        source=clips[0]['source']
        seq=validate_sequence(dict(id=uuid4().hex,name=f'편집본 {number}',source=source,duration=durations[source],clips=clips,ranges=[],linked=linked))
        self.project.edit_sequences.append(seq);self.assign_edit_folder(seq['id']);self.mark_dirty();self.open_edit_sequence(seq['id'])
        self.preview.seek_timeline(position)
        self.timeline.canvas.selected_subtitles={i for i,r in enumerate(self.timeline.canvas.segments) if any(r['text']==old['text'] and abs(r['start']-old['start'])<.002 for old in selected_rows)}
        self.statusBar().showMessage(seq['name']+'에서 편집을 시작합니다. Ctrl+K: 분할 · Shift+드래그: 뒤 컷 함께 이동')
        return True

    def request_timeline_split(self):
        if self.timeline.canvas.drag or self.timeline.canvas.navigation:return
        try:
            if self.begin_timeline_edit():self.split_sequence_clip()
        except (ValueError,OSError) as exc:self.statusBar().showMessage('편집 시작 실패: '+str(exc))
    def timeline_range_selected(self,blocks,subtitles,additive=False):
        if not self.resolve_subtitle_edit():return
        canvas=self.timeline.canvas
        canvas.individual_selection=False
        old_keys=set(canvas.selected_keys) if additive else set()
        old_subtitles=set(canvas.selected_subtitles) if additive else set()
        was_edit=bool(self.active_sequence())
        rows=[canvas.segments[i] for i in subtitles if i<len(canvas.segments)]
        if self.preview._playing:self.preview.toggle_play()
        if blocks and not was_edit and not self.begin_timeline_edit():return
        seq=self.active_sequence()
        if seq:
            clips=sequence_clips(seq)
            if was_edit:keys={key for track,key,_,_ in blocks}
            else:keys={i for i,c in enumerate(clips) for track,key,start,end in blocks if c['track']==track and abs(round(c['at']*1000)-start)<=1 and abs(round((c['at']+c['end']-c['start'])*1000)-end)<=1}
            keys|=old_keys
            if seq.get('linked',True):
                groups={clips[i]['group'] for i in keys if i<len(clips)};keys|={i for i,c in enumerate(clips) if c['group'] in groups}
            canvas.selected_keys=keys
            canvas.selected_clip=next((i for track in ('video','audio') for i in sorted(keys) if clips[i]['track']==track),None)
            canvas.selected_track=clips[canvas.selected_clip]['track'] if canvas.selected_clip is not None else None
            self.timeline.split_button.setEnabled(bool(keys));self.timeline.delete_button.setEnabled(bool(keys or subtitles or old_subtitles))
            if was_edit:canvas.selected_subtitles=old_subtitles|set(subtitles)
            else:canvas.selected_subtitles={i for i,r in enumerate(canvas.segments) if any(r['text']==old['text'] and abs(r['start']-old['start'])<.002 and abs(r['end']-old['end'])<.002 for old in rows)}
            groups={clips[i]['group'] for i in keys}
            groups|={canvas.segments[i].get('owner') for i in canvas.selected_subtitles}
            canvas.selected_keys|={i for i,c in enumerate(clips) if c['group'] in groups and (seq.get('linked',True) or c['track']=='video')}
            canvas.selected_subtitles|={i for i,r in enumerate(canvas.segments) if r.get('owner') in groups}
            canvas.selected_clip=next(iter(canvas.selected_keys),None)
            canvas.selected_track=clips[canvas.selected_clip]['track'] if canvas.selected_clip is not None else None
            self.statusBar().showMessage(f'컷 {len({clips[i]["group"] for i in keys})}개 · 자막 {len(canvas.selected_subtitles)}개 선택')
        else:
            if subtitles:self.timeline_select(subtitles[0]) if self.timeline.scope.currentIndex()==1 else self.select_subtitle(subtitles[0])
            canvas.selected_subtitles=old_subtitles|set(subtitles)
            self.statusBar().showMessage(f'자막 {len(canvas.selected_subtitles)}개 선택 · Delete로 선택 자막 제거')
        canvas.update()

    def clear_workspace_selection(self):
        canvas=self.timeline.canvas
        canvas.selected_gap=None
        had_selection=bool(canvas.selected_keys or canvas.selected_subtitles or self.timeline.sequence_tree.selectedItems() or self.media.project_tree.selectedItems())
        canvas.selected_keys=set();canvas.selected_subtitles=set();canvas.selected_clip=None;canvas.selected_track=None
        canvas.individual_selection=False
        for tree in (self.timeline.sequence_tree,self.media.project_tree):tree.clearSelection()
        self.timeline.split_button.setEnabled(False);self.timeline.delete_button.setEnabled(False)
        if had_selection:self.statusBar().showMessage('선택 해제')
        canvas.update()

    def delete_timeline_selection(self,ripple=False):
        if self.active_sequence():self.delete_sequence_clip(ripple);return
        canvas=self.timeline.canvas
        if not canvas.selected_subtitles or not self.resolve_subtitle_edit():return
        source=self.media.selected_path()
        if self.timeline.scope.currentIndex()==1:
            # Keep the original cross-source subtitle workflow explicit.
            self.statusBar().showMessage('원본 자막을 지우려면 해당 영상을 선택하세요.');return
        self.remember_subtitles(source)
        self.project.subtitles[source]=[row for i,row in enumerate(self.project.subtitles.get(source,[])) if i not in canvas.selected_subtitles]
        canvas.selected_subtitles=set();self.mark_dirty();self.show_source_subtitles(force=True)
