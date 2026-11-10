"""Timeline view, linked clip placement, sequential playback and caption editing."""
from copy import deepcopy
from PySide6.QtCore import QSignalBlocker, QTimer


class TimelineWorkflow:

    def placement(self, path):
        return self.project.media_placements.get(path, {"video":0.,"audio":0.,"linked":True})

    def change_link(self, checked):
        if self.active_sequence():
            self.change_sequence_link(checked)
            return
        source = self.media.selected_path()
        if not source or not self.resolve_subtitle_edit():
            self.show_source_subtitles()
            return
        self.remember_subtitles(source)
        placement = dict(self.placement(source),linked=checked)
        if checked:
            placement["audio"] = placement["video"]
        self.project.media_placements[source] = placement
        self.mark_dirty()
        self.show_source_subtitles()
        self.statusBar().showMessage("영상·음성을 같은 위치로 연결했습니다." if checked else "연결 해제 · 영상과 음성을 따로 드래그할 수 있습니다.")

    def move_timeline_block(self, track, key, target):
        if self.subtitle_job.busy or not self.resolve_subtitle_edit():
            self.show_source_subtitles()
            return
        source = self.media.selected_path()
        if self.timeline.scope.currentIndex() == 1:
            if track == "subtitle":
                source,key,base = self.sequence_cues[key]
            else:
                source,base,length = self.sequence_items[key]
            target = max(0,target-base)
        if not source:
            return
        target = max(0,min(604800000,target))
        self.remember_subtitles(source)
        if track == "subtitle":
            rows = deepcopy(self.project.subtitles.get(source,[]))
            if not 0 <= key < len(rows):
                return
            item = rows[key]
            length = item["end"]-item["start"]
            item.update(start=target/1000,end=round(target/1000+length,3),reviewed=False)
            rows.sort(key=lambda row:row["start"])
            self.project.subtitles[source] = rows
        else:
            placement = dict(self.placement(source))
            delta = target/1000-placement[track]
            if placement["linked"]:
                delta = max(delta,-min(placement["video"],placement["audio"]))
                for field in ("video","audio"):
                    placement[field] = round(placement[field]+delta,3)
            else:
                placement[track] = round(target/1000,3)
            self.project.media_placements[source] = placement
        if source != self.media.selected_path():
            self.media.restore(self.media.paths(),source,self.media.names())
            self.open_media(source)
        self.mark_dirty()
        self.show_source_subtitles(force=True)
        self.statusBar().showMessage("이동 적용 · 되돌리기 가능 · 자막은 별도로 이동합니다. 저장하세요.")

    def scope_changed(self, *_):
        if not self.resolve_subtitle_edit():
            with QSignalBlocker(self.timeline.scope):
                self.timeline.scope.setCurrentIndex(1-self.timeline.scope.currentIndex())
            return
        self.show_source_subtitles()

    def refresh_sequence(self):
        import av
        items,blocks,cues,mapping = [],[],[],[]
        base = 0
        for path in self.media.paths():
            length = self.duration_cache.get(path)
            if length is None:
                try:
                    with av.open(path) as container:
                        length = round(container.duration/1000) if container.duration else 0
                    self.duration_cache[path] = length
                except (OSError,ValueError,av.error.FFmpegError):
                    length = 0
            if length <= 0:
                continue
            placement = self.placement(path)
            rows = self.project.subtitles.get(path,[])
            extent = max(round(max(placement["video"],placement["audio"])*1000)+length,
                         max((round(row["end"]*1000) for row in rows),default=0))
            index = len(items)
            items.append((path,base,extent))
            for track in ("video","audio"):
                start = base+round(placement[track]*1000)
                blocks.append((track,start,start+length,self.media.display_name(path),index))
            for row_index,row in enumerate(rows):
                cues.append(dict(row,start=row["start"]+base/1000,end=row["end"]+base/1000))
                mapping.append((path,row_index,base))
            base += extent
        self.sequence_items,self.sequence_cues = items,mapping
        self.timeline.canvas.duration = base
        self.timeline.canvas.blocks = blocks
        self.timeline.canvas.segments = cues
        self.timeline.info.setText(f"전체 {len(items)}개 · 목록 순서 · 개별 수정 공유")
        self.timeline.update_scroll()
        self.timeline.canvas.update()

    def transport_position(self, position):
        if self.active_sequence():
            self.timeline.set_position(position)
            return
        if not hasattr(self,"timeline"):
            return
        if self.timeline.scope.currentIndex() == 1:
            current = str(self.preview.source)
            for i,(path,base,length) in enumerate(self.sequence_items):
                if path == current:
                    self.timeline.set_position(base+position)
                    return
        self.timeline.set_position(position)

    def advance_sequence(self, index):
        self.switch_queued = False
        if self.timeline.scope.currentIndex() == 1 and index < len(self.sequence_items):
            self.seek_transport(self.sequence_items[index][1],resume=True)

    def transport_position_value(self):
        if self.active_sequence():
            return self.preview.timeline_position()
        if self.timeline.scope.currentIndex() == 1:
            return self.timeline.canvas.position
        return self.preview.timeline_position()

    def transport_duration_value(self):
        if self.active_sequence():
            return self.preview.timeline_duration()
        return self.timeline.canvas.duration if self.timeline.scope.currentIndex() == 1 else self.preview.timeline_duration()

    def seek_transport(self, position, resume=None):
        if self.active_sequence() or self.timeline.scope.currentIndex() == 0:
            self.preview.seek_timeline(position)
            return
        position = max(0,min(position,self.timeline.canvas.duration))
        for i,(path,base,length) in enumerate(self.sequence_items):
            if base <= position < base+length or i == len(self.sequence_items)-1:
                local = max(0,min(length,position-base))
                if path == str(self.preview.source):
                    if not self.preview.ready:
                        playing = (self.pending_seek[1] if self.pending_seek is not None else False) if resume is None else resume
                        self.pending_seek = (local,playing)
                    else:
                        self.preview.seek_timeline(local)
                        if resume and not self.preview._playing:
                            self.preview.toggle_play()
                elif not self.subtitle_job.busy and self.resolve_subtitle_edit():
                    playing = self.preview._playing if resume is None else resume
                    self.pending_seek = (local,playing)
                    self.media.restore(self.media.paths(),path,self.media.names())
                    self.open_media(path)
                return

    def timeline_select(self, index):
        if self.timeline.scope.currentIndex() == 0:
            self.select_subtitle(index)
            return
        if not 0 <= index < len(self.sequence_cues) or not self.resolve_subtitle_edit():
            return
        source,row,base = self.sequence_cues[index]
        self.seek_transport(round(self.project.subtitles[source][row]["start"]*1000)+base,resume=False)
        self.subtitle_panel.editor.set_selection(row)
        self.subtitle_panel.tabs.setCurrentIndex(1)

    def transport_finished(self):
        if self.active_sequence():
            return
        if self.subtitle_job.busy:
            return
        if self.timeline.scope.currentIndex() == 1:
            for i,(path,base,length) in enumerate(self.sequence_items[:-1]):
                if path == str(self.preview.source) and not self.switch_queued:
                    self.switch_queued = True
                    QTimer.singleShot(0,self,lambda index=i+1,project=self.project:self.advance_sequence(index) if self.project is project else None)
                    break

    def reorder_media(self, delta):
        if self.subtitle_job.busy or not self.resolve_subtitle_edit():
            return
        paths = self.media.paths()
        source = self.media.selected_path()
        if source not in paths:
            return
        index = paths.index(source)
        target = index+delta
        if 0 <= target < len(paths):
            paths[index],paths[target] = paths[target],paths[index]
            self.media.restore(paths,source,self.media.names())
            self.mark_dirty()
            self.show_source_subtitles()
            self.statusBar().showMessage("영상 순서를 변경했습니다. 앞 순서·뒤 순서 버튼으로 다시 조정할 수 있습니다. 저장하세요.")

    def toggle_transport(self):
        if self.active_sequence():
            self.preview.toggle_play()
            return
        if self.timeline.scope.currentIndex() == 1 and not self.preview._playing and self.transport_position_value() >= self.transport_duration_value():
            self.seek_transport(0,resume=True)
        else:
            self.preview.toggle_play()

    def resize_timeline_subtitle(self, key, start, end):
        if self.subtitle_job.busy:
            self.show_source_subtitles()
            return
        source = self.media.selected_path()
        if self.timeline.scope.currentIndex() == 1:
            if not 0 <= key < len(self.sequence_cues):
                return
            source,key,base = self.sequence_cues[key]
            start,end = start-base,end-base
        rows = self.project.subtitles.get(source,[])
        if not source or not 0 <= key < len(rows):
            return
        # Capture the intended cue before resolving any pending editor changes.
        target = rows[key]
        if not self.resolve_subtitle_edit():
            self.show_source_subtitles()
            return
        rows = self.project.subtitles.get(source,[])
        if target not in rows:
            self.show_source_subtitles()
            self.statusBar().showMessage("수정 적용으로 자막이 바뀌었습니다. 다시 드래그해 주세요.")
            return
        key = rows.index(target)
        start = max(0,start)
        minimum = min(100,round((rows[key]["end"]-rows[key]["start"])*1000))
        end = max(start+max(1,minimum),end)
        if (round(rows[key]["start"]*1000),round(rows[key]["end"]*1000)) == (start,end):
            return
        self.remember_subtitles(source)
        rows = deepcopy(rows)
        item = rows[key]
        item.update(start=start/1000,end=end/1000,reviewed=False)
        rows.sort(key=lambda row:row["start"])
        selected = next(i for i,row in enumerate(rows) if row is item)
        self.project.subtitles[source] = rows
        if source != self.media.selected_path():
            self.media.restore(self.media.paths(),source,self.media.names())
            self.open_media(source)
        self.mark_dirty()
        self.show_source_subtitles(select=selected,force=True)
        self.subtitle_panel.tabs.setCurrentIndex(1)
        self.statusBar().showMessage("자막 시간을 조정했습니다. Ctrl+Z로 취소 · 프로젝트를 저장하세요.")

    def begin_timeline_scrub(self):
        if self._scrubbing:
            return
        self._scrubbing = True
        self._scrub_target = None
        self._scrub_resume = self.preview._playing
        if self.preview._playing:
            self.preview.toggle_play()
        self._scrub_timer.start()

    def select_playhead_video(self, position):
        seq=self.active_sequence()
        if not seq:return
        from app.features.silence.sequence import sequence_clips
        canvas=self.timeline.canvas;clips=sequence_clips(seq)
        index=next((i for i,c in enumerate(clips) if c['track']=='video' and round(c['at']*1000)<=position<round((c['at']+c['end']-c['start'])*1000)),None)
        canvas.selected_gap=None;canvas.individual_selection=False
        canvas.selected_clip=index;canvas.selected_track='video' if index is not None else None
        group=clips[index]['group'] if index is not None else None
        canvas.selected_keys={i for i,c in enumerate(clips) if i==index or (group is not None and seq.get('linked',True) and c['group']==group)}
        canvas.selected_subtitles={i for i,row in enumerate(canvas.segments) if group is not None and row.get('owner')==group}
        self.timeline.split_button.setEnabled(index is not None)
        self.timeline.delete_button.setEnabled(index is not None)
        canvas.update()

    def request_timeline_seek(self, position):
        if self._scrubbing:
            self._scrub_target = position
            self.timeline.set_position(position)
        else:
            self.seek_transport(position)

    def flush_timeline_seek(self):
        target,self._scrub_target = self._scrub_target,None
        if target is not None:
            self.seek_transport(target,resume=False)

    def end_timeline_scrub(self):
        if not self._scrubbing:
            return
        self._scrub_timer.stop()
        self.flush_timeline_seek()
        resume = self._scrub_resume
        self._scrubbing = False
        self._scrub_resume = False
        if resume:
            if self.preview.ready and not self.preview._playing:
                self.preview.toggle_play()
            elif self.pending_seek is not None:
                self.pending_seek = (self.pending_seek[0],True)

    def abort_timeline_scrub(self):
        self._scrub_timer.stop()
        self._scrubbing = False
        self._scrub_target = None
        self._scrub_resume = False
        self.timeline.canvas.navigation = None
        self.timeline.canvas.selection_origin=None
        self.timeline.canvas.selection_box=None
        self.timeline.canvas.preview_segments=None
