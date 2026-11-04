from pathlib import Path


def validate_video(path):
    """Validate a local source without modifying its contents."""
    source = Path(path).expanduser().resolve()
    if source.suffix.lower() not in (".mp4", ".mov"):
        raise ValueError("MP4 또는 MOV 파일을 선택하세요.")
    if not source.is_file():
        raise ValueError("영상 파일을 찾을 수 없습니다. 이동 또는 삭제 여부를 확인하세요.")
    try:
        with source.open("rb") as stream:
            if not stream.read(1):
                raise ValueError("비어 있는 영상 파일입니다.")
    except OSError as exc:
        raise ValueError("파일을 읽을 수 없습니다. 접근 권한을 확인하세요.") from exc
    return source


def timecode(milliseconds):
    seconds = max(0, milliseconds) // 1000
    return f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"
