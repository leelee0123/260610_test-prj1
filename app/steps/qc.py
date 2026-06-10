"""⑦ 영상 QC 검사 → qc_report.json

ffmpeg 2패스로 4가지 품질 이슈를 감지한다.
패스 1 (비디오): 블랙 프레임 (blackdetect) + 스틸 구간 (freezedetect)
패스 2 (오디오): 무음 구간 (silencedetect) + 오디오 클리핑 (volumedetect)
"""
import json
import re
import subprocess
from pathlib import Path

from app.ffmpeg import ffmpeg


def _run_ffmpeg(args: list[str]) -> str:
    """ffmpeg를 실행하고 stderr를 반환 (분석 필터 결과는 모두 stderr에 출력됨)."""
    result = subprocess.run(
        args, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return result.stderr


def _parse_black(stderr: str) -> list[dict]:
    items = []
    for m in re.finditer(
        r"black_start:([\d.]+).*?black_end:([\d.]+).*?black_duration:([\d.]+)",
        stderr,
    ):
        items.append({"start": float(m.group(1)), "end": float(m.group(2)),
                      "duration": float(m.group(3))})
    return items


def _parse_freeze(stderr: str) -> list[dict]:
    items = []
    for m in re.finditer(
        r"freeze_start:([\d.]+).*?freeze_end:([\d.]+).*?freeze_duration:([\d.]+)",
        stderr,
    ):
        items.append({"start": float(m.group(1)), "end": float(m.group(2)),
                      "duration": float(m.group(3))})
    return items


def _parse_silence(stderr: str) -> list[dict]:
    starts: dict[int, float] = {}
    items = []
    for line in stderr.splitlines():
        ms = re.search(r"silence_start: ([\d.]+)", line)
        me = re.search(r"silence_end: ([\d.]+) \| silence_duration: ([\d.]+)", line)
        if ms:
            starts[len(starts)] = float(ms.group(1))
        if me and starts:
            idx = len(items)
            start = starts.get(idx, 0.0)
            items.append({"start": start, "end": float(me.group(1)),
                          "duration": float(me.group(2))})
    return items


def _parse_volume(stderr: str) -> float | None:
    m = re.search(r"max_volume: ([-\d.]+) dB", stderr)
    return float(m.group(1)) if m else None


def check(job_dir: Path, report=lambda *a: None) -> dict:
    src = next(p for p in job_dir.glob("input.*"))
    audio = job_dir / "audio.mp3"

    # 패스 1: 비디오 — 블랙 프레임 + 스틸 구간
    report("QC 검사 중 — 비디오 분석 (블랙 프레임·스틸 구간)")
    video_stderr = _run_ffmpeg([
        ffmpeg(), "-i", str(src),
        "-vf", "blackdetect=d=0.5:pic_th=0.98,freezedetect=n=0.001:d=2.0",
        "-f", "null", "-",
    ])
    black_frames = _parse_black(video_stderr)
    still_frames = _parse_freeze(video_stderr)

    # 패스 2: 오디오 — 무음 + 클리핑 (audio.mp3 없으면 건너뜀)
    silence: list[dict] = []
    max_volume_db: float | None = None
    clipping_risk = False

    if audio.exists():
        report("QC 검사 중 — 오디오 분석 (무음·클리핑)")
        audio_stderr = _run_ffmpeg([
            ffmpeg(), "-i", str(audio),
            "-af", "silencedetect=n=-40dB:d=0.5,volumedetect",
            "-f", "null", "-",
        ])
        silence = _parse_silence(audio_stderr)
        max_volume_db = _parse_volume(audio_stderr)
        clipping_risk = max_volume_db is not None and max_volume_db >= -1.0

    issue_count = len(black_frames) + len(still_frames) + len(silence) + (1 if clipping_risk else 0)
    report(f"QC 검사 완료 — 이슈 {issue_count}건")

    report_data = {
        "black_frames": black_frames,
        "still_frames": still_frames,
        "silence": silence,
        "max_volume_db": max_volume_db,
        "clipping_risk": clipping_risk,
        "issue_count": issue_count,
    }
    (job_dir / "qc_report.json").write_text(
        json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report_data
