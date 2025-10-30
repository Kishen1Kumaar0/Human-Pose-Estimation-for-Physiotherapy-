from __future__ import annotations
import calendar
import datetime as _dt
import customtkinter as ctk

class MonthGrid(ctk.CTkFrame):
    """
    Month grid with +/- month navigation and weekday header.
    Calls on_pick(date) when a day button is clicked.
    """
    def __init__(self, master, date: _dt.date, on_pick, **kw):
        super().__init__(master, **kw)
        self._date = date.replace(day=1)
        self._on_pick = on_pick

        head = ctk.CTkFrame(self); head.pack(fill="x", padx=6, pady=(6,2))
        self._title = ctk.CTkLabel(head, text=self._title_text(), font=("", 16, "bold"))
        self._title.pack(side="left", padx=6)

        ctk.CTkButton(head, text="−", width=36, command=lambda: self._shift(-1)).pack(side="right", padx=(4,6))
        ctk.CTkButton(head, text="+", width=36, command=lambda: self._shift(+1)).pack(side="right", padx=4)

        days_row = ctk.CTkFrame(self); days_row.pack(fill="x", padx=6, pady=(0,6))
        for d in ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]:
            ctk.CTkLabel(days_row, text=d, width=64, anchor="center").pack(side="left", padx=2)

        self._grid = ctk.CTkFrame(self); self._grid.pack(fill="x", padx=6, pady=(0,6))
        self._render_month()

    def _title_text(self) -> str:
        return self._date.strftime("%B %Y")

    def _shift(self, months: int):
        y, m = self._date.year, self._date.month + months
        while m < 1: y, m = y-1, m+12
        while m > 12: y, m = y+1, m-12
        self._date = self._date.replace(year=y, month=m, day=1)
        self._title.configure(text=self._title_text())
        self._render_month()

    # IMPORTANT: not named `_draw` (CTk uses that)
    def _render_month(self):
        for w in self._grid.winfo_children():
            w.destroy()

        cal = calendar.Calendar(firstweekday=0)
        row = ctk.CTkFrame(self._grid); row.pack(fill="x")
        idx = 0
        for date in cal.itermonthdates(self._date.year, self._date.month):
            if idx and idx % 7 == 0:
                row = ctk.CTkFrame(self._grid); row.pack(fill="x", pady=2)
            fg_color = ("#1e293b", "#1e293b") if date.month != self._date.month else None
            ctk.CTkButton(
                row, width=64, text=str(date.day),
                fg_color=fg_color, command=lambda d=date: self._on_pick(d)
            ).pack(side="left", padx=2)
            idx += 1
