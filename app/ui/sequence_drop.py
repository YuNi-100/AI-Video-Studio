"""Drop routing, cross-project media registration and multi-source insertion."""
from pathlib import Path
from uuid import uuid4
from PySide6.QtCore import Qt
from app.core.media import validate_video
from app.features.silence.sequence import validate_sequence,insert_sources,sequence_layout,sequence_clips


class SequenceDropWorkflow:
    def drop_location(self,watched,position):
        point=position.toPoint()
        for tree,kind in ((self.media.project_tree,'media'),(self.timeline.sequence_tree,'sequence')):
            if watched is tree or tree.isAncestorOf(watched):
                item=tree.itemAt(tree.viewport().mapFrom(watched,point))
                data=item.data(0,Qt.ItemDataRole.UserRole) if item else None
                return kind,data
        canvas=self.timeline.canvas
        if watched is canvas or canvas.isAncestorOf(watched):
            point=canvas.mapFrom(watched,point)
            return 'timeline',max(0,min(canvas.duration,canvas.value_at(point.x())))
        return 'media',None

    def source_items(self,paths):
        import av
        items=[]
        for path in paths:
            source=str(validate_video(path))
            duration=self.duration_cache.get(source,0)/1000
            if duration<=0:
                try:
                    container=av.open(source)
                except av.error.FFmpegError as exc:
                    raise ValueError('영상을 읽을 수 없습니다: '+Path(source).name) from exc
                with container:
                    if not container.streams.video:
                        raise ValueError('영상 트랙이 없는 파일입니다.')
                    duration=float(container.duration/av.time_base) if container.duration else max((float(s.duration*s.time_base) for s in container.streams if s.duration is not None and s.time_base),default=0)
            duration=round(duration,3)
            if not 0<duration<=604800:raise ValueError('영상 길이를 읽을 수 없습니다: '+Path(source).name)
            items.append((source,duration))
        return items

    def register_drop_media(self,items):
        paths=self.media.paths();names=self.media.names()
        for path,duration in items:
            if path not in paths:
                paths.append(path)
                alias=next((d['project'].media_names[path] for d in self.documents if path in d['project'].media_names),None)
                if alias:names[path]=alias
            self.duration_cache[path]=round(duration*1000)
        if len(paths)>10000:raise ValueError('프로젝트 미디어는 최대 10000개입니다.')
        selected=self.media.selected_path() or (paths[0] if paths else None)
        self.media.restore(paths,selected,names)
        self.project.media_paths=paths
        self.project.media_names=names
        self.project.active_path=selected

    def new_drop_sequence(self,items):
        if not items:raise ValueError('편집본에 넣을 영상이 없습니다.')
        if len(self.project.edit_sequences)>=1000:raise ValueError('편집본는 최대 1000개입니다.')
        number=1;names={s['name'] for s in self.project.edit_sequences}
        while f'편집 편집본 {number}' in names:number+=1
        path,duration=items[0]
        base=dict(id=uuid4().hex,name=f'편집 편집본 {number}',source=path,duration=duration,ranges=[],clips=[],linked=True)
        return insert_sources(base,items,0)

    def handle_media_drop(self,paths,watched,position):
        if not self.allow_project_switch():return False
        kind,target=self.drop_location(watched,position)
        try:
            target_uid=target[1] if kind in ('media','sequence') and target else self.active_document_id
            if not self.activate_document(target_uid):return False
            if kind=='media':
                self.media.add_files(paths)
                self.sync_workspace_ui()
                return True
            items=self.source_items(paths)
            if not items:return False
            seq=None
            base=[]
            if kind=='sequence' and target and target[0]=='sequence':
                seq=next((s for s in self.project.edit_sequences if s['id']==target[2]),None)
            elif kind=='timeline':
                seq=self.active_sequence()
            if seq:
                position_ms=sequence_layout(seq)[2] if kind=='sequence' else target
                candidate=insert_sources(seq,items,position_ms)
                self.register_drop_media(items)
                index=next(i for i in range(self.timeline.sequence_tabs.count()) if self.timeline.sequence_tabs.tabData(i)==seq['id'])
                self.timeline.sequence_tabs.setCurrentIndex(index)
                self.commit_sequence(candidate,'영상 삽입 · 뒤 컷 함께 이동')
            else:
                # Original views remain untouched; insertion creates an editable copy.
                if kind=='sequence' and target and target[0]=='view':
                    selected=self.media.selected_path()
                    original=self.media.paths() if target[2]==1 else ([selected] if selected else [])
                    base=self.source_items(original)
                elif kind=='timeline':
                    selected=self.media.selected_path()
                    original=self.media.paths() if self.timeline.scope.currentIndex()==1 else ([selected] if selected else [])
                    base=self.source_items(original)
                if base:
                    candidate=self.new_drop_sequence(base)
                    at=sequence_layout(candidate)[2] if kind=='sequence' else target
                    candidate=insert_sources(candidate,items,at)
                else:candidate=self.new_drop_sequence(items)
                self.register_drop_media(items)
                self.project.edit_sequences.append(candidate)
                self.mark_dirty()
                index=next(i for i in range(self.timeline.sequence_tabs.count()) if self.timeline.sequence_tabs.tabData(i)==candidate['id'])
                self.timeline.sequence_tabs.setCurrentIndex(index)
                self.statusBar().showMessage(candidate['name']+' 생성 · 프로젝트를 저장하세요.')
            self.sync_workspace_ui()
            return True
        except (ValueError,OSError) as exc:
            self.statusBar().showMessage('영상 추가 실패: '+str(exc))
            return False
