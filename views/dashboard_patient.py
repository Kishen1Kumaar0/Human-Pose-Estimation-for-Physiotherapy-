# PoseCare_app/views/dashboard_patient.py
from __future__ import annotations
from typing import Dict, Any, Optional

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox

from services.ui_theme import TOP_BG, CARD_BG, FIELD_BG
from .dashboard_base import DashboardBase
from .calendar_panel import CalendarPanel


class PatientDashboard(DashboardBase):
    """
    Dashboard for Patients:
    - Overview tab:
        * metrics summary
        * feedback card with rating faces, reason, optional email, submit
    - Calendar tab:
        * booking / availability panel
    """

    def __init__(self, parent, controller):
        super().__init__(parent, controller, title="Dashboard • Patient")

        # stateful widgets across renders
        self.cal_panel: Optional[CalendarPanel] = None

        # feedback widgets / state
        self.rating_var: tk.IntVar = tk.IntVar(value=0)
        self.feedback_reason_box: Optional[ctk.CTkTextbox] = None
        self.feedback_email_entry: Optional[ctk.CTkEntry] = None

    # --- hooks app.py calls after login ---
    def set_controller(self, controller):
        self.c = controller

    def load_user(self, user: Dict[str, Any]):
        self.user = user or {}
        self.show_overview()

    # --- sections ---
    def show_overview(self):
        """Overview tab with metrics + feedback card."""
        self.clear_body()

        # -------------------------
        # METRICS CARD
        # -------------------------
        card_metrics = ctk.CTkFrame(self.body, fg_color=CARD_BG, corner_radius=16)
        card_metrics.pack(fill="x", padx=8, pady=8)

        # Try to pull metrics from Firestore via FirebaseClient helper.
        sessions_7d = 0
        total_reps = 0
        streak_days = 0
        next_session_iso = ""

        try:
            uid = self.user.get("uid", "")
            if uid:
                m = self.c.fb.get_patient_metrics(uid)
                sessions_7d = m.get("sessions_7d", 0)
                total_reps = m.get("total_reps", 0)
                streak_days = m.get("streak_days", 0)
                next_session_iso = m.get("next_session", "")
        except Exception:
            # if Firestore / token not ready, we just show defaults
            pass

        ctk.CTkLabel(
            card_metrics,
            text=f"Welcome, {self.user.get('name') or self.user.get('email') or 'Patient'}",
            font=("Segoe UI", 18, "bold"),
            text_color="white",
        ).pack(anchor="w", padx=16, pady=(16, 4))

        lines = [
            f"Sessions in last 7 days: {sessions_7d}",
            f"Total reps logged: {total_reps}",
            f"Current streak (days): {streak_days}",
            f"Next scheduled session: {next_session_iso or '—'}",
        ]
        ctk.CTkLabel(
            card_metrics,
            text="\n".join(lines),
            font=("Segoe UI", 14),
            text_color="white",
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 16))

        # -------------------------
        # FEEDBACK CARD
        # -------------------------
        card_fb = ctk.CTkFrame(self.body, fg_color=CARD_BG, corner_radius=16)
        card_fb.pack(fill="x", padx=8, pady=8)

        # Header row: "Rate your experience" + close button style (we won't wire the X because we keep it on dashboard)
        header_row = ctk.CTkFrame(card_fb, fg_color=CARD_BG)
        header_row.pack(fill="x", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            header_row,
            text="Rate your experience",
            font=("Segoe UI", 16, "bold"),
            text_color="white",
        ).pack(side="left", anchor="w")

        # FACES / RATING ROW
        faces_row = ctk.CTkFrame(card_fb, fg_color=CARD_BG)
        faces_row.pack(fill="x", padx=16, pady=(0, 12))

        # We'll simulate radio buttons with CTkRadioButton so only one is active.
        # 1 = 😡, 2 = 😟, 3 = 😐, 4 = 🙂, 5 = 😍
        face_options = [
            (1, "😡"),
            (2, "😟"),
            (3, "😐"),
            (4, "🙂"),
            (5, "😍"),
        ]

        for val, emoji in face_options:
            rb = ctk.CTkRadioButton(
                faces_row,
                text=emoji,
                value=val,
                variable=self.rating_var,
                fg_color="#1f5eff",            # dot color when selected
                hover_color="#1a4ed6",
                text_color="white",
                border_width_checked=3,
            )
            rb.pack(side="left", padx=6)

        # REASON FIELD
        reason_block = ctk.CTkFrame(card_fb, fg_color=CARD_BG)
        reason_block.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(
            reason_block,
            text="Thanks, what is the reason for your rating?",
            font=("Segoe UI", 14, "bold"),
            text_color="white",
        ).pack(anchor="w", pady=(0, 4))

        self.feedback_reason_box = ctk.CTkTextbox(
            reason_block,
            fg_color=FIELD_BG,
            border_width=0,
            text_color="white",
            height=70,
        )
        self.feedback_reason_box.pack(fill="x")

        # CONTACT FIELD
        contact_block = ctk.CTkFrame(card_fb, fg_color=CARD_BG)
        contact_block.pack(fill="x", padx=16, pady=(0, 12))

        ctk.CTkLabel(
            contact_block,
            text="Do you want us to respond to your feedback?",
            font=("Segoe UI", 14, "bold"),
            text_color="white",
        ).pack(anchor="w", pady=(0, 4))

        self.feedback_email_entry = ctk.CTkEntry(
            contact_block,
            placeholder_text="If yes, add your email",
            fg_color=FIELD_BG,
            border_width=0,
            text_color="white",
        )
        self.feedback_email_entry.pack(fill="x")

        # SUBMIT BUTTON
        submit_row = ctk.CTkFrame(card_fb, fg_color=CARD_BG)
        submit_row.pack(fill="x", padx=16, pady=(0, 16))

        submit_btn = ctk.CTkButton(
            submit_row,
            text="Submit",
            width=100,
            corner_radius=10,
            fg_color="#1f5eff",
            hover_color="#1a4ed6",
            command=self._submit_feedback,
        )
        submit_btn.pack(side="right")

    def _submit_feedback(self):
        """
        Collect rating, reason, and optional reply email,
        then push it to Firestore as 'feedback'.
        """
        rating_val = int(self.rating_var.get() or 0)

        if self.feedback_reason_box:
            reason_txt = self.feedback_reason_box.get("1.0", "end").strip()
        else:
            reason_txt = ""

        if self.feedback_email_entry:
            contact_txt = self.feedback_email_entry.get().strip()
        else:
            contact_txt = ""

        if rating_val == 0:
            messagebox.showinfo("Missing rating", "Please pick a face to rate your experience.")
            return

        if not reason_txt:
            messagebox.showinfo("Missing feedback", "Please describe why you chose that rating.")
            return

        try:
            # We'll store it using your existing client feedback method.
            # We treat this like a patient sending structured feedback to clinician.
            self.c.fb.add_feedback(
                patient_uid=self.user.get("uid", ""),
                clinician_uid=self.c.current_provider_id or "",
                clinician_name=self.c.current_provider_name or "",
                text=f"[rating={rating_val}] {reason_txt}\n(reply_email={contact_txt})",
                patient_email=self.user.get("email", ""),
                patient_name=self.user.get("name", ""),
                patient_auth_uid=self.user.get("uid", ""),
            )

            messagebox.showinfo("Thank you!", "Your feedback has been submitted.")
            # reset fields
            self.rating_var.set(0)
            if self.feedback_reason_box:
                self.feedback_reason_box.delete("1.0", "end")
            if self.feedback_email_entry:
                self.feedback_email_entry.delete(0, "end")

        except Exception as e:
            messagebox.showerror("Error", f"Could not submit feedback:\n{e}")

    def show_calendar(self):
        """Calendar / booking tab."""
        self.clear_body()

        card_cal = ctk.CTkFrame(self.body, fg_color=CARD_BG, corner_radius=16)
        card_cal.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            card_cal,
            text="Appointments",
            font=("Segoe UI", 16, "bold"),
            text_color="white",
        ).pack(anchor="w", padx=16, pady=(16, 8))

        # CalendarPanel internally builds month grid, slots, request / cancel, etc.
        self.cal_panel = CalendarPanel(card_cal, user=self.user, fb=self.c.fb)
        self.cal_panel.pack(fill="both", expand=True, padx=16, pady=(0, 16))
