"""Gesture -> mouse actions, using Onshape's "SolidWorks" mouse preset:
rotate = middle drag, pan = Ctrl + middle drag, zoom = scroll wheel.
"""

from dataclasses import dataclass, field

import numpy as np
from evdev import ecodes as e

from . import gestures as g
from .config import Config
from .filters import OneEuro2D
from .mouse import VirtualMouse

PALM = [0, 5, 9, 13, 17]

MODE_LABELS = {
    g.POINT: "cursor",
    g.CUP: "rotate",
    g.THREE: "pan",
    g.TWO: "zoom",
    g.OPEN: "idle",
    g.FIST: "idle",
    g.NONE: "",
}


@dataclass
class ViewState:
    """Everything the overlay needs for one frame (all coords normalized to the screen)."""

    points: list[tuple[float, float]] | None = None
    gesture: str = g.NONE
    label: str = ""
    cursor: tuple[float, float] | None = None
    pressed: bool = False
    pinch: float | None = None  # 0 = fingers apart .. 1 = pinch closed, in cursor mode
    pinch_finger: int = 8       # landmark the thumb is pinching toward (8 index, 12 middle)
    clicks: list = field(default_factory=list)  # buttons ("left"/"right") pressed this frame
    paused: bool = False
    pause_progress: float = 0.0
    fps: float = 0.0
    debug: dict = field(default_factory=dict)


