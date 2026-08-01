"""
Draws the pose skeleton onto each frame and overlays rep-level feedback
(green = good rep, red = flagged issue) at the bottom-of-squat frame of each rep,
then writes the annotated video back out to disk.
"""
from typing import List
import cv2

try:
    import mediapipe as mp
    mp_pose = mp.solutions.pose
    mp_drawing = mp.solutions.drawing_utils
    mp_styles = mp.solutions.drawing_styles
except (AttributeError, ModuleNotFoundError):
    mp = None
    mp_pose = None
    mp_drawing = None
    mp_styles = None

from app.pose_analysis import FrameLandmarks, AnalysisResult


def _landmarks_to_mp_format(frame_lm: FrameLandmarks):
    """Rebuild a minimal object mimicking mediapipe's pose_landmarks structure
    so we can reuse mp_drawing.draw_landmarks for rendering."""
    if not frame_lm.points:
        return None

    class _LM:
        def __init__(self, x, y, z, visibility):
            self.x, self.y, self.z, self.visibility = x, y, z, visibility

    class _Landmarks:
        def __init__(self, landmark):
            self.landmark = landmark

    ordered = []
    max_idx = max(frame_lm.points.keys())
    for i in range(max_idx + 1):
        if i in frame_lm.points:
            x, y, vis = frame_lm.points[i]
            ordered.append(_LM(x, y, 0.0, vis))
        else:
            ordered.append(_LM(0.0, 0.0, 0.0, 0.0))

    return _Landmarks(ordered)


def annotate_video(video_path: str, output_path: str,
                    frames_lm: List[FrameLandmarks],
                    analysis: AnalysisResult) -> None:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Could not reopen video for annotation: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or analysis.fps or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

    # Map bottom-of-rep frame index -> RepResult, for quick lookup while iterating frames
    bottom_frame_map = {r.bottom_frame_index: r for r in analysis.reps}
    # Keep the "flag" visible for a short window of frames around the bottom so it's readable
    HOLD_FRAMES = max(1, int(fps * 0.6))

    active_flag = None
    active_flag_countdown = 0

    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if idx < len(frames_lm) and mp_drawing is not None and mp_pose is not None and mp_styles is not None:
            mp_landmarks = _landmarks_to_mp_format(frames_lm[idx])
            if mp_landmarks is not None:
                mp_drawing.draw_landmarks(
                    frame, mp_landmarks, mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=mp_styles.get_default_pose_landmarks_style(),
                )

        if idx in bottom_frame_map:
            active_flag = bottom_frame_map[idx]
            active_flag_countdown = HOLD_FRAMES

        if active_flag_countdown > 0 and active_flag is not None:
            rep = active_flag
            color = (0, 200, 0) if rep.is_good else (0, 0, 255)  # BGR: green / red
            label = f"Rep {rep.rep_number}: " + ("Good form" if rep.is_good else rep.issues[0][:60])
            cv2.rectangle(frame, (0, height - 50), (width, height), (0, 0, 0), -1)
            cv2.putText(frame, label, (10, height - 18), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, color, 2, cv2.LINE_AA)
            active_flag_countdown -= 1

        writer.write(frame)
        idx += 1

    cap.release()
    writer.release()
