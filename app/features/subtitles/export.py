import os
import tempfile
from pathlib import Path
from app.features.subtitles.model import validate_segments


def srt_time(seconds):
    value = round(seconds * 1000)
    return f"{value // 3600000:02}:{value // 60000 % 60:02}:{value // 1000 % 60:02},{value % 1000:03}"


def make_srt(segments):
    rows = validate_segments(segments)
    if not rows:
        raise ValueError("내보낼 자막이 없습니다.")
    blocks = []
    for i, row in enumerate(rows, 1):
        if round(row["end"] * 1000) <= round(row["start"] * 1000):
            raise ValueError("1밀리초보다 짧은 자막 시간을 수정하세요.")
        text = "\n".join(line.strip() for line in row["text"].splitlines() if line.strip())
        blocks.append(f"{i}\n{srt_time(row['start'])} --> {srt_time(row['end'])}\n{text}")
    return "\n\n".join(blocks) + "\n"


def export_srt(segments, path):
    target = Path(path).resolve()
    if target.suffix.lower() != ".srt":
        raise ValueError("SRT 확장자로 저장하세요.")
    payload = make_srt(segments).encode("utf-8-sig")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".avs-srt-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except OSError as exc:
        raise ValueError(f"자막 파일 저장 실패: {exc}") from exc
    finally:
        if temporary and temporary.exists():
            temporary.unlink(missing_ok=True)
