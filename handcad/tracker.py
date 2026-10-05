"""Camera + MediaPipe hand tracking, running on a background thread."""

import threading
import time
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import HandLandmarker, HandLandmarkerOptions, RunningMode
from PySide6.QtCore import QThread, Signal

from .config import Config
from .controller import Controller, ViewState

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task"
MODEL_PATH = Path.home() / ".cache" / "handcad" / "hand_landmarker.task"


def ensure_model() -> Path:
    if not MODEL_PATH.exists():
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading hand model to {MODEL_PATH} ...")
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    return MODEL_PATH


class LatestFrame:
    """Reads the camera on its own thread so capture overlaps with inference; keeps only the newest frame."""

    def __init__(self, cap: cv2.VideoCapture):
        self.cap = cap
        self.cond = threading.Condition()
        self.frame = None
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self):
        while self.running:
            ok, f = self.cap.read()
            if ok:
                with self.cond:
                    self.frame = f
                    self.cond.notify()

    def get(self, timeout=1.0):
        with self.cond:
            self.cond.wait_for(lambda: self.frame is not None, timeout)
            f, self.frame = self.frame, None
            return f

    def stop(self):
        self.running = False


class Tracker(QThread):
    frame = Signal(object)  # ViewState

    def __init__(self, cfg: Config, controller: Controller):
        super().__init__()
        self.cfg = cfg
        self.controller = controller
        self.running = True

    def stop(self):
        self.running = False
        self.wait(2000)

    def run(self):
        cfg = self.cfg
        landmarker = HandLandmarker.create_from_options(
            HandLandmarkerOptions(
                base_options=BaseOptions(model_asset_path=str(ensure_model())),
                running_mode=RunningMode.VIDEO,
                num_hands=1,
                min_hand_detection_confidence=0.6,
                min_hand_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
        )
        cap = cv2.VideoCapture(cfg.camera, cv2.CAP_V4L2)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, cfg.cam_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cfg.cam_height)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            raise SystemExit(f"Could not open camera {cfg.camera}")

        camera = LatestFrame(cap)
        t0 = time.monotonic()
        fps = 0.0
        last = t0
        try:
            while self.running:
                bgr = camera.get()
                if bgr is None:
                    continue
                now = time.monotonic()
                fps = 0.9 * fps + 0.1 / max(now - last, 1e-3)
                last = now

                # Mirror so moving your hand right moves the cursor right.
                rgb = cv2.cvtColor(cv2.flip(bgr, 1), cv2.COLOR_BGR2RGB)
                result = landmarker.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int((now - t0) * 1000)
                )
                if result.hand_landmarks:
                    image_pts = np.array([(p.x, p.y, p.z) for p in result.hand_landmarks[0]])
                    world_pts = np.array([(p.x, p.y, p.z) for p in result.hand_world_landmarks[0]])
                    state = self.controller.update(image_pts, world_pts, now)
                else:
                    self.controller.lost()
                    state = ViewState(paused=self.controller.paused, label="paused" if self.controller.paused else "")
                state.fps = fps
                self.frame.emit(state)
        finally:
            self.controller.lost()
            camera.stop()
            time.sleep(0.1)
            cap.release()
            landmarker.close()
