"""
UploadVideoPage
---------------
Patient-facing screen to upload an already-recorded .mp4:

- choose file
- enter exercise name + optional notes
- send to assigned clinician/coach/provider
- actually copies the file locally and logs metadata in Firestore
- shows status to user

Providers / coaches should NOT land here. When they click "Upload Video",
they should get ReviewVideosPanel instead (that's handled in app.open_video_area()).
"""

from __future__ import annotations

import os
import shutil
import threading
import datetime
import customtkinter as ctk
from tkinter import filedialog, messagebox

from services.ui_theme import (
    GlassCard,
    TOP_BG,
    CARD_BG,
    FIELD_BG,
)


class UploadVideoPage(ctk.CTkFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=TOP_BG)

        self.c = controller  # PoseCareApp
        self.file_path: str | None = None
        self._busy = False

        outer_pad = 24

        # -----------------------
        # Header / Nav row
        # -----------------------
        header = ctk.CTkFrame(self, fg_color=TOP_BG)
        header.pack(side="top", fill="x", padx=outer_pad, pady=(16, 8))

        title_lbl = ctk.CTkLabel(
            header,
            text="Upload • Exercise Video",
            font=("Segoe UI", 20, "bold"),
            text_color="white",
        )
        title_lbl.pack(side="left")

        back_btn = ctk.CTkButton(
            header,
            text="Back to Dashboard",
            width=160,
            corner_radius=10,
            fg_color="transparent",
            text_color="white",
            border_width=1,
            border_color="#4b5563",
            hover_color="#2d2f36",
            command=self._go_dashboard,
        )
        back_btn.pack(side="right", padx=(6, 0))

        # -----------------------
        # Main card (2 columns)
        # -----------------------
        card = GlassCard(self, width=1120, height=520)
        card.pack(
            side="top",
            fill="both",
            expand=True,
            padx=outer_pad,
            pady=(0, outer_pad),
        )

        left_col = ctk.CTkFrame(card, fg_color=CARD_BG)
        left_col.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)

        right_col = ctk.CTkFrame(card, fg_color=CARD_BG)
        right_col.grid(row=0, column=1, sticky="nsew", padx=16, pady=16)

        card.grid_columnconfigure(0, weight=1)
        card.grid_columnconfigure(1, weight=1)
        card.grid_rowconfigure(0, weight=1)

        # -----------------------
        # File picker
        # -----------------------
        ctk.CTkLabel(
            left_col,
            text="Selected file:",
            text_color="white",
            font=("Segoe UI", 14, "bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))

        choose_btn = ctk.CTkButton(
            left_col,
            text="Choose .mp4",
            fg_color="#1f5eff",
            hover_color="#1a4ed6",
            width=140,
            command=self._choose_file,
        )
        choose_btn.grid(row=0, column=1, sticky="w")

        self.sel_file_val = ctk.CTkLabel(
            left_col,
            text="(none)",
            text_color="gray80",
        )
        self.sel_file_val.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 12)
        )

        # -----------------------
        # Exercise / Notes fields
        # -----------------------
        ctk.CTkLabel(
            left_col,
            text="Exercise / Activity name",
            text_color="white",
            font=("Segoe UI", 13, "bold"),
        ).grid(row=2, column=0, sticky="w", pady=(4, 4))

        ctk.CTkLabel(
            left_col,
            text="Notes for clinician (optional)",
            text_color="white",
            font=("Segoe UI", 13, "bold"),
        ).grid(row=2, column=1, sticky="w", pady=(4, 4))

        self.entry_exercise = ctk.CTkEntry(
            left_col,
            placeholder_text="e.g. knee flexion",
            fg_color=FIELD_BG,
            border_width=0,
            text_color="white",
            width=160,
        )
        self.entry_exercise.grid(
            row=3,
            column=0,
            sticky="nsew",
            padx=(0, 8)
        )

        self.entry_notes = ctk.CTkTextbox(
            left_col,
            fg_color=FIELD_BG,
            border_width=0,
            text_color="white",
            width=180,
            height=80,
        )
        self.entry_notes.insert(
            "1.0",
            "Any pain? Which rep? Anything to watch?"
        )
        self.entry_notes.grid(
            row=3,
            column=1,
            sticky="nsew"
        )

        # -----------------------
        # Upload button + status
        # -----------------------
        self.upload_btn = ctk.CTkButton(
            left_col,
            text="Upload",
            fg_color="#1f5eff",
            hover_color="#1a4ed6",
            width=260,
            command=self._start_upload_thread,
        )
        self.upload_btn.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(16, 8)
        )

        self.status_lbl = ctk.CTkLabel(
            left_col,
            text="",
            text_color="gray80",
            font=("Segoe UI", 12),
        )
        self.status_lbl.grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="w"
        )

        left_col.grid_columnconfigure(0, weight=1)
        left_col.grid_columnconfigure(1, weight=1)
        left_col.grid_rowconfigure(3, weight=1)

        # -----------------------
        # Right column placeholder (preview / future analysis)
        # -----------------------
        ctk.CTkLabel(
            right_col,
            text="(Preview / analysis area)",
            text_color="gray70",
        ).pack(anchor="center", pady=8)

        self.preview_box = ctk.CTkFrame(
            right_col,
            fg_color=FIELD_BG,
            corner_radius=10,
            height=400,
        )
        self.preview_box.pack(
            fill="both",
            expand=True,
            padx=8,
            pady=8
        )

    # ==================================================
    # Navigation back to dashboard
    # ==================================================
    def _go_dashboard(self):
        """Return to whatever dashboard this user should see."""
        try:
            self.c.show_dashboard(self.c.user)
        except Exception as e:
            messagebox.showerror("Navigation error", str(e))

    # ==================================================
    # Choose file (.mp4)
    # ==================================================
    def _choose_file(self):
        """Ask the user to pick a local .mp4."""
        if self._busy:
            return

        path = filedialog.askopenfilename(
            title="Select exercise video",
            filetypes=[("MP4 video", "*.mp4"), ("All files", "*.*")],
        )
        if path:
            self.file_path = path
            self.sel_file_val.configure(
                text=os.path.basename(path)
            )

    # ==================================================
    # Upload flow
    # ==================================================
    def _start_upload_thread(self):
        """
        Run upload on a background thread so UI doesn't freeze.
        Only patients are allowed to upload.
        """
        role = (self.c.current_role or "").lower()
        if "patient" not in role:
            messagebox.showinfo(
                "Not allowed",
                "Only patients can upload exercise videos.",
            )
            return

        if self._busy:
            return

        if not self.file_path:
            messagebox.showwarning(
                "Missing file",
                "Please select an .mp4 first.",
            )
            return

        self._busy = True
        self.upload_btn.configure(state="disabled")
        self.status_lbl.configure(
            text="Uploading..."
        )

        t = threading.Thread(
            target=self._upload_worker,
            daemon=True
        )
        t.start()

    def _upload_worker(self):
        """
        1. Copy the chosen .mp4 into ./patient_videos/
           (we create this folder if it's missing).
        2. Generate metadata (patient, clinician, notes, exercise).
        3. Write a Firestore record in 'exerciseVideos' using
           FirebaseClient.record_exercise_video_submission().
        4. Report success or failure back on main thread.
        """
        try:
            # -------------------------------------------------
            # 1. Ensure output folder exists
            # -------------------------------------------------
            out_dir = os.path.abspath("patient_videos")
            os.makedirs(out_dir, exist_ok=True)

            # Unique filename: <patientUid>_<timestamp>_<origName>.mp4
            ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            base_name = os.path.basename(self.file_path or "video.mp4")
            safe_uid = self.c.user.get("uid", "unknown")
            new_name = f"{safe_uid}_{ts}_{base_name}"
            dest_path = os.path.join(out_dir, new_name)

            # Copy file locally
            shutil.copy2(self.file_path, dest_path)

            # Build file:// URL that we can open later in provider review
            normalized_path = dest_path.replace("\\", "/")
            video_url = f"file:///{normalized_path}"

            # -------------------------------------------------
            # 2. Collect upload metadata from UI + app state
            # -------------------------------------------------
            exercise_name = self.entry_exercise.get().strip()
            note = self.entry_notes.get("1.0", "end").strip()

            patient_uid = self.c.user.get("uid", "")
            patient_name = (
                self.c.user.get("name")
                or self.c.user.get("email")
                or "Patient"
            )

            clinician_uid = self.c.current_provider_id or ""
            clinician_name = (
                self.c.current_provider_name
                or "Provider"
            )

            # -------------------------------------------------
            # 3. Write Firestore record (exerciseVideos)
            # -------------------------------------------------
            # This persists metadata:
            # {
            #   patientAuthUid,
            #   patientName,
            #   clinicianUid,
            #   clinicianName,
            #   exerciseName,
            #   note,
            #   videoPath,
            #   createdAt
            # }
            self.c.fb.record_exercise_video_submission(
                patient_auth_uid=patient_uid,
                patient_name=patient_name,
                clinician_uid=clinician_uid,
                clinician_name=clinician_name,
                exercise_name=exercise_name,
                note=note,
                video_path=video_url,
            )

            # -------------------------------------------------
            # 4. Notify success on the Tk main thread
            # -------------------------------------------------
            self.after(0, self._on_upload_success)

        except Exception as e:
            # Notify error on the Tk main thread (capture e safely)
            err_msg = str(e)
            self.after(0, lambda msg=err_msg: self._on_upload_error(msg))

    # ==================================================
    # Upload callbacks (main thread UI updates)
    # ==================================================
    def _on_upload_success(self):
        self._busy = False
        self.upload_btn.configure(state="normal")
        self.status_lbl.configure(
            text="Upload complete.",
            text_color="gray80",
        )
        messagebox.showinfo(
            "Upload complete",
            "Your video and notes have been sent to your clinician."
        )

    def _on_upload_error(self, msg: str):
        self._busy = False
        self.upload_btn.configure(state="normal")
        self.status_lbl.configure(
            text="Upload failed.",
            text_color="red",
        )
        messagebox.showerror(
            "Upload error",
            msg,
        )
