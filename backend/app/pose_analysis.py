"""
Core pose-analysis logic for the AI Fitness Form Checker.

This module is intentionally decoupled from FastAPI and from video I/O so it can
be unit-tested with synthetic landmark data (see test_pose_analysis.py).
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

import cv2
import mediapipe as mp
import numpy as np

mp_pose = mp.solutions.pose

# ---- Landmark indices we care about ----
LM = mp_pose.PoseLandmark


@dataclass
class FrameLandmarks:
    """A single frame's landmark set, stored as {index: (x, y, visibility)}."""
    frame_index: int
    points: Dict[int, tuple]  # index -> (x, y, visibility)  (x, y normalized 0-1)


@dataclass
class RepResult:
    rep_number: int
    bottom_frame_index: int
    min_knee_angle: float
    torso_angle_at_bottom: float
    issues: List[str] = field(default_factory=list)
    is_good: bool = True


@dataclass
class AnalysisResult:
    fps: float
    total_frames: int
    side_used: str  # "LEFT" or "RIGHT"
    knee_angle_series: List[Optional[float]]
    reps: List[RepResult]
    summary: str


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def calculate_angle(a: tuple, b: tuple, c: tuple) -> float:
    """Angle at point b (in degrees), formed by points a-b-c."""
    a = np.array(a[:2])
    b = np.array(b[:2])
    c = np.array(c[:2])

    ba = a - b
    bc = c - b

    denom = (np.linalg.norm(ba) * np.linalg.norm(bc))
    if denom == 0:
        return 180.0

    cosine = np.dot(ba, bc) / denom
    cosine = np.clip(cosine, -1.0, 1.0)
    angle = np.degrees(np.arccos(cosine))
    return float(angle)


def torso_lean_angle(shoulder: tuple, hip: tuple) -> float:
    """
    Angle (degrees) between the shoulder->hip vector and true vertical.
    0 degrees = perfectly upright torso. Larger = more forward/backward lean.
    """
    shoulder = np.array(shoulder[:2])
    hip = np.array(hip[:2])
    vec = shoulder - hip  # points "up" from hip to shoulder in image space
    vertical = np.array([0.0, -1.0])  # image y increases downward, so "up" is -y

    denom = (np.linalg.norm(vec) * np.linalg.norm(vertical))
    if denom == 0:
        return 0.0
    cosine = np.dot(vec, vertical) / denom
    cosine = np.clip(cosine, -1.0, 1.0)
    return float(np.degrees(np.arccos(cosine)))


# ---------------------------------------------------------------------------
# Landmark extraction from video
# ---------------------------------------------------------------------------

