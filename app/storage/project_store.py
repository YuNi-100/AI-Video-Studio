"""Versioned JSON storage. Media files are referenced, never copied or modified."""
import json
import os
import tempfile
from pathlib import Path
from app.features.subtitles.model import validate_segments, validate_hotwords
from app.core.project import Project, validate_display_name, validate_placement

from app.features.silence.sequence import validate_sequence, sequence_sources

from app.storage.organization import load_organization, dump_organization

FORMAT = "ai-video-studio"
MAX_SIZE = 16 * 1024 * 1024


def local_path(value, base):
    if not isinstance(value, str) or not value or len(value) > 32767 or "\0" in value:
        raise ValueError("잘못된 영상 경로입니다.")
    if value.startswith(("\\\\", "//")) or "://" in value:
        raise ValueError("프로젝트에는 로컬 영상 경로만 사용할 수 있습니다.")
    path = Path(value)
    if path.suffix.lower() not in (".mp4", ".mov"):
        raise ValueError("프로젝트에 지원되지 않는 영상 경로가 있습니다.")
    return str((base / path).resolve())


def load_project(path):
    source = Path(path).resolve()
    try:
        with source.open("rb") as stream:
            content = stream.read(MAX_SIZE + 1)
        if len(content) > MAX_SIZE:
            raise ValueError("프로젝트 파일이 너무 큽니다 (최대 16MB).")
        data = json.loads(content.decode("utf-8-sig"))
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise ValueError("AI Video Studio 프로젝트 파일이 아닙니다.")
        if type(data.get("version")) is not int or data["version"] != 1:
            raise ValueError("지원하지 않는 프로젝트 버전입니다.")
        project = Project()
        if not isinstance(data.get("name"), str) or not project.rename(data["name"]):
            raise ValueError("프로젝트 이름이 올바르지 않습니다.")
        paths = data.get("media_paths")
        if not isinstance(paths, list) or len(paths) > 10000:
            raise ValueError("미디어 목록이 올바르지 않습니다.")
        project.media_paths = list(dict.fromkeys(local_path(p, source.parent) for p in paths))
        active = data.get("active_path")
        project.active_path = local_path(active, source.parent) if active is not None else None
        if project.active_path is not None and project.active_path not in project.media_paths:
            raise ValueError("선택한 영상이 미디어 목록에 없습니다.")
        names = data.get("media_names", {})
        if not isinstance(names, dict) or len(names) > 10000:
            raise ValueError("영상 표시 이름 목록이 올바르지 않습니다.")
        for key, name in names.items():
            resolved = local_path(key, source.parent)
            if resolved not in project.media_paths:
                raise ValueError("표시 이름에 연결된 영상이 없습니다.")
            project.media_names[resolved] = validate_display_name(name)
        subtitles = data.get("subtitles", {})
        if not isinstance(subtitles, dict) or len(subtitles) > len(project.media_paths):
            raise ValueError("자막 데이터가 올바르지 않습니다.")
        for key, segments in subtitles.items():
            resolved = local_path(key, source.parent)
            if resolved not in project.media_paths:
                raise ValueError("자막의 원본 영상이 목록에 없습니다.")
            project.subtitles[resolved] = validate_segments(segments)
        project.subtitle_terms = validate_hotwords(data.get("subtitle_terms", ""))
        skip_silence = data.get("subtitle_skip_silence", False)
        if type(skip_silence) is not bool:
            raise ValueError("음성 구간 필터 설정이 올바르지 않습니다.")
        project.subtitle_skip_silence = skip_silence
        runs = data.get("subtitle_runs", {})
        if not isinstance(runs, dict) or len(runs) > len(project.media_paths):
            raise ValueError("자막 생성 정보가 올바르지 않습니다.")
        for key, info in runs.items():
            resolved = local_path(key, source.parent)
            if resolved not in project.media_paths or not isinstance(info, dict):
                raise ValueError("자막 생성 정보의 영상이 올바르지 않습니다.")
            if any(not isinstance(v, (str, bool)) or (isinstance(v, str) and len(v) > 2000) for v in info.values()):
                raise ValueError("자막 생성 정보가 올바르지 않습니다.")
            project.subtitle_runs[resolved] = info
        placements = data.get("media_placements", {})
        if not isinstance(placements, dict) or len(placements) > len(project.media_paths):
            raise ValueError("타임라인 배치 정보가 올바르지 않습니다.")
        for key, value in placements.items():
            resolved = local_path(key, source.parent)
            if resolved not in project.media_paths:
                raise ValueError("배치한 원본 영상이 목록에 없습니다.")
            project.media_placements[resolved] = validate_placement(value)
        sequences = data.get('edit_sequences', [])
        if not isinstance(sequences,list) or len(sequences)>1000:
            raise ValueError('시퀀스 목록이 올바르지 않습니다.')
        ids = set()
        for value in sequences:
            seq = validate_sequence(value)
            seq['source'] = local_path(seq['source'], source.parent)
            for clip in seq.get('clips',[]):
                if 'source' in clip:
                    clip['source']=local_path(clip['source'],source.parent)
            if not sequence_sources(seq)<=set(project.media_paths) or seq['id'] in ids:
                raise ValueError('시퀀스 원본 또는 ID가 올바르지 않습니다.')
            ids.add(seq['id'])
            project.edit_sequences.append(seq)
        load_organization(project,data,lambda p:local_path(p,source.parent))
        return project
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError(f"프로젝트를 읽을 수 없습니다: {exc}") from exc


