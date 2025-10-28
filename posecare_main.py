# posecare_main.py
from __future__ import annotations
import os, time
from typing import Optional, Tuple

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from posecare_core import (
    EMAStabilizer, RepCounter, EXER_REG, draw_skeleton
)

MODEL_NAME = os.getenv("POSE_MODEL", "yolov8n-pose.pt")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

RES_MODES = [(1920,1080), (1280,720), (960,540), (640,480)]
RES_IDX = 1

IMG_SIZE = int(os.getenv("IMG_SIZE", "832"))   # a bit bigger for more stable keypoints
FONT = cv2.FONT_HERSHEY_SIMPLEX
HUD = (255,255,255)

OUTPUT_DIR = os.path.join(os.path.expanduser("~"), "Videos")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def UIS(w:int,h:int)->float:
    return max(1.0, min(w,h)/720.0)

# ───────── camera ─────────
def set_capture_props(cap, w, h, fps=30):
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS,          fps)
    try: cap.set(cv2.CAP_PROP_ZOOM, 0)
    except Exception: pass

def open_capture(index=0, w=1280, h=720, fps=30):
    cap = cv2.VideoCapture(index, cv2.CAP_MSMF)
    if not cap.isOpened(): cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened(): cap = cv2.VideoCapture(index)
    if not cap.isOpened(): return None
    set_capture_props(cap, w, h, fps)
    return cap

# ───────── selection (+persistence) ─────────
def _bbox_center_bonus(xyxy: np.ndarray, W: int, H: int) -> float:
    x1,y1,x2,y2 = xyxy
    cx = 0.5*(x1+x2)/max(1.0,W); cy = 0.5*(y1+y2)/max(1.0,H)
    dx, dy = cx-0.5, cy-0.5
    dist = (dx*dx + dy*dy)**0.5
    return max(0.0, 0.15 - dist)

def _iou(a, b):
    if a is None or b is None: return 0.0
    ax1,ay1,ax2,ay2 = a; bx1,by1,bx2,by2 = b
    ix1,iy1 = max(ax1,bx1), max(ay1,by1)
    ix2,iy2 = min(ax2,bx2), min(ay2,by2)
    iw, ih = max(0.0, ix2-ix1), max(0.0, iy2-iy1)
    inter = iw*ih
    areaA = max(0.0, (ax2-ax1)*(ay2-ay1))
    areaB = max(0.0, (bx2-bx1)*(by2-by1))
    denom = areaA + areaB - inter + 1e-6
    return inter/denom

def pick_best_person(res, W:int, H:int, prev_bb=None):
    if res is None or res.keypoints is None or len(res.keypoints)==0:
        return None, None, None, None
    kxy   = res.keypoints.xy
    kconf = res.keypoints.conf
    boxes = res.boxes.xyxy if res.boxes is not None else None
    if kxy is None or kconf is None or boxes is None:
        return None, None, None, None

    # prefer same track if IoU high
    best_i, best_s = None, -1e9
    for i in range(kxy.shape[0]):
        bb = boxes[i].cpu().numpy()
        mean_conf = float(np.nanmean(kconf[i].cpu().numpy()))
        bonus = _bbox_center_bonus(bb, W, H)
        score = mean_conf + bonus + (0.20 * _iou(prev_bb, bb))  # persistence bias
        if score > best_s:
            best_s, best_i = score, i

    if best_i is None: return None, None, None, None
    return (best_i,
            kxy[best_i].cpu().numpy().astype(np.float32),
            kconf[best_i].cpu().numpy().astype(np.float32),
            boxes[best_i].cpu().numpy().astype(np.float32))

# ───────── HUD ─────────
def draw_quality_bar(frame, mean_conf, s):
    h,w = frame.shape[:2]
    bw,bh = int(220*s), int(16*s)
    x,y = int(14*s), h - int(30*s)
    cv2.rectangle(frame,(x-2,y-2),(x+bw+2,y+bh+2),(30,30,30),1)
    fill = int(bw*max(0.0,min(1.0,mean_conf)))
    col = (80,200,80) if mean_conf>=0.75 else ((60,160,220) if mean_conf>=0.55 else (40,40,180))
    cv2.rectangle(frame,(x,y),(x+fill,y+bh),col,-1)
    cv2.putText(frame,f"Quality  {mean_conf*100:.0f}%",(x,y-int(6*s)),FONT,0.5*s,HUD,1,cv2.LINE_AA)

