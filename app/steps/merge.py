"""⑥ 메타데이터 통합 → metadata.json

장면 타임코드 + GPT 분석 + 구간 자막 + 영상 기본 정보(ffprobe)를 하나로 묶는다.
"""
import json
import subprocess
from pathlib import Path

from app.ffmpeg import ffprobe
from app.srt_utils import parse_srt


def _video_meta(src: Path) -> dict:
    cmd = [
        ffprobe(), "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-show_entries", "format=duration,size",
        "-of", "json", str(src),
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        raise RuntimeError(f"ffprobe 실패: {out.stderr[:400]}")
    data = json.loads(out.stdout)
    stream = data.get("streams", [{}])[0]
    fmt = data.get("format", {})
    num, den = stream.get("r_frame_rate", "0/1").split("/")
    fps = round(int(num) / int(den), 2) if int(den) else 0
    w, h = stream.get("width"), stream.get("height")
    return {
        "width": w, "height": h,
        "resolution": f"{w}x{h}",
        "fps": fps,
        "duration_sec": round(float(fmt.get("duration", 0)), 3),
        "size_bytes": int(fmt.get("size", 0)),
    }


def _tc_to_sec(tc: str) -> float:
    h, m, rest = tc.strip().split(":")
    s, ms = rest.replace(".", ",").split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def _subs_for_scene(entries: list[dict], start_sec: float, end_sec: float) -> list[dict]:
    out = []
    for e in entries:
        tc_s, tc_e = e["timecode"].split(" --> ")
        if _tc_to_sec(tc_s) < end_sec and _tc_to_sec(tc_e) > start_sec:
            out.append({"index": e["index"], "timecode": e["timecode"], "text": e["text"]})
    return out


def merge(job_dir: Path, report=lambda *a: None) -> dict:
    report("메타데이터 통합 중…")

    src = next(p for p in job_dir.glob("input.*"))
    status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))

    analysis_path = job_dir / "analysis.json"
    if analysis_path.exists():
        scenes_source = json.loads(analysis_path.read_text(encoding="utf-8"))
        has_analysis = True
    else:
        scenes_source = json.loads((job_dir / "scenes.json").read_text(encoding="utf-8"))
        has_analysis = False

    corr = job_dir / "corrected.srt"
    orig = job_dir / "original.srt"
    entries = parse_srt((corr if corr.exists() else orig).read_text(encoding="utf-8"))

    scenes = [
        {
            "index": s["index"],
            "start": s["start"],
            "end": s["end"],
            "keyframe": s["keyframe"],
            "subtitles": _subs_for_scene(entries, s["start_sec"], s["end_sec"]),
            "analysis": s.get("analysis") if has_analysis else None,
        }
        for s in scenes_source
    ]

    metadata = {
        "video": {"filename": status["filename"], **_video_meta(src)},
        "scenes": scenes,
    }
    (job_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return metadata
