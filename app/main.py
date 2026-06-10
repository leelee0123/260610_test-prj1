import json
import re
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from app import pipeline  # noqa: E402  (load_dotenv 이후 import)
from app.prompts import DEFAULTS, get_prompts, save_prompts  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
JOBS_DIR = BASE_DIR / "jobs"
JOBS_DIR.mkdir(exist_ok=True)

ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
STEPS = ["audio", "transcribe", "correct", "scenes", "analyze", "merge", "qc"]
RESULT_FILES = {"original.srt", "corrected.srt", "metadata.json", "qc_report.json"}
JOB_ID_RE = re.compile(r"^[0-9a-f]{12}$")

app = FastAPI(title="영상 자동 분석 파이프라인")


def read_status(job_id: str) -> dict:
    if not JOB_ID_RE.match(job_id):
        raise HTTPException(404, "잘못된 작업 ID입니다.")
    status_path = JOBS_DIR / job_id / "status.json"
    if not status_path.exists():
        raise HTTPException(404, "작업을 찾을 수 없습니다.")
    return json.loads(status_path.read_text(encoding="utf-8"))


def write_status(job_id: str, status: dict) -> None:
    path = JOBS_DIR / job_id / "status.json"
    path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


@app.post("/api/upload")
async def upload(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    mode: str = Form("cloud"),
):
    if mode not in ("cloud", "onpremise"):
        raise HTTPException(400, "mode는 'cloud' 또는 'onpremise'여야 합니다.")
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(400, f"지원하지 않는 형식입니다: {ext or '(확장자 없음)'}")

    job_id = uuid.uuid4().hex[:12]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True)

    dest = job_dir / f"input{ext}"
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            out.write(chunk)

    status = {
        "job_id": job_id,
        "filename": file.filename,
        "mode": mode,
        "state": "uploaded",
        "steps": {step: "pending" for step in STEPS},
        "error": None,
    }
    write_status(job_id, status)
    background.add_task(pipeline.run, job_dir)
    return status


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    return read_status(job_id)


@app.get("/api/jobs/{job_id}/subtitles")
def job_subtitles(job_id: str):
    from app.srt_utils import parse_srt
    read_status(job_id)  # 404 guard
    job_dir = JOBS_DIR / job_id
    orig_path = job_dir / "original.srt"
    corr_path = job_dir / "corrected.srt"
    if not orig_path.exists():
        raise HTTPException(404, "아직 자막이 생성되지 않았습니다.")
    original = parse_srt(orig_path.read_text(encoding="utf-8"))
    corrected = None
    if corr_path.exists():
        raw = parse_srt(corr_path.read_text(encoding="utf-8"))
        by_idx = {e["index"]: e["text"] for e in raw}
        corrected = [
            {**e, "changed": by_idx.get(e["index"], e["text"]) != e["text"],
             "text": by_idx.get(e["index"], e["text"])}
            for e in original
        ]
    return {"original": original, "corrected": corrected}


@app.get("/api/jobs/{job_id}/keyframes/{name}")
def job_keyframe(job_id: str, name: str):
    read_status(job_id)
    if not name.endswith(".jpg") or "/" in name or "\\" in name:
        raise HTTPException(400, "잘못된 파일명입니다.")
    path = JOBS_DIR / job_id / "keyframes" / name
    if not path.exists():
        raise HTTPException(404, "키프레임이 없습니다.")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/jobs/{job_id}/files/{name}")
def job_file(job_id: str, name: str):
    read_status(job_id)  # 404 if job doesn't exist
    if name not in RESULT_FILES:
        raise HTTPException(404, "허용되지 않는 파일입니다.")
    path = JOBS_DIR / job_id / name
    if not path.exists():
        raise HTTPException(404, "아직 생성되지 않은 파일입니다.")
    return FileResponse(path, filename=name)


@app.get("/api/prompts")
def read_prompts():
    return get_prompts()


@app.put("/api/prompts")
async def update_prompts(body: dict):
    unknown = set(body) - set(DEFAULTS)
    if unknown:
        raise HTTPException(400, f"알 수 없는 키: {', '.join(sorted(unknown))}")
    return save_prompts(body)


@app.post("/api/prompts/reset")
def reset_prompts():
    return save_prompts(DEFAULTS)


app.mount("/docs-static", StaticFiles(directory=BASE_DIR / "docs"), name="docs")
app.mount("/", StaticFiles(directory=BASE_DIR / "app" / "static", html=True), name="static")
