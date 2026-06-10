"""③ GPT 자막 교정 → corrected.srt

타임코드는 GPT에 전달하지 않는다. 텍스트만 index와 함께 보내 교정받고,
SRT는 원본에서 파싱한 타임코드로 코드가 재조립한다 → 타임코드 수정이 구조적으로 불가능.
"""
import json
from pathlib import Path

from openai import OpenAI

from app.prompts import get_prompts
from app.srt_utils import entries_to_srt, parse_srt

MODEL = "gpt-4o-mini"
BATCH = 50

SCHEMA = {
    "type": "object",
    "properties": {
        "corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "text": {"type": "string"},
                },
                "required": ["index", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["corrections"],
    "additionalProperties": False,
}


def correct(job_dir: Path, report=lambda *a: None):
    entries = parse_srt((job_dir / "original.srt").read_text(encoding="utf-8"))
    client = OpenAI()
    corrected = {}
    preview = []
    batches = [entries[i:i + BATCH] for i in range(0, len(entries), BATCH)]

    for bi, batch in enumerate(batches):
        report(f"GPT 자막 교정 중 — 배치 {bi + 1}/{len(batches)}", preview)
        payload = [{"index": e["index"], "text": e["text"]} for e in batch]
        res = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": get_prompts()["correct_system"]},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "subtitle_corrections", "strict": True, "schema": SCHEMA},
            },
        )
        data = json.loads(res.choices[0].message.content)
        valid = {e["index"] for e in batch}
        for c in data["corrections"]:
            if c["index"] in valid and c["text"].strip():
                corrected[c["index"]] = c["text"].strip()
        # 응답에서 누락된 index는 corrected에 없으므로 아래 재조립에서 원문 유지(폴백)
        for e in batch:
            new = corrected.get(e["index"], e["text"])
            if new != e["text"]:
                preview.append(f"{e['text']}  →  {new}")
        report(f"GPT 자막 교정 중 — 배치 {bi + 1}/{len(batches)} 완료", preview)

    out = [
        {"index": e["index"], "timecode": e["timecode"], "text": corrected.get(e["index"], e["text"])}
        for e in entries
    ]
    (job_dir / "corrected.srt").write_text(entries_to_srt(out), encoding="utf-8")

    # 타임코드 보존 자동 검증
    after = parse_srt((job_dir / "corrected.srt").read_text(encoding="utf-8"))
    if [e["timecode"] for e in entries] != [e["timecode"] for e in after]:
        raise RuntimeError("타임코드 보존 검증 실패: 원본과 교정본의 타임코드가 다릅니다.")
    return out
