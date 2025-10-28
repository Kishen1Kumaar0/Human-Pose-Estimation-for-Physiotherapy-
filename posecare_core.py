# posecare_core.py
from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
import cv2

# ───────── constants / indices ─────────
KEYPT_MIN_CONF = 0.35

SQUAT_DOWN_MAX = 120.0   # both knees < 120° -> down
SQUAT_UP_MIN   = 165.0   # both knees > 165° -> up (a bit stricter to reduce false ups)

STS_SIT_MAX    = 120.0   # sit if knees < 120°
STS_STAND_MIN  = 165.0   # stand if knees > 165°

LR_UP_MAX      = 120.0   # leg up if hip angle < 120°
LR_DOWN_MIN    = 165.0   # leg down if hip angle > 165°

# Debounce to avoid jitter (frames)
MIN_DWELL = 3

KP = {
    "nose": 0, "leye": 1, "reye": 2, "lear": 3, "rear": 4,
    "lsh": 5, "rsh": 6, "lelb": 7, "relb": 8, "lwri": 9, "rwri": 10,
    "lhip": 11, "rhip": 12, "lknee": 13, "rknee": 14, "lank": 15, "rank": 16
}

# ───────── math helpers ─────────
def _valid_point(p: np.ndarray) -> bool:
    return p is not None and p.shape == (2,) and p[0] > 0 and p[1] > 0

def angle_3pt(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> Optional[float]:
    if not (_valid_point(a) and _valid_point(b) and _valid_point(c)):
        return None
    v1, v2 = a - b, c - b
    n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
    if n1 < 1e-6 or n2 < 1e-6:
        return None
    cosx = float(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0))
    return math.degrees(math.acos(cosx))

def knee_angles(kps: np.ndarray) -> Tuple[Optional[float], Optional[float]]:
    L = angle_3pt(kps[KP["lhip"]], kps[KP["lknee"]], kps[KP["lank"]])
    R = angle_3pt(kps[KP["rhip"]], kps[KP["rknee"]], kps[KP["rank"]])
    return L, R

def hip_angle_side(kps: np.ndarray, side: str) -> Optional[float]:
    if side == 'l':
        return angle_3pt(kps[KP["lsh"]], kps[KP["lhip"]], kps[KP["lank"]])
    else:
        return angle_3pt(kps[KP["rsh"]], kps[KP["rhip"]], kps[KP["rank"]])

# ───────── smoothing ─────────
class EMAStabilizer:
    """Per-joint EMA with confidence masking."""
    def __init__(self, alpha_fast: float = 0.45, alpha_slow: float = 0.15):
        self.alpha_fast = float(alpha_fast)
        self.alpha_slow = float(alpha_slow)
        self.state = None

    def update(self, kps, conf):
        if kps is None or conf is None:
            return None
        kps = np.asarray(kps, dtype=np.float32).copy()
        conf = np.asarray(conf, dtype=np.float32).reshape(-1)
        if kps.shape != (17, 2) or conf.shape[0] < 17:
            return None

        # mask low confidence
        mask_good = conf >= KEYPT_MIN_CONF
        kps[~mask_good] = -1.0

        if self.state is None:
            self.state = kps.copy()
            return self.state

        out = self.state.copy()
        for i in range(17):
            if kps[i, 0] <= 0 or kps[i, 1] <= 0:
                out[i] = np.array([-1.0, -1.0], dtype=np.float32)
                continue
            prev = self.state[i]
            if prev[0] <= 0 or prev[1] <= 0:
                out[i] = kps[i]; continue
            dist = float(np.linalg.norm(kps[i] - prev))
            alpha = self.alpha_fast if dist > 6.0 else self.alpha_slow
            out[i] = (1.0 - alpha) * prev + alpha * kps[i]
        self.state = out
        return self.state

# ───────── counter ─────────
@dataclass
class RepCounter:
    exercise: str = "squat"
    reps: int = 0
    state: str = ""
    dwell: int = 0
    form_pct: int = 0   # 0..100 (live quality)

    def reset(self, exercise: Optional[str] = None):
        if exercise:
            self.exercise = exercise
        self.reps = 0
        self.state = ""
        self.dwell = 0
        self.form_pct = 0

# ───────── form quality (0..100) ─────────
def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))

def form_quality_squat(kps: np.ndarray) -> Optional[int]:
    Lk, Rk = knee_angles(kps)
    if Lk is None or Rk is None: return None
    # 0% at ~180° (no bend), 100% at ~90°; linear map
    def knee_score(a): return _clamp01((180.0 - a) / (180.0 - 90.0))
    q = 0.5 * (knee_score(Lk) + knee_score(Rk))
    return int(round(100 * q))

def form_quality_sts(kps: np.ndarray) -> Optional[int]:
    # want knees to fully extend at stand (→ high quality)
    Lk, Rk = knee_angles(kps)
    if Lk is None or Rk is None: return None
    def ext_score(a): return _clamp01((a - 120.0) / (180.0 - 120.0))
    q = 0.5 * (ext_score(Lk) + ext_score(Rk))
    return int(round(100 * q))

