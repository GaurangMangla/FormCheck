"""
Unit tests for the squat analysis logic using synthetic landmark sequences.
This validates the angle math, rep-detection state machine, and threshold logic
independent of the actual MediaPipe CV model.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from app.pose_analysis import (
    FrameLandmarks, calculate_angle, torso_lean_angle, analyze_squat, LM
)
import math


def make_frame(frame_index, hip_y, knee_y, knee_x_offset=0.0, shoulder_x_offset=0.0):
    """
    Build a synthetic frame where a side-view stick figure squats.
    Coordinates are normalized (0-1), y increases downward (image convention).
    ankle is fixed at the bottom; hip moves down as the person squats;
    knee bends forward as hip drops (knee_x_offset simulates knee travel / valgus fudge).
    """
    ankle = (0.5, 0.9, 0.99)
    knee = (0.5 + knee_x_offset, knee_y, 0.99)
    hip = (0.5, hip_y, 0.99)
    shoulder = (0.5 + shoulder_x_offset, hip_y - 0.35, 0.99)

    points = {
        LM.LEFT_HIP.value: hip,
        LM.LEFT_KNEE.value: knee,
        LM.LEFT_ANKLE.value: ankle,
        LM.LEFT_SHOULDER.value: shoulder,
        # keep right side low-visibility so LEFT gets picked
        LM.RIGHT_HIP.value: (0.5, hip_y, 0.1),
        LM.RIGHT_KNEE.value: (0.5, knee_y, 0.1),
        LM.RIGHT_ANKLE.value: (0.5, 0.9, 0.1),
        LM.RIGHT_SHOULDER.value: (0.5, hip_y - 0.35, 0.1),
    }
    return FrameLandmarks(frame_index=frame_index, points=points)


def test_calculate_angle_straight_line():
    # a-b-c in a straight line -> 180 degrees
    angle = calculate_angle((0, 1), (0, 0.5), (0, 0))
    assert abs(angle - 180.0) < 1e-3, f"expected 180, got {angle}"
    print("PASS: straight-line angle == 180")


def test_calculate_angle_right_angle():
    # a=(0,0), b=(0,1), c=(1,1) -> 90 degrees at b
    angle = calculate_angle((0, 0), (0, 1), (1, 1))
    assert abs(angle - 90.0) < 1e-3, f"expected 90, got {angle}"
    print("PASS: right angle == 90")


def test_good_deep_squat_rep_detected():
    frames = []
    idx = 0
    # standing (knee angle ~180) -> descend to a deep squat (knee bends forward, hip drops) -> back up.
    # In a real side-view squat the knee travels forward (+x) as the hip drops, which is what actually
    # bends the hip-knee-ankle angle away from 180 degrees.
    for hip_y in [0.55, 0.55, 0.6, 0.68, 0.76, 0.83, 0.85, 0.85, 0.8, 0.72, 0.64, 0.58, 0.55, 0.55]:
        knee_y = (hip_y + 0.9) / 2
        depth = max(0.0, hip_y - 0.55)  # how far into the squat we are
        knee_x_offset = depth * 0.9     # knee travels forward as squat deepens
        frames.append(make_frame(idx, hip_y, knee_y, knee_x_offset=knee_x_offset, shoulder_x_offset=0.02))
        idx += 1

    result = analyze_squat(frames, fps=30.0)
    assert result.side_used == "LEFT"
    assert len(result.reps) == 1, f"expected 1 rep, got {len(result.reps)}"
    rep = result.reps[0]
    print(f"Rep detected: min_knee_angle={rep.min_knee_angle:.1f}, torso_angle={rep.torso_angle_at_bottom:.1f}, issues={rep.issues}")
    assert rep.min_knee_angle < 100, "expected deep squat to register knee angle < 100"
    print("PASS: deep squat rep detected with good depth")


def test_shallow_squat_flags_depth_issue():
    frames = []
    idx = 0
    # Only a shallow dip - hip never gets much below 0.65, so knee never bends much (angle stays > 100)
    for hip_y in [0.55, 0.55, 0.58, 0.62, 0.65, 0.65, 0.62, 0.58, 0.55, 0.55]:
        knee_y = (hip_y + 0.9) / 2
        depth = max(0.0, hip_y - 0.55)
        knee_x_offset = depth * 0.9
        frames.append(make_frame(idx, hip_y, knee_y, knee_x_offset=knee_x_offset, shoulder_x_offset=0.01))
        idx += 1

    result = analyze_squat(frames, fps=30.0)
    assert len(result.reps) == 1, f"expected 1 rep, got {len(result.reps)}"
    rep = result.reps[0]
    print(f"Shallow rep: min_knee_angle={rep.min_knee_angle:.1f}, issues={rep.issues}")
    assert not rep.is_good
    assert any("depth" in issue.lower() for issue in rep.issues)
    print("PASS: shallow squat correctly flagged for insufficient depth")


def test_no_person_detected_handled_gracefully():
    # frames with no landmarks at all (simulating nothing detected in video)
    frames = [FrameLandmarks(frame_index=i, points={}) for i in range(10)]
    result = analyze_squat(frames, fps=30.0)
    assert len(result.reps) == 0
    assert "No complete squat reps" in result.summary
    print("PASS: no-detection case handled gracefully, no crash")


if __name__ == "__main__":
    test_calculate_angle_straight_line()
    test_calculate_angle_right_angle()
    test_good_deep_squat_rep_detected()
    test_shallow_squat_flags_depth_issue()
    test_no_person_detected_handled_gracefully()
    print("\nALL TESTS PASSED")
