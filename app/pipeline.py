"""①~⑥ 단계 오케스트레이션. 업로드 후 백그라운드에서 실행되며 status.json을 갱신한다.

mode="cloud"     → OpenAI Whisper API + GPT 교정 + GPT-4o 비전 분석
mode="onpremise" → faster-whisper 로컬 STT + NLLB 번역 + 장면 분석 건너뜀
"""
import json
import traceback
from pathlib import Path

from app.steps import analyze, audio, correct, merge, qc, scenes, transcribe
from app.steps import transcribe_local, translate

PIPELINE_CLOUD = [
    ("audio",      audio.extract),
    ("transcribe", transcribe.transcribe),
    ("correct",    correct.correct),
    ("scenes",     scenes.detect),
    ("analyze",    analyze.analyze),
    ("merge",      merge.merge),
    ("qc",         qc.check),
]

PIPELINE_ONPREMISE = [
    ("audio",      audio.extract),
    ("transcribe", transcribe_local.transcribe_local),
    ("correct",    translate.translate),
    ("scenes",     scenes.detect),
    # analyze는 건너뜀 — run()에서 직접 "skipped" 처리
    ("merge",      merge.merge),
    ("qc",         qc.check),
]


def _load(job_dir: Path) -> dict:
    return json.loads((job_dir / "status.json").read_text(encoding="utf-8"))


def _save(job_dir: Path, status: dict) -> None:
    (job_dir / "status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def run(job_dir: Path) -> None:
    status = _load(job_dir)
    mode = status.get("mode", "cloud")
    pipeline = PIPELINE_ONPREMISE if mode == "onpremise" else PIPELINE_CLOUD

    status["state"] = "processing"
    _save(job_dir, status)

    # 온프레미스 모드: analyze 단계를 미리 skipped로 표시
    if mode == "onpremise":
        status["steps"]["analyze"] = "skipped"
        _save(job_dir, status)

    for name, func in pipeline:
        status["steps"][name] = "running"
        status["progress"] = None
        _save(job_dir, status)

        def report(detail, lines=None, _name=name):
            status["progress"] = {"step": _name, "detail": detail, "lines": list(lines or [])[-4:]}
            _save(job_dir, status)

        try:
            func(job_dir, report)
        except Exception:
            status["steps"][name] = "error"
            status["state"] = "error"
            status["error"] = traceback.format_exc(limit=3)
            status["progress"] = None
            _save(job_dir, status)
            return
        status["steps"][name] = "done"
        status["progress"] = None
        _save(job_dir, status)

    status["state"] = "done"
    _save(job_dir, status)
