# PoseCare_app/views/dashboard_provider.py
from __future__ import annotations
from typing import Dict, Any, Optional, List
import datetime

import customtkinter as ctk
from tkinter import messagebox

from services.ui_theme import TOP_BG, CARD_BG, FIELD_BG
from .dashboard_base import DashboardBase


class ProviderDashboard(DashboardBase):
    """
    Dashboard for Providers (clinicians / doctors / therapists).

    Tabs:
    - Overview: basic placeholder or upcoming list
    - Calendar: opens ProviderSchedulePanel where provider
        * picks a day
        * sees all slots / requests / bookings
        * accepts / rejects requests
    """

    def __init__(self, parent, controller):
        super().__init__(parent, controller, title="Dashboard • Provider")

        self.user: Dict[str, Any] = {}
        self.schedule_panel: Optional[ProviderSchedulePanel] = None

    def set_controller(self, controller):
        self.c = controller

    def load_user(self, user: Dict[str, Any]):
        self.user = user or {}
        self.show_overview()

    # ------------------- OVERVIEW TAB -------------------
    def show_overview(self):
        self.clear_body()

        card = ctk.CTkFrame(self.body, fg_color=CARD_BG, corner_radius=16)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            card,
            text="Provider Dashboard",
            font=("Segoe UI", 18, "bold"),
            text_color="white",
        ).pack(anchor="w", padx=16, pady=(16, 8))

        ctk.CTkLabel(
            card,
            text="Welcome back. Use the Calendar tab to review requests,\n"
                 "accept / reject sessions, and see open/free slots.",
            font=("Segoe UI", 14),
            text_color="white",
            justify="left",
        ).pack(anchor="w", padx=16, pady=(0, 16))

    # ------------------- CALENDAR TAB -------------------
    def show_calendar(self):
        """
        Show provider-facing calendar / request manager.
        """
        self.clear_body()

        card = ctk.CTkFrame(self.body, fg_color=CARD_BG, corner_radius=16)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            card,
            text="Schedule / Requests",
            font=("Segoe UI", 16, "bold"),
            text_color="white",
        ).pack(anchor="w", padx=16, pady=(16, 8))

        # panel with month picker + request list
        self.schedule_panel = ProviderSchedulePanel(
            card,
            provider_user=self.user,
            app_ref=self.c,  # PoseCareApp with fb + schedule
        )
        self.schedule_panel.pack(fill="both", expand=True, padx=16, pady=(0, 16))


