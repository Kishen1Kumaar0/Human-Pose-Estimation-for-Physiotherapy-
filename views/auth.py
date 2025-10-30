# views/auth.py
from __future__ import annotations
import customtkinter as ctk
from tkinter import messagebox
from typing import Optional

from services.ui_theme import TOP_BG, CARD_BG, FIELD_BG
from services.firebase_client import FirebaseClient
from services.config import WEB_API_KEY, PROJECT_ID


class AuthView(ctk.CTkFrame):
    """
    Centered auth card:
    - Login form
    - Small link to "Create account"
    - Create account form with role selector (Patient / Doctor / Coach)
    After successful auth it calls controller.on_auth_success(...)
    """

    def __init__(self, parent, controller):
        super().__init__(parent, fg_color=TOP_BG)
        self.c = controller

        # we keep our own fb client but controller.fb will be updated with it
        self.fb = controller.fb

        self.mode = "login"  # or "create"

        # outer container in the middle
        outer = ctk.CTkFrame(
            self,
            fg_color="transparent",
        )
        outer.pack(expand=True)

        self.card = ctk.CTkFrame(
            outer,
            fg_color=CARD_BG,
            corner_radius=10,
        )
        self.card.pack(padx=24, pady=24, ipadx=24, ipady=24)

        # build both panels but show only one at a time
        self.login_panel = ctk.CTkFrame(self.card, fg_color="transparent")
        self.create_panel = ctk.CTkFrame(self.card, fg_color="transparent")

        self._build_login_panel()
        self._build_create_panel()

        self._show_login()

        # footer "Powered by..."
        self.footer = ctk.CTkLabel(
            self,
            text="•  Powered by Sen Gideons",
            text_color="#6b7280",
            font=("Segoe UI", 11),
        )
        self.footer.pack(side="bottom", anchor="se", padx=16, pady=8)

    # ------------------------- panel builders -------------------------

    def _build_login_panel(self):
        header = ctk.CTkLabel(
            self.login_panel,
            text="Welcome back",
            font=("Segoe UI", 20, "bold"),
            text_color="white",
        )
        header.pack(anchor="w")

        subrow = ctk.CTkFrame(self.login_panel, fg_color="transparent")
        subrow.pack(anchor="w", pady=(4, 12))
        ctk.CTkLabel(
            subrow,
            text="New here?",
            font=("Segoe UI", 12),
            text_color="gray80",
        ).pack(side="left")
        create_link = ctk.CTkButton(
            subrow,
            text="Create account",
            fg_color="transparent",
            text_color="#3b82f6",
            hover_color="#1e40af",
            width=1,
            command=self._show_create,
        )
        create_link.pack(side="left", padx=(4, 0))

        self.login_email = ctk.CTkEntry(
            self.login_panel,
            placeholder_text="Email account",
            fg_color=FIELD_BG,
            border_width=0,
            text_color="white",
            width=260,
        )
        self.login_email.pack(anchor="w", pady=(0, 8))

        self.login_pw = ctk.CTkEntry(
            self.login_panel,
            placeholder_text="Password",
            fg_color=FIELD_BG,
            border_width=0,
            text_color="white",
            width=260,
            show="*",
        )
        self.login_pw.pack(anchor="w", pady=(0, 16))

        btn = ctk.CTkButton(
            self.login_panel,
            text="Login",
            width=260,
            fg_color="#1f5eff",
            hover_color="#1a4ed6",
            command=self._do_submit_login,
        )
        btn.pack(anchor="w", pady=(0, 8))

    def _build_create_panel(self):
        header = ctk.CTkLabel(
            self.create_panel,
            text="Create new account",
            font=("Segoe UI", 20, "bold"),
            text_color="white",
        )
        header.pack(anchor="w")

        subrow = ctk.CTkFrame(self.create_panel, fg_color="transparent")
        subrow.pack(anchor="w", pady=(4, 12))
        ctk.CTkLabel(
            subrow,
            text="Already a member?",
            font=("Segoe UI", 12),
            text_color="gray80",
        ).pack(side="left")
        login_link = ctk.CTkButton(
            subrow,
            text="Login",
            fg_color="transparent",
            text_color="#3b82f6",
            hover_color="#1e40af",
            width=1,
            command=self._show_login,
        )
        login_link.pack(side="left", padx=(4, 0))

        row_names = ctk.CTkFrame(self.create_panel, fg_color="transparent")
        row_names.pack(anchor="w")
        self.first_name = ctk.CTkEntry(
            row_names,
            placeholder_text="First name",
            fg_color=FIELD_BG,
            border_width=0,
            text_color="white",
            width=160,
        )
        self.first_name.pack(side="left", pady=(0, 8), padx=(0, 8))

        self.last_name = ctk.CTkEntry(
            row_names,
            placeholder_text="Last name",
            fg_color=FIELD_BG,
            border_width=0,
            text_color="white",
            width=160,
        )
        self.last_name.pack(side="left", pady=(0, 8))

        self.create_email = ctk.CTkEntry(
            self.create_panel,
            placeholder_text="Email account",
            fg_color=FIELD_BG,
            border_width=0,
            text_color="white",
            width=332,
        )
        self.create_email.pack(anchor="w", pady=(0, 8))

        row_pw = ctk.CTkFrame(self.create_panel, fg_color="transparent")
        row_pw.pack(anchor="w")

        self.create_pw = ctk.CTkEntry(
            row_pw,
            placeholder_text="Password",
            fg_color=FIELD_BG,
            border_width=0,
            text_color="white",
            show="*",
            width=160,
        )
        self.create_pw.pack(side="left", pady=(0, 8), padx=(0, 8))

        self.create_pw2 = ctk.CTkEntry(
            row_pw,
            placeholder_text="Confirm Password",
            fg_color=FIELD_BG,
            border_width=0,
            text_color="white",
            show="*",
            width=160,
        )
        self.create_pw2.pack(side="left", pady=(0, 8))

        # --- Role selector (Patient / Doctor / Coach)
        self.role_label = ctk.CTkLabel(
            self.create_panel,
            text="Account type",
            text_color="white",
            font=("Segoe UI", 13, "bold"),
        )
        self.role_label.pack(anchor="w", pady=(8, 4))

        self.var_role = ctk.StringVar(value="Patient")
        self.role_segment = ctk.CTkSegmentedButton(
            self.create_panel,
            values=["Patient", "Doctor", "Coach"],
            variable=self.var_role,
            fg_color=FIELD_BG,
            selected_color="#1f5eff",
            selected_hover_color="#1a4ed6",
            unselected_color=FIELD_BG,
            unselected_hover_color="#2d2f36",
            text_color="white",
            corner_radius=8,
        )
        self.role_segment.pack(anchor="w", pady=(0, 12))

        btn = ctk.CTkButton(
            self.create_panel,
            text="Submit",
            width=332,
            fg_color="#1f5eff",
            hover_color="#1a4ed6",
            command=self._do_submit_create,
        )
        btn.pack(anchor="w", pady=(0, 8))

    # ------------------------- mode switching -------------------------

    def _show_login(self):
        self.mode = "login"
        self.create_panel.pack_forget()
        self.login_panel.pack(anchor="w")

    def _show_create(self):
        self.mode = "create"
        self.login_panel.pack_forget()
        self.create_panel.pack(anchor="w")

    # ------------------------- submit handlers -------------------------

    def _do_submit_login(self):
        email = self.login_email.get().strip()
        pw = self.login_pw.get().strip()
        if not email or not pw:
            messagebox.showwarning("Login", "Please enter email and password.")
            return

        try:
            info = self.fb.sign_in(email, pw)
        except Exception as e:
            messagebox.showerror("Login failed", str(e))
            return

        # hand off session to controller
        self.c.fb = self.fb
        self.c.user = info
        messagebox.showinfo("Login", f"Logged in as {info.get('email','')}")
        self.c.on_auth_success(info)

    def _do_submit_create(self):
        first = self.first_name.get().strip()
        last = self.last_name.get().strip()
        email = self.create_email.get().strip()
        pw1 = self.create_pw.get().strip()
        pw2 = self.create_pw2.get().strip()
        role = self.var_role.get().strip()  # "Patient" | "Doctor" | "Coach"

        if not first:
            messagebox.showwarning("Create account", "First name required.")
            return
        if not email or not pw1:
            messagebox.showwarning("Create account", "Email and password required.")
            return
        if pw1 != pw2:
            messagebox.showwarning("Create account", "Passwords do not match.")
            return

        display_name = f"{first} {last}".strip()

        try:
            info = self.fb.sign_up(email, pw1, display_name, role)
        except Exception as e:
            messagebox.showerror("Create account failed", str(e))
            return

        # after sign-up, we are logged in already (fb tokens are set)
        self.c.fb = self.fb
        self.c.user = info

        messagebox.showinfo(
            "Account created",
            f"Account created for {display_name} ({role}).",
        )
        self.c.on_auth_success(info)