def put_simple_hud(frame, ex_name, reps, state, form_pct):
    h,w = frame.shape[:2]; s = UIS(w,h)
    # Title (left)
    cv2.putText(frame, ex_name, (int(16*s), int(48*s)), FONT, 1.2*s, HUD, int(3*s), cv2.LINE_AA)
    # Reps (center top)
    rt = f"Reps:  {reps}"
    (tw,_), _ = cv2.getTextSize(rt, FONT, 1.2*s, int(3*s))
    cv2.putText(frame, rt, (w//2 - tw//2, int(48*s)), FONT, 1.2*s, HUD, int(3*s), cv2.LINE_AA)
    # State (right)
    cv2.putText(frame, f"State:  {state or '—'}", (w - int(300*s), int(48*s)), FONT, 1.0*s, HUD, int(3*s), cv2.LINE_AA)
    # Form % (right side, mid)
    form_text = f"Form: {form_pct:3d}%"
    cv2.putText(frame, form_text, (w - int(260*s), int(120*s)), FONT, 1.0*s, HUD, int(3*s), cv2.LINE_AA)

def draw_help_panel(frame, recording):
    """Big readable options panel (toggle with H)."""
    h,w = frame.shape[:2]; s = UIS(w,h)
    overlay = frame.copy()
    pad = int(16*s)
    x1,y1,x2,y2 = pad, int(90*s), w - pad, h - int(90*s)
    cv2.rectangle(overlay,(x1,y1),(x2,y2),(0,0,0),-1)
    frame[:] = cv2.addWeighted(overlay, 0.35, frame, 0.65, 0)

    LeftX = x1 + int(24*s)
    RightX = w - int(420*s)
    lh = int(48*s)

    cv2.putText(frame,"Exercises", (LeftX, y1+lh), FONT, 1.1*s, HUD, int(3*s), cv2.LINE_AA)
    items = [("[1]  Squat"), ("[2]  Sit to Stand"), ("[3]  Leg Raise")]
    for i,t in enumerate(items, start=2):
        cv2.putText(frame, t, (LeftX, y1 + i*lh), FONT, 1.0*s, HUD, int(2*s), cv2.LINE_AA)

    cv2.putText(frame,"Controls", (RightX, y1+lh), FONT, 1.1*s, HUD, int(3*s), cv2.LINE_AA)
    ctrls = [
        "[R]  Reset Counter",
        "[V]  Start/Stop Recording",
        "[H]  Toggle Help Panel",
        "[[ / ]]  Cycle Resolution (zoom out/in)",
        "[Q / ESC]  Quit"
    ]
    for i,t in enumerate(ctrls, start=2):
        cv2.putText(frame, t, (RightX, y1 + i*lh), FONT, 1.0*s, HUD, int(2*s), cv2.LINE_AA)

    # recording badge
    if recording:
        cv2.circle(frame, (RightX, y2 - int(40*s)), int(12*s), (0,0,255), -1)
        cv2.putText(frame, "REC", (RightX + int(26*s), y2 - int(34*s)), FONT, 0.9*s, (0,0,255), int(3*s), cv2.LINE_AA)

# ───────── main ─────────
def main():
    global RES_IDX
    print(f"[INFO] Loading model: {MODEL_NAME} on {DEVICE}")
    model = YOLO(MODEL_NAME).to(DEVICE)

    W,H = RES_MODES[RES_IDX]
    cap = open_capture(0, W, H, 30)
    if cap is None: raise RuntimeError("Cannot open camera.")
    cv2.namedWindow("PoseCare", cv2.WINDOW_NORMAL); cv2.resizeWindow("PoseCare", W, H)

    rc = RepCounter(exercise="squat")
    stab = EMAStabilizer(alpha_fast=0.45, alpha_slow=0.15)

    writer, recording = None, False
    last_ex = EXER_REG[rc.exercise][0]
    show_help = True
    prev_bb = None

    while True:
        ok, frame = cap.read()
        if not ok: break
        H,W = frame.shape[:2]; s = UIS(W,H)

        # Pose
        res = model.predict(source=frame, imgsz=IMG_SIZE, conf=0.30, iou=0.50,
                            verbose=False, device=DEVICE)[0]
        best_idx, kxy, kconf, bbox = pick_best_person(res, W, H, prev_bb)
        prev_bb = bbox if bbox is not None else prev_bb

        # quality
        mean_conf = 0.0
        if kconf is not None:
            m = float(np.nanmean(kconf)); mean_conf = 0.0 if not np.isfinite(m) else max(0.0,min(1.0,m))

        # step-back hint
        if bbox is not None:
            x1,y1,x2,y2 = bbox; frac = (y2-y1)/max(1.0,float(H))
            if frac > 0.80:
                cv2.putText(frame, "Step back a little for full-body",
                            (int(16*s), int(80*s)), FONT, 0.9*s, (0,0,255), int(3*s), cv2.LINE_AA)

        # stabilize & logic
        kps = stab.update(kxy, kconf) if (kxy is not None and kconf is not None) else None
        if kps is not None and kps.shape == (17,2):
            draw_skeleton(frame, kps)
            _, logic_fn = EXER_REG[rc.exercise]
            try: logic_fn(kps, rc, frame)
            except Exception: pass

        # top HUD
        ex_name, _ = EXER_REG[rc.exercise]
        if ex_name != last_ex: last_ex = ex_name
        put_simple_hud(frame, ex_name, rc.reps, rc.state, rc.form_pct)
        draw_quality_bar(frame, mean_conf, s)

        # help panel (toggle)
        if show_help:
            draw_help_panel(frame, recording)

        # record
        if recording:
            if writer is None:
                ts = time.strftime("%Y%m%d-%H%M%S")
                path = os.path.join(OUTPUT_DIR, f"posecare_{last_ex}_{ts}.mp4")
                fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                writer = cv2.VideoWriter(path, fourcc, 30, (W, H))
                print(f"[REC] {path}")
            writer.write(frame)
        else:
            if writer is not None: writer.release(); writer = None

        cv2.imshow("PoseCare", frame)
        k = cv2.waitKey(1) & 0xFF

        # Controls
        if k in (ord('q'), 27): break
        elif k == ord('r'): rc.reset()
        elif k == ord('v'): recording = not recording
        elif k == ord('h'): show_help = not show_help
        elif k == ord('1'): rc.reset("squat")
        elif k == ord('2'): rc.reset("sts")
        elif k == ord('3'): rc.reset("leg_raise")
        elif k in (ord('['), ord(']')):
            RES_IDX = (RES_IDX - 1) % len(RES_MODES) if k == ord('[') else (RES_IDX + 1) % len(RES_MODES)
            newW,newH = RES_MODES[RES_IDX]
            print(f"[CAM] switching to {newW}x{newH}")
            set_capture_props(cap, newW, newH, 30); cv2.resizeWindow("PoseCare", newW, newH)

    if writer is not None: writer.release()
    cap.release(); cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
