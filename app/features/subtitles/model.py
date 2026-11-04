import math


def validate_segments(segments):
    if not isinstance(segments, list) or len(segments) > 50000:
        raise ValueError("자막 목록 크기가 올바르지 않습니다.")
    result = []
    previous = 0.0
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError("잘못된 자막 항목입니다.")
        start, end, text = segment.get("start"), segment.get("end"), segment.get("text")
        if (type(start) not in (int, float) or type(end) not in (int, float)
                or not math.isfinite(start) or not math.isfinite(end)
                or start < previous or end <= start
                or not isinstance(text, str) or not text.strip() or len(text) > 4000):
            raise ValueError("자막 시간 또는 내용이 올바르지 않습니다.")
        row = {"start": float(start), "end": float(end), "text": text.strip()}
        if "reviewed" in segment:
            if type(segment["reviewed"]) is not bool:
                raise ValueError("검수 상태가 올바르지 않습니다.")
            row["reviewed"] = segment["reviewed"]
        for key in ("avg_logprob", "no_speech_prob"):
            if key in segment:
                value = segment[key]
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError("인식 신뢰 정보가 올바르지 않습니다.")
                row[key] = float(value)
        result.append(row)
        previous = start
    return result


def subtitle_time(seconds):
    ms = round(seconds * 1000)
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}.{ms % 1000:03}"


def validate_hotwords(value):
    if not isinstance(value, str) or len(value) > 400 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("이름·용어 힌트는 400자 이하의 한 줄로 입력하세요.")
    return value.strip()