def form_quality_legraise(kps: np.ndarray) -> Optional[int]:
    Lh = hip_angle_side(kps, 'l')
    Rh = hip_angle_side(kps, 'r')
    if Lh is None and Rh is None: return None
    vals = []
    if Lh is not None: vals.append(_clamp01((180.0 - Lh) / (180.0 - 90.0)))
    if Rh is not None: vals.append(_clamp01((180.0 - Rh) / (180.0 - 90.0)))
    if not vals: return None
    return int(round(100 * float(np.mean(vals))))

# ───────── exercise logic with hysteresis ─────────
def logic_squat(kps: np.ndarray, rc: RepCounter, frame=None):
    Lk, Rk = knee_angles(kps)
    if Lk is None or Rk is None: return
    down = (Lk < SQUAT_DOWN_MAX and Rk < SQUAT_DOWN_MAX)
    up   = (Lk > SQUAT_UP_MIN and Rk > SQUAT_UP_MIN)

    if rc.state == "":
        rc.state, rc.dwell = ("up", 0)
    elif rc.state == "up":
        rc.dwell = rc.dwell + 1 if down else 0
        if down and rc.dwell >= MIN_DWELL:
            rc.state, rc.dwell = ("down", 0)
    elif rc.state == "down":
        rc.dwell = rc.dwell + 1 if up else 0
        if up and rc.dwell >= MIN_DWELL:
            rc.reps += 1
            rc.state, rc.dwell = ("up", 0)

    q = form_quality_squat(kps)
    if q is not None: rc.form_pct = q

def logic_sts(kps: np.ndarray, rc: RepCounter, frame=None):
    Lk, Rk = knee_angles(kps)
    if Lk is None or Rk is None: return
    sit   = (Lk < STS_SIT_MAX and Rk < STS_SIT_MAX)
    stand = (Lk > STS_STAND_MIN and Rk > STS_STAND_MIN)

    if rc.state == "":
        rc.state, rc.dwell = ("sit", 0)
    elif rc.state == "sit":
        rc.dwell = rc.dwell + 1 if stand else 0
        if stand and rc.dwell >= MIN_DWELL:
            rc.reps += 1
            rc.state, rc.dwell = ("stand", 0)
    elif rc.state == "stand":
        rc.dwell = rc.dwell + 1 if sit else 0
        if sit and rc.dwell >= MIN_DWELL:
            rc.state, rc.dwell = ("sit", 0)

    q = form_quality_sts(kps)
    if q is not None: rc.form_pct = q

def logic_leg_raise(kps: np.ndarray, rc: RepCounter, frame=None):
    Lh = hip_angle_side(kps, 'l')
    Rh = hip_angle_side(kps, 'r')
    if Lh is None and Rh is None: return

    any_up = False; both_down = True
    if Lh is not None:
        any_up |= (Lh < LR_UP_MAX); both_down &= (Lh > LR_DOWN_MIN)
    if Rh is not None:
        any_up |= (Rh < LR_UP_MAX); both_down &= (Rh > LR_DOWN_MIN)

    if rc.state == "":
        rc.state, rc.dwell = ("down", 0)
    elif rc.state == "down":
        rc.dwell = rc.dwell + 1 if any_up else 0
        if any_up and rc.dwell >= MIN_DWELL:
            rc.state, rc.dwell = ("up", 0)
    elif rc.state == "up":
        rc.dwell = rc.dwell + 1 if both_down else 0
        if both_down and rc.dwell >= MIN_DWELL:
            rc.reps += 1
            rc.state, rc.dwell = ("down", 0)

    q = form_quality_legraise(kps)
    if q is not None: rc.form_pct = q

EXER_REG = {
    "squat": ("Squat", logic_squat),
    "sts": ("Sit to Stand", logic_sts),
    "leg_raise": ("Leg Raise", logic_leg_raise),
}

# ───────── drawing helpers ─────────
SKELETON = [
    (KP["lsh"], KP["rsh"]),
    (KP["lsh"], KP["lhip"]), (KP["rsh"], KP["rhip"]),
    (KP["lhip"], KP["rhip"]),
    (KP["lhip"], KP["lknee"]), (KP["lknee"], KP["lank"]),
    (KP["rhip"], KP["rknee"]), (KP["rknee"], KP["rank"]),
]

def draw_skeleton(img: np.ndarray, kps: np.ndarray):
    for i, j in SKELETON:
        p1, p2 = kps[i], kps[j]
        if _valid_point(p1) and _valid_point(p2):
            cv2.line(img, tuple(p1.astype(int)), tuple(p2.astype(int)), (255, 255, 255), 2)
    for p in kps:
        if _valid_point(p):
            cv2.circle(img, tuple(p.astype(int)), 3, (255, 255, 255), -1)
