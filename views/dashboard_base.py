from __future__ import annotations
from typing import Dict, Any
import customtkinter as ctk

from services.ui_theme import TOP_BG, CARD_BG, FIELD_BG


class DashboardBase(ctk.CTkFrame):
    """
    Shared top nav + body for all dashboards.
    Subclasses implement show_overview(), optionally show_calendar().
    """

    def __init__(self, parent, controller, title: str = "Dashboard"):
        super().__init__(parent, fg_color=TOP_BG)

        self.c = controller            # PoseCareApp
        self.user: Dict[str, Any] = {}
        self._title_text = title

        # ---------- Top nav bar ----------
        top = ctk.CTkFrame(self, fg_color=TOP_BG)
        top.pack(fill="x", padx=16, pady=(12, 8))

        ctk.CTkLabel(
            top,
            text=title,
            font=("Segoe UI", 20, "bold"),
            text_color="white",
        ).pack(side="left")

        spacer = ctk.CTkFrame(top, fg_color="transparent")
        spacer.pack(side="left", expand=True, fill="x")

        # Overview
        ctk.CTkButton(
            top,
            text="Overview",
            width=90,
            corner_radius=10,
            fg_color="#1f5eff",
            hover_color="#1a4ed6",
            command=self._nav_overview,
        ).pack(side="left", padx=(0, 6))

        # Calendar
        ctk.CTkButton(
            top,
            text="Calendar",
            width=90,
            corner_radius=10,
            fg_color="#1f5eff",
            hover_color="#1a4ed6",
            command=self._nav_calendar,
        ).pack(side="left", padx=(0, 6))

        # Upload / Review Video
        ctk.CTkButton(
            top,
            text="Upload Video",
            width=120,
            corner_radius=10,
            fg_color="transparent",
            text_color="white",
            border_width=1,
            border_color="#4b5563",
            hover_color="#2d2f36",
            command=self.c.open_video_area,  # NOTE: changed here
        ).pack(side="left", padx=(0, 6))

        # Logout
        ctk.CTkButton(
            top,
            text="Logout",
            width=80,
            corner_radius=10,
            fg_color="transparent",
            text_color="white",
            border_width=1,
            border_color="#4b5563",
            hover_color="#2d2f36",
            command=self.c.logout,
        ).pack(side="left")

        # ---------- Main body ----------
        self.body = ctk.CTkFrame(self, fg_color=TOP_BG)
        self.body.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    def clear_body(self):
        for child in self.body.winfo_children():
            child.destroy()

    def _nav_overview(self):
        if hasattr(self, "show_overview") and callable(self.show_overview):
            self.show_overview()

    def _nav_calendar(self):
        fn = getattr(self, "show_calendar", None)
        if callable(fn):
            fn()
            return

        # default stub for roles with no calendar tab
        self.clear_body()
        card = ctk.CTkFrame(self.body, fg_color=CARD_BG, corner_radius=16)
        card.pack(fill="both", expand=True, padx=8, pady=8)

        ctk.CTkLabel(
            card,
            text="No calendar view for this role.",
            font=("Segoe UI", 16),
            text_color="white",
        ).pack(padx=16, pady=16, anchor="w")
