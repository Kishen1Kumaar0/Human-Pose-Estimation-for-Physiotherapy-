from __future__ import annotations
import datetime
from typing import Dict, Any, Optional, List

import customtkinter as ctk
from tkinter import messagebox, StringVar

from services.ui_theme import TOP_BG, CARD_BG, FIELD_BG


class CalendarPanel(ctk.CTkFrame):
    """
    Patient booking panel.

    Left column:
        - Provider dropdown
        - Month calendar (pick a date)
    Middle column:
        - Time slots for that date (real availability, or fallback 09:00-17:00)
    Right column:
        - Session Details (selected provider/date/time)
        - Request session button
        - "My bookings on this day" list (+ Cancel buttons)
    """

    def __init__(self, parent, user: Dict[str, Any], fb):
        super().__init__(parent, fg_color=TOP_BG)

        self.user = user or {}
        self.fb = fb  # FirebaseClient (already signed in by app.py)
        self.app_ref = getattr(self.master.master.master, "c", None)  # PoseCareApp instance

        # Provider selection
        self.provider_var: StringVar = StringVar(value="")
        self.provider_id: str = ""
        self.provider_name: str = ""

        # Date selection
        self.current_month: datetime.date = datetime.date.today().replace(day=1)
        self.selected_day: datetime.date = datetime.date.today()

        # Time slot selection
        self.selected_time: Optional[str] = None  # "HH:MM"

        # UI refs we update
        self.month_label: Optional[ctk.CTkLabel] = None
        self.calendar_days_frame: Optional[ctk.CTkFrame] = None

        self.day_title_label: Optional[ctk.CTkLabel] = None
        self.times_frame: Optional[ctk.CTkFrame] = None

        self.details_when_label: Optional[ctk.CTkLabel] = None
        self.book_btn: Optional[ctk.CTkButton] = None
        self.bookings_list_frame: Optional[ctk.CTkFrame] = None

        # Build layout
        self._build_ui()

        # Load providers and default selection
        self._init_provider_defaults()

        # Initial render
        self._refresh_all()

    # -------------------------------------------------
    # UI STRUCTURE
    # -------------------------------------------------
    def _build_ui(self):
        # Outer wrapper card "Appointments"
        outer = ctk.CTkFrame(self, fg_color=CARD_BG, corner_radius=12)
        outer.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            outer,
            text="Appointments",
            font=("Segoe UI", 16, "bold"),
            text_color="white",
        ).pack(anchor="w", padx=16, pady=(16, 8))

        body = ctk.CTkFrame(outer, fg_color=CARD_BG)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        # 3 responsive columns
        body.grid_columnconfigure(0, weight=1, uniform="col")
        body.grid_columnconfigure(1, weight=1, uniform="col")
        body.grid_columnconfigure(2, weight=1, uniform="col")
        body.grid_rowconfigure(0, weight=1)

        # ---- COL 1: Provider + Calendar ----
        col1 = ctk.CTkFrame(body, fg_color=FIELD_BG, corner_radius=10)
        col1.grid(row=0, column=0, sticky="nsew", padx=(0, 12), pady=0)

        col1.grid_columnconfigure(0, weight=1)
        # provider dropdown
        prov_wrap = ctk.CTkFrame(col1, fg_color=FIELD_BG)
        prov_wrap.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 12))
        prov_wrap.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            prov_wrap,
            text="Select provider",
            font=("Segoe UI", 14, "bold"),
            text_color="white",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.provider_dropdown = ctk.CTkOptionMenu(
            prov_wrap,
            variable=self.provider_var,
            values=[],
            width=200,
            fg_color=FIELD_BG,
            button_color="#1f5eff",
            button_hover_color="#1a4ed6",
            text_color="white",
            dropdown_fg_color=CARD_BG,
            dropdown_hover_color="#1f5eff",
            dropdown_text_color="white",
            command=self._on_provider_change,
        )
        self.provider_dropdown.grid(row=1, column=0, sticky="w")

        # Calendar header row: month + arrows
        cal_header = ctk.CTkFrame(col1, fg_color=FIELD_BG)
        cal_header.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        cal_header.grid_columnconfigure(0, weight=1)
        cal_header.grid_columnconfigure(1, weight=0)
        cal_header.grid_columnconfigure(2, weight=0)

        self.month_label = ctk.CTkLabel(
            cal_header,
            text="",
            font=("Segoe UI", 14, "bold"),
            text_color="white",
        )
        self.month_label.grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            cal_header,
            text="<",
            width=28,
            corner_radius=6,
            fg_color="#1f5eff",
            hover_color="#1a4ed6",
            command=self._go_prev_month,
        ).grid(row=0, column=1, padx=(8, 4), sticky="e")

        ctk.CTkButton(
            cal_header,
            text=">",
            width=28,
            corner_radius=6,
            fg_color="#1f5eff",
            hover_color="#1a4ed6",
            command=self._go_next_month,
        ).grid(row=0, column=2, sticky="e")

        # Weekday row
        weekdays = ctk.CTkFrame(col1, fg_color=FIELD_BG)
        weekdays.grid(row=2, column=0, sticky="ew", padx=16)
        weekdays.grid_columnconfigure((0, 1, 2, 3, 4, 5, 6), weight=1)

        for i, wd in enumerate(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]):
            ctk.CTkLabel(
                weekdays,
                text=wd,
                font=("Segoe UI", 12, "bold"),
                text_color="white",
                anchor="center",
            ).grid(row=0, column=i, sticky="ew", pady=(0, 4))

        # Day grid
        self.calendar_days_frame = ctk.CTkFrame(col1, fg_color=FIELD_BG)
        self.calendar_days_frame.grid(
            row=3, column=0, sticky="nsew", padx=16, pady=(0, 16)
        )
        self.calendar_days_frame.grid_columnconfigure((0, 1, 2, 3, 4, 5, 6), weight=1)
        col1.grid_rowconfigure(3, weight=1)

        # ---- COL 2: Time slots for chosen date/provider ----
        col2 = ctk.CTkFrame(body, fg_color=FIELD_BG, corner_radius=10)
        col2.grid(row=0, column=1, sticky="nsew", padx=(12, 12), pady=0)
        col2.grid_columnconfigure(0, weight=1)
        col2.grid_rowconfigure(1, weight=1)

        # Date header ("Tuesday, Oct 28")
        header2 = ctk.CTkFrame(col2, fg_color=FIELD_BG)
        header2.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        header2.grid_columnconfigure(0, weight=1)

        self.day_title_label = ctk.CTkLabel(
            header2,
            text="",
            font=("Segoe UI", 14, "bold"),
            text_color="white",
        )
        self.day_title_label.grid(row=0, column=0, sticky="w")

        # times grid
        self.times_frame = ctk.CTkFrame(col2, fg_color=FIELD_BG)
        self.times_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.times_frame.grid_columnconfigure(0, weight=1)

        # ---- COL 3: Session details + bookings ----
        col3 = ctk.CTkFrame(body, fg_color=FIELD_BG, corner_radius=10)
        col3.grid(row=0, column=2, sticky="nsew", padx=(12, 0), pady=0)

        col3.grid_columnconfigure(0, weight=1)
        col3.grid_rowconfigure(2, weight=1)

        # Session details box
        details_box = ctk.CTkFrame(col3, fg_color=FIELD_BG)
        details_box.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        details_box.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            details_box,
            text="Session Details",
            font=("Segoe UI", 14, "bold"),
            text_color="white",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        detail_inner = ctk.CTkFrame(details_box, fg_color=CARD_BG, corner_radius=8)
        detail_inner.grid(row=1, column=0, sticky="ew")
        detail_inner.grid_columnconfigure(0, weight=1)

        self.details_when_label = ctk.CTkLabel(
            detail_inner,
            text="Select a time slot...",
            font=("Segoe UI", 13),
            text_color="white",
            justify="left",
        )
        self.details_when_label.grid(row=0, column=0, sticky="w", padx=12, pady=(12, 8))

        self.book_btn = ctk.CTkButton(
            detail_inner,
            text="Request session",
            width=140,
            corner_radius=8,
            fg_color="#1f5eff",
            hover_color="#1a4ed6",
            command=self._confirm_booking,
            state="disabled",
        )
        self.book_btn.grid(row=1, column=0, sticky="e", padx=12, pady=(0, 12))

        # Bookings list (for that day)
        bookings_box = ctk.CTkFrame(col3, fg_color=FIELD_BG)
        bookings_box.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        bookings_box.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            bookings_box,
            text="My bookings on this day",
            font=("Segoe UI", 14, "bold"),
            text_color="white",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.bookings_list_frame = ctk.CTkFrame(
            bookings_box, fg_color=CARD_BG, corner_radius=8
        )
        self.bookings_list_frame.grid(row=1, column=0, sticky="ew")
        self.bookings_list_frame.grid_columnconfigure(0, weight=1)

    # -------------------------------------------------
    # PROVIDER HANDLING
    # -------------------------------------------------
    def _init_provider_defaults(self):
        """
        Populate provider dropdown from FirebaseClient.list_providers().
        """
        try:
            providers = self.fb.list_providers() or []
        except Exception:
            providers = []

        # build lookup lists
        self._provider_lookup = []  # list[(id, name)]
        dropdown_names: List[str] = []

        for p in providers:
            pid = p.get("uid", "") or p.get("id", "")
            pname = p.get("name", "") or p.get("email", "") or "(unnamed)"
            if not pid:
                continue
            self._provider_lookup.append((pid, pname))
            dropdown_names.append(pname)

        if dropdown_names:
            self.provider_dropdown.configure(values=dropdown_names)

            # choose default: from app_ref if available, else first
            if (
                self.app_ref
                and self.app_ref.current_provider_name
                in dropdown_names
            ):
                default_name = self.app_ref.current_provider_name
            else:
                default_name = dropdown_names[0]

            self.provider_var.set(default_name)
            self._set_provider_by_name(default_name)
        else:
            self.provider_dropdown.configure(values=["(no providers)"])
            self.provider_var.set("(no providers)")
            self.provider_id = ""
            self.provider_name = ""

    def _set_provider_by_name(self, name: str):
        for pid, pname in self._provider_lookup:
            if pname == name:
                self.provider_id = pid
                self.provider_name = pname
                return
        # fallback
        self.provider_id = ""
        self.provider_name = name

    def _on_provider_change(self, chosen_name: str):
        self._set_provider_by_name(chosen_name)
        # reset current selection
        self.selected_time = None
        self._refresh_all()

    # -------------------------------------------------
    # MONTH / DAY NAVIGATION
    # -------------------------------------------------
    def _go_prev_month(self):
        # go to previous month (first of previous month)
        self.current_month = (self.current_month - datetime.timedelta(days=1)).replace(day=1)
        # if selected_day fell outside new month, snap it
        if (
            self.selected_day.year != self.current_month.year
            or self.selected_day.month != self.current_month.month
        ):
            self.selected_day = self.current_month
            self.selected_time = None
        self._refresh_all()

    def _go_next_month(self):
        # jump ~32 days ahead then snap to day=1
        self.current_month = (self.current_month + datetime.timedelta(days=32)).replace(day=1)
        if (
            self.selected_day.year != self.current_month.year
            or self.selected_day.month != self.current_month.month
        ):
            self.selected_day = self.current_month
            self.selected_time = None
        self._refresh_all()

    def _on_click_day(self, day_date: datetime.date):
        self.selected_day = day_date
        self.selected_time = None
        self._refresh_day_only()

    # -------------------------------------------------
    # RENDER PIPELINE
    # -------------------------------------------------
    def _refresh_all(self):
        """
        Re-render calendar month and then refresh the selected day state.
        """
        self._render_month_header()
        self._render_month_days()
        self._refresh_day_only()

    def _refresh_day_only(self):
        """
        Refresh:
          - middle column slots
          - right column details
          - bookings list
        """
        # update day title "Tuesday, Oct 28"
        if self.day_title_label:
            self.day_title_label.configure(
                text=self.selected_day.strftime("%A, %b %d")
            )

        # build available slots list
        available_slots = self._fetch_available_slots_for_day()
        # build patient bookings
        bookings_today = self._fetch_my_bookings_for_day()

        self._render_slots(available_slots)
        self._render_selection_summary()
        self._render_bookings(bookings_today)

    def _render_month_header(self):
        # Month header text, e.g. "October 2025"
        if self.month_label:
            self.month_label.configure(
                text=self.current_month.strftime("%B %Y")
            )

    def _render_month_days(self):
        # wipe old day buttons
        for w in self.calendar_days_frame.winfo_children():
            w.destroy()

        start = self.current_month
        # weekday() Mon=0..Sun=6, but we display Sun..Sat columns [0..6]
        # convert so Sunday -> column 0
        first_col = (start.weekday() + 1) % 7

        # days in this month:
        next_month_first = (start + datetime.timedelta(days=32)).replace(day=1)
        last_day_this_month = next_month_first - datetime.timedelta(days=1)
        num_days = last_day_this_month.day

        row = 0
        col = first_col
        for day_num in range(1, num_days + 1):
            d = datetime.date(start.year, start.month, day_num)

            is_selected = (d == self.selected_day)
            btn_fg = "#1f5eff" if is_selected else CARD_BG
            btn_hover = "#1a4ed6" if is_selected else "#2d2f36"
            txt_color = "white"

            def make_cmd(dd=d):
                return lambda: self._on_click_day(dd)

            b = ctk.CTkButton(
                self.calendar_days_frame,
                text=str(day_num),
                width=32,
                height=28,
                corner_radius=6,
                fg_color=btn_fg,
                hover_color=btn_hover,
                text_color=txt_color,
                command=make_cmd(),
            )
            b.grid(row=row, column=col, padx=2, pady=2, sticky="nsew")

            col += 1
            if col > 6:
                col = 0
                row += 1

    def _render_slots(self, slots: List[str]):
        # clear old content
        for w in self.times_frame.winfo_children():
            w.destroy()

        if not self.provider_id:
            ctk.CTkLabel(
                self.times_frame,
                text="No provider selected.",
                font=("Segoe UI", 13),
                text_color="white",
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)
            return

        if not slots:
            # fallback times 09:00 -> 17:00 every hour
            slots = [f"{h:02d}:00" for h in range(9, 18)]

        # make a 2-column grid of buttons (more like your example)
        self.times_frame.grid_columnconfigure(0, weight=1)
        self.times_frame.grid_columnconfigure(1, weight=1)

        r = 0
        c = 0
        for t24 in slots:
            def cmd(tt=t24):
                return lambda: self._select_time(tt)

            pretty = self._format_time_label(t24)

            btn = ctk.CTkButton(
                self.times_frame,
                text=pretty,
                height=36,
                corner_radius=6,
                fg_color="#1f5eff",
                hover_color="#1a4ed6",
                text_color="white",
                command=cmd(),
            )
            btn.grid(row=r, column=c, padx=8, pady=8, sticky="ew")

            c += 1
            if c > 1:
                c = 0
                r += 1

    def _render_selection_summary(self):
        if not self.details_when_label or not self.book_btn:
            return

        if self.selected_time and self.provider_name and self.selected_day:
            summary_text = (
                f"{self.provider_name}\n"
                f"{self.selected_day.strftime('%b %d, %Y')} at {self._format_time_label(self.selected_time)}"
            )
            self.details_when_label.configure(text=summary_text)
            self.book_btn.configure(state="normal")
        else:
            self.details_when_label.configure(text="Select a time slot...")
            self.book_btn.configure(state="disabled")

    def _render_bookings(self, bookings: List[Dict[str, Any]]):
        # wipe
        for w in self.bookings_list_frame.winfo_children():
            w.destroy()

        if not bookings:
            ctk.CTkLabel(
                self.bookings_list_frame,
                text="You have no bookings on this day.",
                font=("Segoe UI", 13),
                text_color="white",
                justify="left",
            ).grid(row=0, column=0, sticky="w", padx=12, pady=12)
            return

        for i, bk in enumerate(bookings):
            rowf = ctk.CTkFrame(
                self.bookings_list_frame,
                fg_color=CARD_BG,
                corner_radius=8,
            )
            rowf.grid(row=i, column=0, sticky="ew", padx=12, pady=8)
            rowf.grid_columnconfigure(0, weight=1)
            rowf.grid_columnconfigure(1, weight=0)

            # display "10:00 am • Dr Ali [requested]"
            line = (
                f"{self._format_time_label(bk.get('time',''))}  •  "
                f"{bk.get('provider_name','')}  "
                f"[{bk.get('status','')}]"
            )

            ctk.CTkLabel(
                rowf,
                text=line,
                font=("Segoe UI", 13),
                text_color="white",
                justify="left",
            ).grid(row=0, column=0, sticky="w", padx=8, pady=8)

            # Cancel button (enabled if it's your booking)
            def cancel_cmd(booking_id=bk.get("id", "")):
                return lambda: self._cancel_booking(booking_id)

            ctk.CTkButton(
                rowf,
                text="Cancel",
                width=70,
                corner_radius=6,
                fg_color="#2d2f36",
                hover_color="#444",
                text_color="white",
                command=cancel_cmd(),
            ).grid(row=0, column=1, sticky="e", padx=8, pady=8)

    # -------------------------------------------------
    # DATA FETCH
    # -------------------------------------------------
    def _fetch_available_slots_for_day(self) -> List[str]:
        """
        Ask FirestoreSchedule for this provider/day's open slots.
        Returns ["HH:MM", ...]
        """
        if not (self.app_ref and self.app_ref.schedule and self.provider_id):
            return []

        day_iso = self.selected_day.strftime("%Y-%m-%d")
        try:
            rows = self.app_ref.schedule.fetch_available_slots(day_iso, self.provider_id)
        except Exception as e:
            print("fetch_available_slots error:", e)
            rows = []
        return [r.get("time", "") for r in rows or []]

    def _fetch_my_bookings_for_day(self) -> List[Dict[str, Any]]:
        """
        Ask FirestoreSchedule for THIS PATIENT's bookings on this date.
        Returns list of {"id","time","provider_name","status"}
        """
        if not (self.app_ref and self.app_ref.schedule):
            return []
        patient_uid = self.user.get("uid", "")
        if not patient_uid:
            return []

        day_iso = self.selected_day.strftime("%Y-%m-%d")
        try:
            out = self.app_ref.schedule.fetch_patient_bookings(day_iso, patient_uid)
        except Exception as e:
            print("fetch_patient_bookings error:", e)
            out = []
        return out or []

    # -------------------------------------------------
    # ACTIONS
    # -------------------------------------------------
    def _select_time(self, t24: str):
        self.selected_time = t24
        self._render_selection_summary()

    def _confirm_booking(self):
        """
        Send booking request to Firestore.
        """
        if not (self.selected_time and self.provider_id and self.app_ref):
            messagebox.showinfo("Select time", "Please choose a time first.")
            return

        try:
            bid = self.app_ref.schedule.request_slot(
                day_iso=self.selected_day.strftime("%Y-%m-%d"),
                time_24=self.selected_time,
                patient_id=self.user.get("uid", ""),
                provider_id=self.provider_id,
                patient_name=self.user.get("name") or self.user.get("email") or "",
                provider_name=self.provider_name,
            )

            messagebox.showinfo(
                "Request sent",
                f"Requested {self._format_time_label(self.selected_time)} with {self.provider_name}\nRequest ID: {bid}",
            )

            # reset selected_time, reload bookings
            self.selected_time = None
            self._refresh_day_only()

        except Exception as e:
            messagebox.showerror("Error", f"Could not request session:\n{e}")

    def _cancel_booking(self, booking_id: str):
        """
        Cancel a booking / request for this patient if schedule.cancel_request(...) exists.
        """
        if not booking_id:
            return

        if not (self.app_ref and self.app_ref.schedule):
            messagebox.showerror("Error", "Schedule service unavailable.")
            return

        try:
            # call schedule.cancel_request just like AppController.cancel_booking()
            self.app_ref.schedule.cancel_request(
                booking_id,
                patient_id=self.user.get("uid", ""),
            )

            messagebox.showinfo("Cancelled", "Your booking was cancelled.")
            self._refresh_day_only()

        except Exception as e:
            messagebox.showerror("Error", f"Could not cancel booking:\n{e}")

    # -------------------------------------------------
    # SMALL HELPERS
    # -------------------------------------------------
    def _format_time_label(self, t24: str) -> str:
        """Turn '13:00' into '1:00 pm' for display."""
        try:
            hh_str, mm_str = t24.split(":")
            hh = int(hh_str)
            ampm = "am"
            if hh == 0:
                disp_h = 12
                ampm = "am"
            elif hh < 12:
                disp_h = hh
                ampm = "am"
            elif hh == 12:
                disp_h = 12
                ampm = "pm"
            else:
                disp_h = hh - 12
                ampm = "pm"
            return f"{disp_h}:{mm_str} {ampm}"
        except Exception:
            return t24
