"""
AI Fitness Form Checker - FastAPI backend.

POST /analyze   -> upload a squat video, get back JSON feedback + a URL to the annotated video
GET  /videos/{f} -> serves a processed annotated video file
"""
import os
import shutil
import uuid
from dataclasses import asdict

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.pose_analysis import extract_landmarks_from_video, analyze_squat
from app.video_processor import annotate_video

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

app = FastAPI(title="AI Fitness Form Checker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # fine for local dev; restrict this before any real deployment
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(file: UploadFile = File(...), exercise: str = "squat"):
    if exercise != "squat":
        raise HTTPException(status_code=400, detail="Only 'squat' is supported in this MVP.")

    ext = os.path.splitext(file.filename or "")[1] or ".mp4"
    job_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{job_id}{ext}")
    output_filename = f"{job_id}_annotated.mp4"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        frames, fps, width, height, total_frames = extract_landmarks_from_video(input_path)
        if total_frames == 0:
            raise HTTPException(status_code=400, detail="Could not read any frames from the uploaded video.")

        result = analyze_squat(frames, fps)
        annotate_video(input_path, output_path, frames, result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")
    finally:
        # Clean up the raw upload; keep only the annotated output
        if os.path.exists(input_path):
            os.remove(input_path)

    reps_payload = [
        {
            "rep_number": r.rep_number,
            "min_knee_angle": round(r.min_knee_angle, 1),
            "torso_angle_at_bottom": round(r.torso_angle_at_bottom, 1),
            "is_good": r.is_good,
            "issues": r.issues,
            "timestamp_seconds": round(r.bottom_frame_index / fps, 2) if fps else None,
        }
        for r in result.reps
    ]

    return {
        "job_id": job_id,
        "summary": result.summary,
        "side_analyzed": result.side_used,
        "fps": fps,
        "total_frames": total_frames,
        "reps": reps_payload,
        "annotated_video_url": f"/videos/{output_filename}",
    }


@app.get("/videos/{filename}")
def get_video(filename: str):
    path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Video not found.")
    return FileResponse(path, media_type="video/mp4")
