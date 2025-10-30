from __future__ import annotations
import os
import webbrowser
import customtkinter as ctk
from tkinter import messagebox
from typing import Dict, Any, List

from services.ui_theme import TOP_BG, CARD_BG, FIELD_BG


class ReviewVideosPanel(ctk.CTkFrame):
    """
    For providers / coaches:
    Lists patient-submitted exercise videos addressed to this clinician.

    Renders:
    - patient name
    - exercise name
    - patient note
    - timestamp
    - "Play video" button
    """

    def __init__(self, parent, app_ref, clinician_user: Dict[str, Any]):
        super().__init__(parent, fg_color=TOP_BG)

        self.c = app_ref  # PoseCareApp (has fb, current role, etc.)
        self.clinician_user = clinician_user or {}
        self.clinician_uid = self.clinician_user.get("uid", "") or self.clinician_user.get("id", "")
        self.clinician_name = (
            self.clinician_user.get("name")
            or self.clinician_user.get("email")
            or "Provider"
        )

        # ---- outer card ----
        outer = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=16)
        outer.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            outer,
            text="Patient Exercise Videos",
            font=("Segoe UI", 18, "bold"),
            text_color="white",
        ).pack(anchor="w", padx=16, pady=(16, 4))

        ctk.CTkLabel(
            outer,
            text="Click a video to review form and performance.",
            font=("Segoe UI", 13),
            text_color="white",
        ).pack(anchor="w", padx=16, pady=(0, 12))

        # scrollable list container
        self.scroll = ctk.CTkScrollableFrame(
            outer,
            fg_color=CARD_BG,
            corner_radius=12,
        )
        self.scroll.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # load videos from Firestore
        try:
            submissions = self.c.fb.list_exercise_videos_for_provider(self.clinician_uid) or []
        except Exception as e:
            submissions = []
            messagebox.showerror("Error", f"Could not load videos:\n{e}")

        if not submissions:
            ctk.CTkLabel(
                self.scroll,
                text="No submitted videos yet.",
                font=("Segoe UI", 13),
                text_color="white",
            ).pack(anchor="w", padx=12, pady=12)
        else:
            for item in submissions:
                self._render_row(item)

    def _render_row(self, sub: Dict[str, Any]):
        """
        sub looks like:
        {
          "_id": "...",
          "patientAuthUid": "...",
          "patientName": "...",
          "clinicianUid": "...",
          "clinicianName": "...",
          "exerciseName": "...",
          "note": "...",
          "videoPath": "file://C:/.../patient_videos/...mp4",
          "createdAt": "2025-10-28T14:22:00+00:00"
        }
        """

        frame = ctk.CTkFrame(self.scroll, fg_color=FIELD_BG, corner_radius=10)
        frame.pack(fill="x", padx=12, pady=8)

        pt_name  = sub.get("patientName", "Unknown patient")
        exer     = sub.get("exerciseName", "Exercise")
        note     = sub.get("note", "")
        created  = sub.get("createdAt", "")
        vpath    = sub.get("videoPath", "")

        header_line = f"{pt_name} • {exer}"
        ctk.CTkLabel(
            frame,
            text=header_line,
            font=("Segoe UI", 14, "bold"),
            text_color="white",
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(12, 4))

        ctk.CTkLabel(
            frame,
            text=created,
            font=("Segoe UI", 11),
            text_color="#9ca3af",
        ).grid(row=0, column=1, sticky="e", padx=12, pady=(12, 4))

        ctk.CTkLabel(
            frame,
            text=f"Patient note: {note}",
            font=("Segoe UI", 13),
            text_color="white",
            justify="left",
            wraplength=480,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 8))

        def _play():
            if not vpath:
                messagebox.showinfo("No video", "No stored video path.")
                return
            # If it's a file:// URL we can open with webbrowser, or normal path.
            if vpath.startswith("file://"):
                webbrowser.open(vpath)
            else:
                # build file:// if it's a local path
                abs_p = os.path.abspath(vpath)
                webbrowser.open(f"file:///{abs_p}")

        play_btn = ctk.CTkButton(
            frame,
            text="Play video",
            width=100,
            corner_radius=8,
            fg_color="#1f5eff",
            hover_color="#1a4ed6",
            text_color="white",
            command=_play,
        )
        play_btn.grid(row=2, column=0, sticky="w", padx=12, pady=(0, 12))
