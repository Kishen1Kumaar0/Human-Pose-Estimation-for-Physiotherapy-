# PoseCare_app/views/dashboard_coach.py
from __future__ import annotations
from typing import Dict, Any, Optional

import customtkinter as ctk
from tkinter import messagebox

from services.ui_theme import TOP_BG, CARD_BG, FIELD_BG
from .dashboard_base import DashboardBase


class CoachDashboard(DashboardBase):
    """
    Dashboard for Coaches:
    - Overview: coach notes / observations you can save
    - Calendar: placeholder for future follow-up planning
    """

    def __init__(self, parent, controller):
        super().__init__(parent, controller, title="Dashboard • Coach")
        self.msg_box: Optional[ctk.CTkTextbox] = None

    def set_controller(self, controller):
        self.c = controller

    def load_user(self, user: Dict[str, Any]):
        self.user = user or {}
        self.show_overview()

    def show_overview(self):
        """
        Overview tab:
        - freeform note box
        - 'Save note' button that writes to feedback collection
        """
        self.clear_body()

        card = ctk.CTkFrame(self.body, fg_color=CARD_BG, corner_radius=16)
        card.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            card,
            text="Coach Notes",
            font=("Segoe UI", 16, "bold"),
            text_color="white",
        ).pack(anchor="w", padx=16, pady=(16, 4))

        self.msg_box = ctk.CTkTextbox(
            card,
            fg_color=FIELD_BG,
            border_width=0,
            text_color="white",
            height=160,
        )
        self.msg_box.pack(fill="x", padx=16, pady=(0, 8))
        self.msg_box.insert("end", "Write session notes / observations here...")

        ctk.CTkButton(
            card,
            text="Save note",
            width=100,
            corner_radius=10,
            fg_color="#1f5eff",
            hover_color="#1a4ed6",
            command=self._save_note,
        ).pack(anchor="e", padx=16, pady=(0, 16))

    def _save_note(self):
        """
        When coach hits "Save note":
        We'll store this note in feedback so it's persisted server-side.
        """
        if not self.msg_box:
            return

        text = self.msg_box.get("1.0", "end").strip()
        if not text:
            messagebox.showinfo("Empty", "Please type something first.")
            return

        try:
            user = self.user or {}
            uid = user.get("uid", "")
            # Reuse add_feedback() to persist the note.
            # We'll just store coach as both author and clinician.
            self.c.fb.add_feedback(
                patient_uid=uid,              # we attribute it to self for now
                clinician_uid=uid,
                clinician_name="Coach",
                text=text,
                patient_email=user.get("email", ""),
                patient_name=user.get("name", ""),
                patient_auth_uid=uid,
            )
            messagebox.showinfo("Saved", "Note saved.")
            self.msg_box.delete("1.0", "end")

        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def show_calendar(self):
        """
        Calendar tab for coach:
        For now it's just a placeholder explaining what will go here later.
        """
        self.clear_body()

        card = ctk.CTkFrame(self.body, fg_color=CARD_BG, corner_radius=16)
        card.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            card,
            text="Calendar / follow-ups for coach will go here.",
            font=("Segoe UI", 16, "bold"),
            text_color="white",
            wraplength=600,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            card,
            text="(Future: view assigned patients, plan next check-in.)",
            font=("Segoe UI", 14),
            text_color="white",
            wraplength=600,
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 16))
