"""Turn 21 MediaPipe hand landmarks into a gesture label plus a few continuous signals."""

from dataclasses import dataclass, field

import numpy as np

from .config import Config

WRIST = 0
THUMB_TIP = 4
INDEX_MCP, INDEX_PIP, INDEX_TIP = 5, 6, 8
MIDDLE_MCP, MIDDLE_TIP = 9, 12
PINKY_MCP = 17

# (mcp, pip, dip, tip) per finger
FINGERS = {
    "index": (5, 6, 7, 8),
    "middle": (9, 10, 11, 12),
    "ring": (13, 14, 15, 16),
    "pinky": (17, 18, 19, 20),
}

BONES = [
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (0, 17), (17, 18), (18, 19), (19, 20),
]

# Gesture labels
NONE = "none"
POINT = "point"   # index only -> move cursor, thumb out = click
CUP = "cup"       # all fingers half bent -> rotate (middle drag)
THREE = "three"   # index+middle+ring -> pan (ctrl + middle drag)
TWO = "two"       # index+middle -> zoom (scroll)
OPEN = "open"     # flat hand -> idle
FIST = "fist"     # hold to pause / resume


def _angle(a: np.ndarray, b: np.ndarray) -> float:
    cos = np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9)
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))


@dataclass
class HandFeatures:
    curl: dict[str, float] = field(default_factory=dict)  # degrees per finger
    thumb_ratio: float = 0.0
    pinch_ratio: float = 0.0         # thumb tip to index tip
    middle_pinch_ratio: float = 0.0  # thumb tip to middle tip
    index_bend: float = 0.0  # bend at index MCP+PIP, for air taps
    gesture: str = NONE


def features(world: np.ndarray, cfg: Config) -> HandFeatures:
    """world: (21, 3) metric landmarks, rotation invariant enough for joint angles."""
    f = HandFeatures()
    for name, (mcp, pip, dip, tip) in FINGERS.items():
        segs = [world[mcp] - world[WRIST], world[pip] - world[mcp], world[dip] - world[pip], world[tip] - world[dip]]
        f.curl[name] = sum(_angle(segs[i], segs[i + 1]) for i in range(3))
    palm = np.linalg.norm(world[MIDDLE_MCP] - world[WRIST]) + 1e-9
    f.thumb_ratio = float(np.linalg.norm(world[THUMB_TIP] - world[INDEX_MCP]) / palm)
    f.pinch_ratio = float(np.linalg.norm(world[THUMB_TIP] - world[INDEX_TIP]) / palm)
    f.middle_pinch_ratio = float(np.linalg.norm(world[THUMB_TIP] - world[MIDDLE_TIP]) / palm)
    i = FINGERS["index"]
    f.index_bend = _angle(world[i[0]] - world[WRIST], world[i[1]] - world[i[0]]) + _angle(
        world[i[1]] - world[i[0]], world[i[2]] - world[i[1]]
    )
    f.gesture = classify(f.curl, cfg)
    pinched = f.pinch_ratio < cfg.pinch_release and cfg.click == "pinch"
    if f.gesture in (NONE, CUP) and (pinched or f.middle_pinch_ratio < cfg.pinch_release):
        # Pinching bends fingers out of the "point" shape (and a relaxed pinching hand can
        # look cupped); thumb touching the index or middle tip means cursor mode.
        f.gesture = POINT
    return f


def classify(curl: dict[str, float], cfg: Config) -> str:
    ext = {k: v < cfg.extended_max for k, v in curl.items()}
    folded = {k: v > cfg.curled_min for k, v in curl.items()}
    i, m, r, p = (ext[k] for k in ("index", "middle", "ring", "pinky"))

    if all(folded.values()):
        return FIST
    if i and m and r and p:
        return OPEN
    if i and m and r and not p:
        return THREE
    if i and m and folded["ring"] and folded["pinky"]:
        return TWO
    if i and folded["middle"] and folded["ring"]:
        return POINT
    if all(cfg.cup_min < v < cfg.cup_max for v in curl.values()):
        return CUP
    return NONE


class Debouncer:
    """Only switch gesture after it has been seen `n` frames in a row."""

    def __init__(self, n: int):
        self.n = n
        self.current = NONE
        self.candidate = NONE
        self.count = 0

    def __call__(self, g: str) -> str:
        if g == self.current:
            self.candidate, self.count = g, 0
            return self.current
        if g == self.candidate:
            self.count += 1
        else:
            self.candidate, self.count = g, 1
        if self.count >= self.n:
            self.current, self.count = g, 0
        return self.current

    def reset(self):
        self.current = self.candidate = NONE
        self.count = 0
