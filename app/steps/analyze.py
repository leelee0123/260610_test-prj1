"""⑤ 장면별 GPT 비전 분석

각 장면의 키프레임(base64) + 해당 구간 교정 자막을 GPT-4o에 전달.
structured output으로 summary / elements / mood / subtitle_relevance 반환.
"""
import base64
import json
from pathlib import Path

from openai import OpenAI

from app.prompts import get_prompts
from app.srt_utils import parse_srt

MODEL = "gpt-4o"

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "장면의 핵심 내용을 1~2문장으로 요약"
        },
        "elements": {
            "type": "array",
            "items": {"type": "string"},
            "description": "화면에 보이는 주요 시각적 요소 목록 (인물, 사물, 배경 등)"
        },
        "mood": {
            "type": "string",
            "description": "장면의 전반적인 분위기나 감정 (예: 활기찬, 고요한, 긴장된)"
        },
        "subtitle_relevance": {
            "type": "string",
            "description": "자막 내용이 화면과 얼마나 일치하는지 설명 (자막이 없으면 '자막 없음')"
        },
    },
    "required": ["summary", "elements", "mood", "subtitle_relevance"],
    "additionalProperties": False,
}


def _encode_image(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode()


def _subtitles_for_scene(entries: list[dict], start_sec: float, end_sec: float) -> str:
    lines = [
        e["text"] for e in entries
        if _tc_to_sec(e["timecode"].split(" --> ")[0]) < end_sec
        and _tc_to_sec(e["timecode"].split(" --> ")[1]) > start_sec
    ]
    return "\n".join(lines) if lines else ""


def _tc_to_sec(tc: str) -> float:
    # HH:MM:SS,mmm
    h, m, rest = tc.strip().split(":")
    s, ms = rest.replace(".", ",").split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def analyze(job_dir: Path, report=lambda *a: None) -> list[dict]:
    scenes = json.loads((job_dir / "scenes.json").read_text(encoding="utf-8"))
    corr_path = job_dir / "corrected.srt"
    orig_path = job_dir / "original.srt"
    srt_path = corr_path if corr_path.exists() else orig_path
    entries = parse_srt(srt_path.read_text(encoding="utf-8")) if srt_path.exists() else []

    client = OpenAI()
    results = []

    for scene in scenes:
        report(f"장면 {scene['index']}/{len(scenes)} GPT 분석 중…", [s.get("summary", "") for s in results])
        kf = job_dir / "keyframes" / scene["keyframe"]
        img_b64 = _encode_image(kf)
        subs = _subtitles_for_scene(entries, scene["start_sec"], scene["end_sec"])
        user_content = [
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}", "detail": "low"},
            },
            {
                "type": "text",
                "text": (
                    f"장면 {scene['index']} / 구간: {scene['start']} → {scene['end']}\n"
                    f"자막:\n{subs if subs else '(없음)'}"
                ),
            },
        ]
        res = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": get_prompts()["analyze_system"]},
                {"role": "user", "content": user_content},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "scene_analysis", "strict": True, "schema": SCHEMA},
            },
            max_tokens=512,
        )
        analysis = json.loads(res.choices[0].message.content)
        results.append({**scene, "analysis": analysis})
        report(
            f"장면 {scene['index']}/{len(scenes)} 완료",
            [r["analysis"]["summary"] for r in results],
        )

    (job_dir / "analysis.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return results