class ProviderSchedulePanel(ctk.CTkFrame):
    """
    Panel for a single provider to:
      - choose a date
      - see sessions for that date
      - accept / reject patient requests

    Uses:
      app_ref.schedule.fetch_provider_bookings(day_iso, provider_id)
        -> list of {"id","date","time","patient_name","status"}

      and we update session status in Firestore using app_ref.fb
      (mimics AppController.accept_request/reject_request logic).
    """

    def __init__(self, parent, provider_user: Dict[str, Any], app_ref):
        super().__init__(parent, fg_color=CARD_BG, corner_radius=12)

        self.provider_user = provider_user or {}
        self.app_ref = app_ref  # PoseCareApp, has .schedule and .fb

        self.provider_id = self.provider_user.get("uid", "") or self.provider_user.get("id", "")
        self.provider_name = (
            self.provider_user.get("name")
            or self.provider_user.get("email")
            or "Provider"
        )

        # Date state
        self.current_month: datetime.date = datetime.date.today().replace(day=1)
        self.selected_day: datetime.date = datetime.date.today()

        # UI refs
        self.month_label: Optional[ctk.CTkLabel] = None
        self.calendar_days_frame: Optional[ctk.CTkFrame] = None
        self.day_title_label: Optional[ctk.CTkLabel] = None
        self.session_list_frame: Optional[ctk.CTkFrame] = None

        # build layout
        self._build_ui()
        self._refresh_all()

    # ---------------- LAYOUT ----------------
    def _build_ui(self):
        # 2 columns: left = mini calendar, right = today's sessions/requests
        shell = ctk.CTkFrame(self, fg_color=CARD_BG)
        shell.pack(fill="both", expand=True)

        shell.grid_columnconfigure(0, weight=1, uniform="col")
        shell.grid_columnconfigure(1, weight=2, uniform="col")
        shell.grid_rowconfigure(0, weight=1)

        # LEFT column (calendar picker)
        left_col = ctk.CTkFrame(shell, fg_color=FIELD_BG, corner_radius=10)
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, 12), pady=0)

        left_col.grid_columnconfigure(0, weight=1)
        left_col.grid_rowconfigure(3, weight=1)

        # Provider heading
        ctk.CTkLabel(
            left_col,
            text=f"{self.provider_name}",
            font=("Segoe UI", 14, "bold"),
            text_color="white",
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 4))

        ctk.CTkLabel(
            left_col,
            text="Select a date to review requests / slots.",
            font=("Segoe UI", 12),
            text_color="white",
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 12))

        # month header with prev/next
        mh = ctk.CTkFrame(left_col, fg_color=FIELD_BG)
        mh.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        mh.grid_columnconfigure(0, weight=1)
        mh.grid_columnconfigure(1, weight=0)
        mh.grid_columnconfigure(2, weight=0)

        self.month_label = ctk.CTkLabel(
            mh,
            text="",
            font=("Segoe UI", 14, "bold"),
            text_color="white",
        )
        self.month_label.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            mh,
            text="<",
            width=28,
            corner_radius=6,
            fg_color="#1f5eff",
            hover_color="#1a4ed6",
            command=self._go_prev_month,
        ).grid(row=0, column=1, padx=(8, 4))

        ctk.CTkButton(
            mh,
            text=">",
            width=28,
            corner_radius=6,
            fg_color="#1f5eff",
            hover_color="#1a4ed6",
            command=self._go_next_month,
        ).grid(row=0, column=2)

        # weekday header row
        weekday_frame = ctk.CTkFrame(left_col, fg_color=FIELD_BG)
        weekday_frame.grid(row=3, column=0, sticky="ew", padx=16)
        weekday_frame.grid_columnconfigure((0, 1, 2, 3, 4, 5, 6), weight=1)

        for i, wd in enumerate(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]):
            ctk.CTkLabel(
                weekday_frame,
                text=wd,
                font=("Segoe UI", 12, "bold"),
                text_color="white",
                anchor="center",
            ).grid(row=0, column=i, sticky="ew", pady=(0, 4))

        # day grid frame
        self.calendar_days_frame = ctk.CTkFrame(left_col, fg_color=FIELD_BG)
        self.calendar_days_frame.grid(
            row=4, column=0, sticky="nsew", padx=16, pady=(0, 16)
        )
        self.calendar_days_frame.grid_columnconfigure((0, 1, 2, 3, 4, 5, 6), weight=1)
        left_col.grid_rowconfigure(4, weight=1)

        # RIGHT column (session list for that date)
        right_col = ctk.CTkFrame(shell, fg_color=FIELD_BG, corner_radius=10)
        right_col.grid(row=0, column=1, sticky="nsew", padx=(12, 0), pady=0)

        right_col.grid_columnconfigure(0, weight=1)
        right_col.grid_rowconfigure(1, weight=1)

        # header with selected date text
        hdr = ctk.CTkFrame(right_col, fg_color=FIELD_BG)
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        hdr.grid_columnconfigure(0, weight=1)

        self.day_title_label = ctk.CTkLabel(
            hdr,
            text="",  # "Tue, Oct 28"
            font=("Segoe UI", 14, "bold"),
            text_color="white",
        )
        self.day_title_label.grid(row=0, column=0, sticky="w")

        # scroll-ish area for requests / slots
        self.session_list_frame = ctk.CTkFrame(
            right_col, fg_color=FIELD_BG
        )
        self.session_list_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.session_list_frame.grid_columnconfigure(0, weight=1)

    # ---------------- NAV / REFRESH ----------------
    def _go_prev_month(self):
        self.current_month = (self.current_month - datetime.timedelta(days=1)).replace(day=1)
        # snap selected_day to new month if out of range
        if (
            self.selected_day.year != self.current_month.year
            or self.selected_day.month != self.current_month.month
        ):
            self.selected_day = self.current_month
        self._refresh_all()

    def _go_next_month(self):
        self.current_month = (self.current_month + datetime.timedelta(days=32)).replace(day=1)
        if (
            self.selected_day.year != self.current_month.year
            or self.selected_day.month != self.current_month.month
        ):
            self.selected_day = self.current_month
        self._refresh_all()

    def _on_click_day(self, d: datetime.date):
        self.selected_day = d
        self._refresh_day_only()

    def _refresh_all(self):
        self._render_month_header()
        self._render_month_days()
        self._refresh_day_only()

    def _refresh_day_only(self):
        # update day header text for right pane
        if self.day_title_label is not None:
            self.day_title_label.configure(
                text=self.selected_day.strftime("%A, %b %d %Y")
            )
        # fetch and render sessions
        sessions = self._fetch_provider_sessions_for_day()
        self._render_sessions(sessions)

    # ---------------- RENDER: MONTH CALENDAR ----------------
    def _render_month_header(self):
        if self.month_label is not None:
            self.month_label.configure(
                text=self.current_month.strftime("%B %Y")
            )

    def _render_month_days(self):
        # clear old
        for w in self.calendar_days_frame.winfo_children():
            w.destroy()

        first = self.current_month  # first of month
        first_col = (first.weekday() + 1) % 7  # Sunday=0..Saturday=6
        next_month_first = (first + datetime.timedelta(days=32)).replace(day=1)
        last_of_month = next_month_first - datetime.timedelta(days=1)
        days_in_month = last_of_month.day

        row = 0
        col = first_col
        for day_num in range(1, days_in_month + 1):
            d = datetime.date(first.year, first.month, day_num)
            is_selected = (d == self.selected_day)

            fg_col = "#1f5eff" if is_selected else CARD_BG
            hov_col = "#1a4ed6" if is_selected else "#2d2f36"
            txt_col = "white"

            def mk_cmd(dd=d):
                return lambda: self._on_click_day(dd)

            btn = ctk.CTkButton(
                self.calendar_days_frame,
                text=str(day_num),
                width=32,
                height=28,
                corner_radius=6,
                fg_color=fg_col,
                hover_color=hov_col,
                text_color=txt_col,
                command=mk_cmd(),
            )
            btn.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")

            col += 1
            if col > 6:
                col = 0
                row += 1

    # ---------------- FETCH / RENDER SESSIONS ----------------
    def _fetch_provider_sessions_for_day(self) -> List[Dict[str, Any]]:
        """
        Calls FirestoreSchedule.fetch_provider_bookings(day_iso, provider_id)
        which returns list of dicts:
          { "id","date","time","patient_name","status" }
        """
        out: List[Dict[str, Any]] = []
        if not (self.app_ref and self.app_ref.schedule and self.provider_id):
            return out

        day_iso = self.selected_day.strftime("%Y-%m-%d")
        try:
            rows = self.app_ref.schedule.fetch_provider_bookings(day_iso, self.provider_id)
            out = rows or []
        except Exception as e:
            print("fetch_provider_bookings error:", e)
        return out

    def _render_sessions(self, sessions: List[Dict[str, Any]]):
        # clear UI
        for w in self.session_list_frame.winfo_children():
            w.destroy()

        if not sessions:
            ctk.CTkLabel(
                self.session_list_frame,
                text="No slots for this day.",
                font=("Segoe UI", 13),
                text_color="white",
                justify="left",
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
            return

        # we show each session row with time, patient, status, and maybe Accept/Reject
        for i, sess in enumerate(sessions):
            sid = sess.get("id", "")
            tm = sess.get("time", "")
            pat_name = sess.get("patient_name", "") or "(open slot)"
            status = sess.get("status", "") or "open"

            # Row frame
            rowf = ctk.CTkFrame(self.session_list_frame, fg_color=CARD_BG, corner_radius=8)
            rowf.grid(row=i, column=0, sticky="ew", padx=8, pady=8)
            rowf.grid_columnconfigure(0, weight=1)
            rowf.grid_columnconfigure(1, weight=0)

            # Left text block
            nice_line = f"{tm}  •  {pat_name}  [{status}]"
            ctk.CTkLabel(
                rowf,
                text=nice_line,
                font=("Segoe UI", 13),
                text_color="white",
                justify="left",
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)

            # Right action buttons
            # Only show Accept/Reject if this looks like a pending request
            # We consider "requested", "request", etc. as needing action.
            lower_status = status.lower()
            needs_action = (
                ("request" in lower_status)
                or (lower_status == "pending")
            )

            if needs_action and pat_name != "(open slot)":
                btns = ctk.CTkFrame(rowf, fg_color=CARD_BG)
                btns.grid(row=0, column=1, sticky="e", padx=8, pady=8)

                # Accept
                ctk.CTkButton(
                    btns,
                    text="Accept",
                    width=70,
                    corner_radius=6,
                    fg_color="#1f5eff",
                    hover_color="#1a4ed6",
                    text_color="white",
                    command=lambda booking_id=sid: self._update_booking_status(booking_id, "scheduled"),
                ).pack(side="left", padx=(0, 6))

                # Reject
                ctk.CTkButton(
                    btns,
                    text="Reject",
                    width=70,
                    corner_radius=6,
                    fg_color="#2d2f36",
                    hover_color="#444",
                    text_color="white",
                    command=lambda booking_id=sid: self._update_booking_status(booking_id, "rejected"),
                ).pack(side="left", padx=(0, 0))

    # ---------------- MUTATIONS (ACCEPT / REJECT) ----------------
    def _update_booking_status(self, booking_id: str, new_status: str):
        """
        Patch the Firestore doc for this session to set .status
        Exactly like AppController.accept_request/reject_request:
            - GET /sessions/{booking_id}
            - update fields["status"]
            - PATCH with the new status
        """
        if not booking_id:
            return
        if not (self.app_ref and hasattr(self.app_ref, "fb") and self.app_ref.fb):
            messagebox.showerror("Error", "No Firestore client.")
            return

        fb = self.app_ref.fb

        try:
            fb._ensure_token()
            headers = {"Authorization": f"Bearer {fb.id_token}"}
            url = fb._doc_url(f"sessions/{booking_id}")

            # load session doc
            import requests  # local import to avoid top-level cycle
            r = requests.get(url, headers=headers)
            if r.status_code != 200:
                raise RuntimeError(f"Load session failed: {r.text}")

            fields = r.json().get("fields", {})
            fields["status"] = fb._fv(new_status)

            r2 = requests.patch(url, headers=headers, json={"fields": fields})
            if r2.status_code not in (200, 201):
                raise RuntimeError(f"Update failed: {r2.text}")

            messagebox.showinfo("Updated", f"Marked session as '{new_status}'.")
            # refresh day view
            self._refresh_day_only()

        except Exception as e:
            messagebox.showerror("Error", f"Could not update status:\n{e}")
