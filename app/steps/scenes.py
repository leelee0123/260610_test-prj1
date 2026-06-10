"""④ 장면 감지 + 키프레임 추출

PySceneDetect ContentDetector로 장면 경계를 찾고,
각 장면의 중간 프레임을 ffmpeg로 JPEG 추출한다.
"""
import json
import subprocess
from pathlib import Path

from scenedetect import SceneManager, open_video
from scenedetect.detectors import ContentDetector

from app.ffmpeg import ffmpeg


def _run(args: list[str]) -> None:
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(f"{args[0]} 실패: {result.stderr[-800:]}")


def detect(job_dir: Path, report=lambda *a: None) -> list[dict]:
    src = next(p for p in job_dir.glob("input.*"))
    frames_dir = job_dir / "keyframes"
    frames_dir.mkdir(exist_ok=True)

    report("장면 감지 중 (PySceneDetect)…")
    video = open_video(str(src))
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=27.0))
    sm.detect_scenes(video, show_progress=False)
    scene_list = sm.get_scene_list()

    if not scene_list:
        # 장면 변화 없으면 영상 전체를 1개 장면으로
        video2 = open_video(str(src))
        end_tc = video2.duration
        from scenedetect import FrameTimecode
        scene_list = [(FrameTimecode(0, video2.frame_rate), end_tc)]

    scenes = []
    for i, (start_tc, end_tc) in enumerate(scene_list):
        mid_sec = (start_tc.get_seconds() + end_tc.get_seconds()) / 2
        kf_path = frames_dir / f"scene_{i + 1:03d}.jpg"
        report(f"키프레임 추출 중 — {i + 1}/{len(scene_list)} 장면", scenes)
        _run([
            ffmpeg(), "-y", "-ss", f"{mid_sec:.3f}",
            "-i", str(src), "-frames:v", "1",
            "-q:v", "3", str(kf_path),
        ])
        scenes.append({
            "index": i + 1,
            "start": start_tc.get_timecode().replace(".", ","),
            "end": end_tc.get_timecode().replace(".", ","),
            "start_sec": round(start_tc.get_seconds(), 3),
            "end_sec": round(end_tc.get_seconds(), 3),
            "keyframe": kf_path.name,
        })

    (job_dir / "scenes.json").write_text(
        json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return scenes
