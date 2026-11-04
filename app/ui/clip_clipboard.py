from pathlib import Path
from uuid import uuid4
from copy import deepcopy
from app.features.clip_clipboard import copy_sets
from app.features.silence.sequence import sequence_sources, splice_sequence


class ClipClipboardWorkflow:
    def new_edit_from_clipboard(self):
        payload = getattr(self,'clip_clipboard',None)
        if not payload or not self.allow_project_switch():
            self.statusBar().showMessage('먼저 타임라인에서 컷을 선택하고 Ctrl+C로 복사하세요.')
            return
        try:
            if len(self.project.edit_sequences)>=1000:
                raise ValueError('편집본은 최대 1000개입니다.')
            paths = sequence_sources(payload)
            if any(not Path(p).is_file() for p in paths):
                raise ValueError('복사한 컷의 원본 파일을 찾을 수 없습니다.')
            if not paths <= set(self.media.paths()):
                self.register_drop_media(self.source_items(sorted(paths)))
            seq = deepcopy(payload)
            seq.update(id=uuid4().hex,name='붙여넣은 편집본 '+str(len(self.project.edit_sequences)+1))
            self.project.edit_sequences.append(seq)
            self.assign_edit_folder(seq['id'])
            self.mark_dirty()
            self.open_edit_sequence(seq['id'])
            self.statusBar().showMessage('복사한 컷으로 새 편집본 생성 · 다른 영상의 컷도 Ctrl+C / Ctrl+V로 추가하세요.')
        except (ValueError,OSError) as exc:
            self.statusBar().showMessage(str(exc))

    def copy_timeline_sets(self):
        if self.subtitle_job.busy or not self.resolve_subtitle_edit():
            return
        seq = self.active_sequence()
        if not seq:
            self.statusBar().showMessage('편집본에서 복사할 컷을 선택하세요.')
            return
        c = self.timeline.canvas
        try:
            self.clip_clipboard = copy_sets(seq,c.selected_keys,c.selected_subtitles,
                self.project.subtitles,{p:self.placement(p)['video'] for p in self.media.paths()})
            self.statusBar().showMessage('선택 컷과 영상·음성·소속 자막 복사 · 붙여넣을 편집본의 타임라인에서 Ctrl+V')
        except ValueError as exc:
            self.statusBar().showMessage(str(exc))

    def paste_timeline_sets(self):
        payload = getattr(self,'clip_clipboard',None)
        if not payload or self.subtitle_job.busy or not self.resolve_subtitle_edit():
            return
        if not self.active_sequence():
            self.statusBar().showMessage('붙여넣을 편집본을 먼저 열어 주세요. 원본 보기에서는 붙여넣지 않습니다.')
            return
        try:
            paths = sequence_sources(payload)
            if any(not Path(p).is_file() for p in paths):
                raise ValueError('복사한 컷의 원본 파일을 찾을 수 없습니다.')
            candidate = splice_sequence(self.active_sequence(),[payload],self.transport_position_value(),
                self.project.subtitles,{p:self.placement(p)['video'] for p in self.media.paths()})
            if not paths <= set(self.media.paths()):
                self.register_drop_media(self.source_items(sorted(paths)))
            self.commit_sequence(candidate,'컷 붙여넣기 · 뒤 컷 함께 이동')
        except (ValueError,OSError) as exc:
            self.statusBar().showMessage(str(exc))
