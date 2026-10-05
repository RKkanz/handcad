"""`handcad --calibrate`: measure your pinches and save click thresholds that fit your hand."""

import sys
import time

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode

from . import gestures as g
from .config import USER_CONFIG, Config, save_user
from .tracker import ensure_model

PHASES = [
    ("open", "Point at the screen with your index finger, thumb relaxed and AWAY from your fingers"),
    ("index", "Touch your THUMB tip to your INDEX fingertip, lightly, like a normal click"),
    ("middle", "Touch your THUMB tip to your MIDDLE fingertip (right click)"),
]
READY_S = 2.5
RECORD_S = 3.0


def run(cfg: Config):
    landmarker = HandLandmarker.create_from_options(
        HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(ensure_model())),
            running_mode=RunningMode.VIDEO,
            num_hands=1,
        )
    )
    cap = cv2.VideoCapture(cfg.camera, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.cam_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.cam_height)
    if not cap.isOpened():
        sys.exit(f"Could not open camera {cfg.camera} (is handcad already running?)")
    t0 = time.monotonic()

    def read():
        ok, bgr = cap.read()
        if not ok:
            return None
        rgb = cv2.cvtColor(cv2.flip(bgr, 1), cv2.COLOR_BGR2RGB)
        res = landmarker.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int((time.monotonic() - t0) * 1000)
        )
        if not res.hand_landmarks:
            return None
        return g.features(np.array([(p.x, p.y, p.z) for p in res.hand_world_landmarks[0]]), cfg)

    samples: dict[str, list[tuple[float, float]]] = {}
    print("\nhandcad calibration: hold each pose until it says done.\n")
    for key, prompt in PHASES:
        print(f"> {prompt}")
        start = time.monotonic()
        while time.monotonic() - start < READY_S:
            read()  # keep the tracker warm while you get into position
            print(f"\r  get ready... {READY_S - (time.monotonic() - start):.0f}s ", end="", flush=True)
        got: list[tuple[float, float]] = []
        start = time.monotonic()
        while time.monotonic() - start < RECORD_S:
            f = read()
            if f:
                got.append((f.pinch_ratio, f.middle_pinch_ratio))
                print(f"\r  recording  index={f.pinch_ratio:.2f}  middle={f.middle_pinch_ratio:.2f}   ", end="", flush=True)
            else:
                print("\r  recording  (hand not visible)                  ", end="", flush=True)
        print(f"\r  done ({len(got)} frames)                              ")
        samples[key] = got
    cap.release()
    landmarker.close()

    values = {}
    for finger, col, prefix in (("index", 0, "pinch"), ("middle", 1, "rpinch")):
        if len(samples["open"]) < 10 or len(samples[finger]) < 10:
            print(f"\n{finger}: not enough frames with your hand visible, keeping current values.")
            continue
        # Use the "worst" ends: a light touch, and the least-open relaxed hand.
        touch = float(np.percentile([s[col] for s in samples[finger]], 80))
        apart = float(np.percentile([s[col] for s in samples["open"]], 20))
        gap = apart - touch
        print(f"\n{finger}: touching ~{touch:.2f}, relaxed ~{apart:.2f}")
        if gap < 0.15:
            print(f"  too close together to tell apart reliably, keeping current values. Try again with the thumb further away.")
            continue
        values[f"{prefix}_press"] = round(touch + 0.30 * gap, 3)
        values[f"{prefix}_release"] = round(touch + 0.55 * gap, 3)
        values[f"{prefix}_open"] = round(apart, 3)
        print(f"  click below {values[f'{prefix}_press']:.2f}, release above {values[f'{prefix}_release']:.2f}")

    if values:
        save_user(values)
        print(f"\nSaved to {USER_CONFIG}. Start handcad normally to use them.")
