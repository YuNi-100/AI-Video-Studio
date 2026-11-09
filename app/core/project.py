from dataclasses import dataclass, field


@dataclass
class Project:
    name: str = "Untitled Project"
    media_paths: list[str] = field(default_factory=list)
    active_path: str | None = None
    media_names: dict[str, str] = field(default_factory=dict)
    subtitles: dict[str, list[dict]] = field(default_factory=dict)
    subtitle_terms: str = ""
    subtitle_skip_silence: bool = False
    subtitle_runs: dict[str, dict] = field(default_factory=dict)
    media_placements: dict[str, dict] = field(default_factory=dict)

    edit_sequences: list[dict] = field(default_factory=list)

    library_folders: list[dict] = field(default_factory=list)
    library_items: list[dict] | None = None
    edit_folders: list[dict] = field(default_factory=list)
    edit_assets: list[dict] = field(default_factory=list)
    edit_locations: dict[str, str | None] = field(default_factory=dict)
    search_folders: list[dict] = field(default_factory=list)
    search_locations: dict[str, str] = field(default_factory=dict)

    def rename(self, name: str) -> bool:
        name = name.strip()
        if not name or len(name) > 80:
            return False
        self.name = name
        return True


def validate_display_name(value):
    if not isinstance(value, str):
        raise ValueError("표시 이름은 문자열이어야 합니다.")
    value = value.strip()
    if not value or len(value) > 120 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("표시 이름은 1~120자의 한 줄로 입력하세요.")
    return value


def validate_placement(value):
    import math
    if not isinstance(value, dict):
        raise ValueError("타임라인 배치 정보가 올바르지 않습니다.")
    result = {}
    for key in ("video", "audio"):
        number = value.get(key, 0)
        if type(number) not in (int, float) or not math.isfinite(number) or not 0 <= number <= 604800:
            raise ValueError("클립 시작 위치는 0~604800초 범위여야 합니다.")
        result[key] = round(float(number), 3)
    linked = value.get("linked", True)
    if type(linked) is not bool:
        raise ValueError("영상·음성 연결 설정이 올바르지 않습니다.")
    result["linked"] = linked
    return result