def extract_landmarks_from_video(video_path: str, model_complexity: int = 1):
    """
    Runs MediaPipe Pose over every frame of the video.
    Returns (frames: List[FrameLandmarks], fps: float, width: int, height: int, total_frames: int)
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    frames: List[FrameLandmarks] = []

    with mp_pose.Pose(static_image_mode=False, model_complexity=model_complexity,
                       min_detection_confidence=0.5, min_tracking_confidence=0.5) as pose:
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = pose.process(rgb)

            points = {}
            if results.pose_landmarks:
                for i, lm in enumerate(results.pose_landmarks.landmark):
                    points[i] = (lm.x, lm.y, lm.visibility)

            frames.append(FrameLandmarks(frame_index=idx, points=points))
            idx += 1

    cap.release()
    return frames, fps, width, height, len(frames)


# ---------------------------------------------------------------------------
# Squat-specific analysis
# ---------------------------------------------------------------------------

DEPTH_THRESHOLD_DEG = 100.0       # knee angle must dip below this to count as "good depth"
TORSO_LEAN_THRESHOLD_DEG = 45.0   # torso lean beyond this at the bottom is flagged
STANDING_ANGLE_DEG = 160.0        # above this = considered "standing" (rep boundary)
MIN_VISIBILITY = 0.5


def _pick_side(frames: List[FrameLandmarks]) -> str:
    """Choose LEFT or RIGHT side based on average visibility of hip/knee/ankle."""
    left_ids = [LM.LEFT_HIP.value, LM.LEFT_KNEE.value, LM.LEFT_ANKLE.value]
    right_ids = [LM.RIGHT_HIP.value, LM.RIGHT_KNEE.value, LM.RIGHT_ANKLE.value]

    def avg_visibility(ids):
        vis = []
        for f in frames:
            for i in ids:
                if i in f.points:
                    vis.append(f.points[i][2])
        return sum(vis) / len(vis) if vis else 0.0

    return "LEFT" if avg_visibility(left_ids) >= avg_visibility(right_ids) else "RIGHT"


def _smooth(series: List[Optional[float]], window: int = 3) -> List[Optional[float]]:
    """Simple moving average smoothing, skipping None values."""
    out = []
    for i in range(len(series)):
        lo, hi = max(0, i - window // 2), min(len(series), i + window // 2 + 1)
        vals = [v for v in series[lo:hi] if v is not None]
        out.append(sum(vals) / len(vals) if vals else None)
    return out


def analyze_squat(frames: List[FrameLandmarks], fps: float) -> AnalysisResult:
    side = _pick_side(frames)
    hip_i = (LM.LEFT_HIP if side == "LEFT" else LM.RIGHT_HIP).value
    knee_i = (LM.LEFT_KNEE if side == "LEFT" else LM.RIGHT_KNEE).value
    ankle_i = (LM.LEFT_ANKLE if side == "LEFT" else LM.RIGHT_ANKLE).value
    shoulder_i = (LM.LEFT_SHOULDER if side == "LEFT" else LM.RIGHT_SHOULDER).value

    knee_angles: List[Optional[float]] = []
    torso_angles: List[Optional[float]] = []

    for f in frames:
        pts = f.points
        required = [hip_i, knee_i, ankle_i, shoulder_i]
        if not all(i in pts and pts[i][2] >= MIN_VISIBILITY for i in required):
            knee_angles.append(None)
            torso_angles.append(None)
            continue

        hip, knee, ankle, shoulder = pts[hip_i], pts[knee_i], pts[ankle_i], pts[shoulder_i]
        knee_angles.append(calculate_angle(hip, knee, ankle))
        torso_angles.append(torso_lean_angle(shoulder, hip))

    knee_angles_smoothed = _smooth(knee_angles)

    # ---- Rep detection via simple state machine over the smoothed knee-angle series ----
    reps: List[RepResult] = []
    state = "STANDING"
    current_min_angle = None
    current_min_idx = None
    rep_num = 0

    for i, angle in enumerate(knee_angles_smoothed):
        if angle is None:
            continue

        if state == "STANDING":
            if angle < STANDING_ANGLE_DEG:
                state = "DESCENDING"
                current_min_angle = angle
                current_min_idx = i
        elif state == "DESCENDING":
            if current_min_angle is None or angle < current_min_angle:
                current_min_angle = angle
                current_min_idx = i
            if angle > (current_min_angle + 8):  # started rising back up -> bottom passed
                state = "ASCENDING"
        elif state == "ASCENDING":
            if angle >= STANDING_ANGLE_DEG:
                # Rep complete
                rep_num += 1
                bottom_idx = current_min_idx
                torso_at_bottom = torso_angles[bottom_idx] if bottom_idx is not None and bottom_idx < len(torso_angles) else None
                torso_at_bottom = torso_at_bottom if torso_at_bottom is not None else 0.0

                issues = []
                if current_min_angle is None or current_min_angle > DEPTH_THRESHOLD_DEG:
                    issues.append(
                        f"Not hitting full depth (knee angle only reached "
                        f"{current_min_angle:.0f}°; aim for below {DEPTH_THRESHOLD_DEG:.0f}°)."
                    )
                if torso_at_bottom > TORSO_LEAN_THRESHOLD_DEG:
                    issues.append(
                        f"Excessive forward lean at the bottom ({torso_at_bottom:.0f}° from vertical); "
                        f"try keeping your chest more upright."
                    )

                reps.append(RepResult(
                    rep_number=rep_num,
                    bottom_frame_index=bottom_idx if bottom_idx is not None else i,
                    min_knee_angle=current_min_angle if current_min_angle is not None else 180.0,
                    torso_angle_at_bottom=torso_at_bottom,
                    issues=issues,
                    is_good=(len(issues) == 0),
                ))
                state = "STANDING"
                current_min_angle = None
                current_min_idx = None

    if not reps:
        summary = ("No complete squat reps were detected. Make sure the full body is visible "
                    "from a side angle and that at least one full squat (standing -> bottom -> standing) is in frame.")
    else:
        good = sum(1 for r in reps if r.is_good)
        summary = f"Detected {len(reps)} rep(s). {good}/{len(reps)} had clean form."

    return AnalysisResult(
        fps=fps,
        total_frames=len(frames),
        side_used=side,
        knee_angle_series=knee_angles_smoothed,
        reps=reps,
        summary=summary,
    )
