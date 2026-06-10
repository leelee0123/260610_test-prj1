"""① 오디오 추출: ffmpeg로 16kHz 모노 MP3 생성, Whisper 25MB 제한 초과 시 분할."""
import json
import math
import subprocess
from pathlib import Path

from app.ffmpeg import ffmpeg, ffprobe

MAX_BYTES = 25 * 1024 * 1024


def _run(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"{args[0]} 실패: {result.stderr[-800:]}")
    return result.stdout


def _duration_sec(path: Path) -> float:
    out = _run([
        ffprobe(), "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ])
    return float(out.strip())


def _has_audio(path: Path) -> bool:
    result = subprocess.run(
        [ffprobe(), "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_type", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    return result.stdout.strip() == "audio"


def extract(job_dir: Path, report=lambda *a: None) -> list[dict]:
    """오디오를 추출하고 [{file, offset}] 청크 목록을 audio_chunks.json에 기록."""
    src = next(p for p in job_dir.glob("input.*"))
    if not _has_audio(src):
        raise RuntimeError("영상에 오디오 트랙이 없습니다. 음성이 포함된 영상을 업로드해 주세요.")
    audio = job_dir / "audio.mp3"
    report("ffmpeg로 오디오 추출 중 (16kHz 모노)")
    _run([
        ffmpeg(), "-y", "-i", str(src),
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k",
        str(audio),
    ])

    if audio.stat().st_size <= MAX_BYTES:
        chunks = [{"file": audio.name, "offset": 0.0}]
    else:
        total = _duration_sec(audio)
        n = math.ceil(audio.stat().st_size / MAX_BYTES)
        chunk_dur = total / n
        chunks = []
        for i in range(n):
            offset = i * chunk_dur
            part = job_dir / f"audio_{i:03d}.mp3"
            _run([
                ffmpeg(), "-y", "-i", str(audio),
                "-ss", f"{offset:.3f}", "-t", f"{chunk_dur:.3f}",
                "-c", "copy", str(part),
            ])
            chunks.append({"file": part.name, "offset": round(offset, 3)})

    (job_dir / "audio_chunks.json").write_text(
        json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return chunks