def save_project(project, path):
    destination = Path(path).resolve()
    if destination.suffix.lower() != ".avsp":
        raise ValueError("프로젝트 저장 확장자는 .avsp여야 합니다.")
    if not project.name.strip() or len(project.name.strip()) > 80:
        raise ValueError("프로젝트 이름이 올바르지 않습니다.")
    paths = list(dict.fromkeys(local_path(p, destination.parent) for p in project.media_paths))
    active = local_path(project.active_path, destination.parent) if project.active_path else None
    if active is not None and active not in paths:
        raise ValueError("선택한 영상이 미디어 목록에 없습니다.")

    def portable(value):
        try:
            return os.path.relpath(value, destination.parent)
        except ValueError:  # Different Windows drive.
            return value

    data = {"format": FORMAT, "version": 1, "name": project.name.strip(),
            "media_paths": [portable(p) for p in paths],
            "active_path": portable(active) if active else None}
    names = {}
    for key, name in project.media_names.items():
        resolved = local_path(key, destination.parent)
        if resolved not in paths:
            raise ValueError("표시 이름에 연결된 영상이 없습니다.")
        names[portable(resolved)] = validate_display_name(name)
    data["media_names"] = names
    subtitles = {}
    for key, segments in project.subtitles.items():
        resolved = local_path(key, destination.parent)
        if resolved not in paths:
            raise ValueError("자막의 원본 영상이 목록에 없습니다.")
        subtitles[portable(resolved)] = validate_segments(segments)
    data["subtitles"] = subtitles
    data["subtitle_terms"] = validate_hotwords(project.subtitle_terms)
    if type(project.subtitle_skip_silence) is not bool:
        raise ValueError("음성 구간 필터 설정이 올바르지 않습니다.")
    data["subtitle_skip_silence"] = project.subtitle_skip_silence
    data["media_placements"] = {portable(k): validate_placement(v) for k, v in project.media_placements.items() if k in paths}
    data["subtitle_runs"] = {portable(k): v for k, v in project.subtitle_runs.items() if k in paths}
    if len(project.edit_sequences)>1000:
        raise ValueError('시퀀스는 최대 1000개입니다.')
    sequences, ids = [], set()
    for value in project.edit_sequences:
        seq = validate_sequence(value)
        if not sequence_sources(seq)<=set(paths) or seq['id'] in ids:
            raise ValueError('시퀀스 원본 또는 ID가 올바르지 않습니다.')
        ids.add(seq['id'])
        seq['source'] = portable(seq['source'])
        for clip in seq.get('clips',[]):
            if 'source' in clip:
                clip['source']=portable(clip['source'])
        sequences.append(seq)
    data['edit_sequences'] = sequences
    data.update(dump_organization(project,portable))
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    if len(paths) > 10000 or len(payload) > MAX_SIZE:
        raise ValueError("프로젝트 크기 제한을 초과했습니다.")
    temporary = None
    try:
        # Write alongside the destination so replacement stays on one filesystem.
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".avs-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except OSError as exc:
        raise ValueError(f"프로젝트를 저장할 수 없습니다: {exc}") from exc
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink(missing_ok=True)
