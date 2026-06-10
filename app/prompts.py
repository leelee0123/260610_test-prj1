"""사용자 정의 프롬프트 관리.

프롬프트는 BASE_DIR/prompts.json에 저장된다.
파일이 없거나 특정 키가 없으면 DEFAULTS 값을 사용한다.
"""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "whisper_prompt": (
        "안녕하세요. 다음은 인터뷰, 강의 또는 미디어 콘텐츠의 음성입니다."
    ),
    "correct_system": (
        "다음은 음성 인식(Whisper)으로 생성된 자막 목록입니다. "
        "오탈자·띄어쓰기·잘못 인식된 단어를 자연스럽게 교정하세요.\n"
        "규칙:\n"
        "- 의미 변경·번역·요약 금지. 텍스트만 교정합니다.\n"
        "- 문장을 합치거나 나누지 마세요. 항목 수와 index를 반드시 유지하세요.\n"
        "- 동음이의어·외래어·전문용어는 문맥에 맞는 표준 표기로 교정합니다.\n"
        "- 숫자·고유명사·영문 혼용 표기는 문맥에 맞는 표준 형식으로 교정합니다.\n"
        "- 고칠 것이 없으면 원문을 그대로 반환하세요."
    ),
    "analyze_system": (
        "당신은 영상 분석 전문가입니다. "
        "제공된 영상 프레임 이미지와 해당 구간 자막을 보고 아래 JSON 스키마에 따라 분석 결과를 반환하세요. "
        "모든 텍스트는 한국어로 작성하세요."
    ),
}

_PATH = BASE_DIR / "prompts.json"


def get_prompts() -> dict:
    if not _PATH.exists():
        return dict(DEFAULTS)
    stored = json.loads(_PATH.read_text(encoding="utf-8"))
    return {k: stored.get(k, v) for k, v in DEFAULTS.items()}


def save_prompts(data: dict) -> dict:
    merged = get_prompts()
    for k in DEFAULTS:
        if k in data and isinstance(data[k], str):
            merged[k] = data[k].strip() or DEFAULTS[k]
    _PATH.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    return merged
