"""② (온프레미스) faster-whisper large-v3로 로컬 전사 → original.srt

검출된 언어 코드는 transcription_meta.json에 저장해 translate.py가 참조한다.
모델은 프로세스 수명 동안 1회만 로드한다.
"""
import json
import threading
from pathlib import Path

from app.device import get_device
from app.prompts import get_prompts
from app.srt_utils import sec_to_timecode, segments_to_srt

_model = None
_lock = threading.Lock()


def _get_model():
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                device, _, compute_type = get_device()
                from faster_whisper import WhisperModel
                _model = WhisperModel("large-v3", device=device, compute_type=compute_type)
    return _model


def transcribe_local(job_dir: Path, report=lambda *a: None):
    chunks = json.loads((job_dir / "audio_chunks.json").read_text(encoding="utf-8"))
    _, label, _ = get_device()
    report(f"로컬 STT 초기화 중 ({label})")
    model = _get_model()
    segments_out = []
    preview = []
    detected_lang = "unknown"

    for i, chunk in enumerate(chunks):
        report(f"로컬 STT 전사 중 — 오디오 {i + 1}/{len(chunks)} ({label})", preview)
        audio_path = str(job_dir / chunk["file"])
        segs, info = model.transcribe(
            audio_path,
            beam_size=5,
            initial_prompt=get_prompts()["whisper_prompt"],
        )
        if i == 0:
            detected_lang = info.language  # BCP-47 코드 (예: "en", "ja", "ko")

        for seg in segs:
            text = seg.text.strip()
            if not text:
                continue
            start = seg.start + chunk["offset"]
            end = seg.end + chunk["offset"]
            segments_out.append({"start": start, "end": end, "text": text})
            preview.append(f"{sec_to_timecode(start)}  {text}")
            report(f"로컬 STT 전사 중 — 오디오 {i + 1}/{len(chunks)} ({label})", preview)

    if not segments_out:
        raise RuntimeError("음성이 인식되지 않았습니다. 영상에 음성이 포함되어 있는지 확인하세요.")

    (job_dir / "original.srt").write_text(segments_to_srt(segments_out), encoding="utf-8")
    (job_dir / "transcription_meta.json").write_text(
        json.dumps({"language": detected_lang}, ensure_ascii=False), encoding="utf-8"
    )
    return segments_out