class Controller:
    def __init__(self, cfg: Config, mouse: VirtualMouse | None):
        self.cfg = cfg
        self.mouse = mouse
        self.debounce = g.Debouncer(cfg.stable_frames)
        self.cursor_filter = OneEuro2D(cfg.filter_min_cutoff, cfg.filter_beta)
        self.palm_filter = OneEuro2D(cfg.filter_min_cutoff, cfg.filter_beta)
        self.mode = g.NONE
        self.cursor = (0.5, 0.5)
        self.last_palm = None
        self.zoom_accum = 0.0
        self.left_down = False
        self.right_down = False
        self.clicks: list[str] = []
        self.freeze_until = 0.0
        self.last_click_signal = None
        self.last_t = None
        self.paused = False
        self.fist_since = None
        self.fist_armed = True
        self.tap_baseline = None
        self.tap_start = None

    # -- helpers -------------------------------------------------------------

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        (x0, x1), (y0, y1) = self.cfg.active_x, self.cfg.active_y
        return (x - x0) / (x1 - x0), (y - y0) / (y1 - y0)

    def _release(self):
        if self.mouse:
            self.mouse.release_all()
        self.left_down = False
        self.right_down = False

    def _enter(self, mode: str, palm):
        """Leave the current mode cleanly, then start the new one."""
        self._release()
        self.mode = mode
        self.last_palm = palm
        self.zoom_accum = 0.0
        self.cursor_filter.reset()
        if not self.mouse or self.paused:
            return
        if mode == g.CUP:
            self.mouse.press(e.BTN_MIDDLE)
        elif mode == g.THREE:
            self.mouse.press(e.KEY_LEFTCTRL)
            self.mouse.press(e.BTN_MIDDLE)

    def _move(self, x, y):
        self.cursor = (min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0))
        if self.mouse and not self.paused:
            self.mouse.move(*self.cursor)

    # -- main update ---------------------------------------------------------

    def lost(self):
        """Hand left the frame."""
        if self.mode != g.NONE:
            self._enter(g.NONE, None)
        self.debounce.reset()
        self.fist_since = None
        self.last_click_signal = None
        self.tap_start = None

    def update(self, image_pts: np.ndarray, world_pts: np.ndarray, t: float) -> ViewState:
        cfg = self.cfg
        feats = g.features(world_pts, cfg)
        raw = feats.gesture
        if raw == g.NONE and self.mode == g.POINT:
            raw = g.POINT  # stay in cursor mode through in-between hand shapes
        gesture = self.debounce(raw)
        pts = [self.to_screen(x, y) for x, y in image_pts[:, :2]]
        palm = self.palm_filter(tuple(np.mean([pts[i] for i in PALM], axis=0)), t)
        dt = (t - self.last_t) if self.last_t else 1 / 30
        self.last_t = t

        pause_progress = self._handle_pause(gesture, t)

        if gesture != self.mode:
            self._enter(gesture, palm)

        if not self.paused:
            if self.mode == g.POINT:
                self._point(pts, feats, t, dt)
            elif self.mode in (g.CUP, g.THREE):
                gain = cfg.rotate_gain if self.mode == g.CUP else cfg.pan_gain
                dx, dy = palm[0] - self.last_palm[0], palm[1] - self.last_palm[1]
                self._move(self.cursor[0] + dx * gain, self.cursor[1] + dy * gain)
            elif self.mode == g.TWO:
                self.zoom_accum += (self.last_palm[1] - palm[1]) * cfg.zoom_gain * (-1 if cfg.zoom_invert else 1)
                notches = int(self.zoom_accum)
                if notches and self.mouse:
                    self.mouse.scroll(notches)
                self.zoom_accum -= notches
        self.last_palm = palm

        return ViewState(
            points=pts,
            gesture=self.mode,
            label="paused" if self.paused else MODE_LABELS[self.mode],
            cursor=self.cursor if self.mode in (g.POINT, g.CUP, g.THREE) else None,
            pressed=self.left_down or self.right_down or self.mode in (g.CUP, g.THREE),
            pinch=self._pinch_closeness(feats) if self.mode == g.POINT else None,
            pinch_finger=self._pinch_finger(feats),
            clicks=self._take_clicks(),
            paused=self.paused,
            pause_progress=pause_progress,
            debug={
                **{k: round(v) for k, v in feats.curl.items()},
                "raw": feats.gesture,
                "thumb": round(feats.thumb_ratio, 2),
                "pinch": round(feats.pinch_ratio, 2),
                "rpinch": round(feats.middle_pinch_ratio, 2),
                "bend": round(feats.index_bend),
            }
            if cfg.debug
            else {},
        )

    def _handle_pause(self, gesture: str, t: float) -> float:
        if gesture != g.FIST:
            self.fist_since = None
            self.fist_armed = True
            return 0.0
        if not self.fist_armed:
            return 0.0
        if self.fist_since is None:
            self.fist_since = t
        progress = (t - self.fist_since) / self.cfg.pause_hold_s
        if progress >= 1.0:
            self.paused = not self.paused
            self.fist_armed = False  # open the hand before toggling again
            self._release()
            return 0.0
        return progress

    def _pinch_finger(self, feats: g.HandFeatures) -> int:
        """Which fingertip the thumb is going for. Thumb-out clicking has no index pinch."""
        if self.right_down or self.cfg.click == "thumb":
            return g.MIDDLE_TIP
        if self.left_down:
            return g.INDEX_TIP
        return g.MIDDLE_TIP if feats.middle_pinch_ratio < feats.pinch_ratio else g.INDEX_TIP

    def _take_clicks(self) -> list[str]:
        clicks, self.clicks = self.clicks, []
        return clicks

    def _pinch_closeness(self, feats: g.HandFeatures) -> float:
        """0 = relaxed hand .. 1 = at the click threshold."""
        cfg = self.cfg
        if self._pinch_finger(feats) == g.MIDDLE_TIP:
            ratio, press, open_ratio = feats.middle_pinch_ratio, cfg.rpinch_press, cfg.rpinch_open
        else:
            ratio, press, open_ratio = feats.pinch_ratio, cfg.pinch_press, cfg.pinch_open
        return min(max((open_ratio - ratio) / max(open_ratio - press, 1e-3), 0.0), 1.0)

    def _point(self, pts, feats: g.HandFeatures, t: float, dt: float):
        cfg = self.cfg
        # Press when the click gesture closes, release when it opens (so holding it drags).
        # Signals are oriented so that bigger = more "pressed".
        if cfg.click == "pinch":
            signal, press, release = -feats.pinch_ratio, -cfg.pinch_press, -cfg.pinch_release
            freeze_speed, anchor = cfg.pinch_freeze_speed, g.INDEX_MCP
        else:
            signal, press, release = feats.thumb_ratio, cfg.thumb_press, cfg.thumb_release
            freeze_speed, anchor = cfg.thumb_freeze_speed, g.INDEX_TIP
        right = feats.middle_pinch_ratio
        if self.last_click_signal is not None:
            last_signal, last_right = self.last_click_signal
            speed = max(abs(signal - last_signal) / dt, abs(right - last_right) / dt * freeze_speed / cfg.pinch_freeze_speed)
        else:
            speed = 0.0
        self.last_click_signal = (signal, right)

        # Right click: thumb to middle fingertip. Whichever fingertip the thumb is closer to wins.
        if not self.right_down and not self.left_down and right < cfg.rpinch_press and right < feats.pinch_ratio:
            self.right_down = True
            self.clicks.append("right")
            if self.mouse:
                self.mouse.press(e.BTN_RIGHT)
            self.freeze_until = t + cfg.click_freeze_s
        elif self.right_down and right > cfg.rpinch_release:
            self.right_down = False
            if self.mouse:
                self.mouse.release(e.BTN_RIGHT)
            self.freeze_until = t + cfg.click_freeze_s

        if not self.left_down and not self.right_down and signal > press and (
            cfg.click == "thumb" or feats.pinch_ratio <= right
        ):
            self.left_down = True
            self.clicks.append("left")
            if self.mouse:
                self.mouse.press(e.BTN_LEFT)
            self.freeze_until = t + cfg.click_freeze_s
        elif self.left_down and signal < release:
            self.left_down = False
            if self.mouse:
                self.mouse.release(e.BTN_LEFT)
            self.freeze_until = t + cfg.click_freeze_s
        frozen = t < self.freeze_until or speed > freeze_speed

        if cfg.air_tap:
            frozen |= self._air_tap(feats.index_bend, t)

        target = self.cursor_filter(pts[anchor], t)
        if not frozen:
            self._move(*target)

    def _air_tap(self, bend: float, t: float) -> bool:
        """Quick dip-and-return of the index finger = click. Returns True while tapping."""
        cfg = self.cfg
        if self.tap_baseline is None:
            self.tap_baseline = bend
        delta = bend - self.tap_baseline
        if self.tap_start is None:
            if delta > cfg.tap_depth_deg:
                self.tap_start = t
            else:
                self.tap_baseline += 0.1 * (bend - self.tap_baseline)
            return delta > cfg.tap_depth_deg / 3
        if t - self.tap_start > cfg.tap_max_s:
            # Too slow: that was a deliberate bend, not a tap.
            self.tap_start = None
            self.tap_baseline = bend
            return False
        if delta < cfg.tap_depth_deg / 2:
            self.tap_start = None
            if self.mouse:
                self.mouse.click(e.BTN_LEFT)
            self.freeze_until = t + cfg.click_freeze_s
        return True
