"""② Whisper API로 자막 생성 → original.srt"""
import json
from pathlib import Path

from openai import OpenAI

from app.prompts import get_prompts
from app.srt_utils import sec_to_timecode, segments_to_srt


def transcribe(job_dir: Path, report=lambda *a: None):
    chunks = json.loads((job_dir / "audio_chunks.json").read_text(encoding="utf-8"))
    client = OpenAI()
    segments = []
    preview = []

    for i, chunk in enumerate(chunks):
        report(f"Whisper 전사 중 — 오디오 {i + 1}/{len(chunks)}", preview)
        with (job_dir / chunk["file"]).open("rb") as f:
            res = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="verbose_json",
                prompt=get_prompts()["whisper_prompt"],
            )
        for seg in res.segments or []:
            text = seg.text.strip()
            if not text:
                continue
            start = seg.start + chunk["offset"]
            end = seg.end + chunk["offset"]
            segments.append({"start": start, "end": end, "text": text})
            preview.append(f"{sec_to_timecode(start)}  {text}")
            report(f"Whisper 전사 중 — 오디오 {i + 1}/{len(chunks)}", preview)

    if not segments:
        raise RuntimeError("음성이 인식되지 않았습니다. 영상에 음성이 포함되어 있는지 확인하세요.")

    (job_dir / "original.srt").write_text(segments_to_srt(segments), encoding="utf-8")
    return segments
