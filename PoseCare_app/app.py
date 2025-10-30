from __future__ import annotations

import customtkinter as ctk
from tkinter import messagebox
from typing import Dict, Optional

# theme
from services.ui_theme import apply_ctk_theme, TOP_BG

# backend services
from services.firebase_client import FirebaseClient
from services.schedule import FirestoreSchedule
from services.config import WEB_API_KEY, PROJECT_ID

# views
from views.auth import AuthView
from views.dashboard_patient import PatientDashboard
from views.dashboard_provider import ProviderDashboard
from views.dashboard_coach import CoachDashboard
from views.upload_video import UploadVideoPage
# CalendarPanel is imported by dashboards themselves when needed

class PoseCareApp(ctk.CTk):
    """
    Root window / controller.
    Holds Firebase client, logged-in user, dashboards, and nav helpers.
    """

    def __init__(self):
        super().__init__()

        # --- theme / window ---
        apply_ctk_theme(self)
        self.title("PoseCare • Rehab Coach")
        self.geometry("1100x700")
        self.configure(fg_color=TOP_BG)

        # --- backend clients ---
        self.fb = FirebaseClient(api_key=WEB_API_KEY, project_id=PROJECT_ID)
        self.schedule = FirestoreSchedule(self.fb)

        # --- session state ---
        self.user: Dict[str, str] = {}
        self.current_role: str = ""
        self.current_provider_id: Optional[str] = None
        self.current_provider_name: str = ""

        # --- master container ---
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(side="top", fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.views: Dict[str, ctk.CTkFrame] = {}

        # --- static pages ---
        auth = AuthView(self.container, self)
        self.views["AuthView"] = auth
        auth.grid(row=0, column=0, sticky="nsew")

        upload = UploadVideoPage(self.container, self)
        self.views["UploadVideoPage"] = upload
        upload.grid(row=0, column=0, sticky="nsew")

        # dashboards are created lazily after login

        self.show("AuthView")

    # -------------------------------------------------
    # generic navigation
    # -------------------------------------------------
    def show(self, name: str):
        view = self.views.get(name)
        if view is None:
            print(f"[WARN] Tried to show unknown view '{name}'")
            return
        view.tkraise()

    def logout(self):
        """
        Clear auth state and send user back to login.
        """
        self.user = {}
        self.current_role = ""
        self.current_provider_id = None
        self.current_provider_name = ""

        # fresh Firebase client so tokens reset
        self.fb = FirebaseClient(api_key=WEB_API_KEY, project_id=PROJECT_ID)
        self.schedule = FirestoreSchedule(self.fb)

        self.show("AuthView")

    # -------------------------------------------------
    # video-area navigation (patients upload vs providers review)
    # -------------------------------------------------
    def open_video_area(self):
        """
        Called by the top nav "Upload Video" button (DashboardBase).
        - Patient -> open UploadVideoPage
        - Provider/Coach -> open ReviewVideosPanel inside their dashboard body
        """
        role_low = (self.current_role or "").lower()
        if role_low.startswith("patient"):
            self.show("UploadVideoPage")
            return

        # provider / coach / doctor / etc. see review panel
        self.show_review_videos()

    def show_review_videos(self):
        """
        Build and display ReviewVideosPanel in the provider/coach dashboard body.
        """
        role_low = (self.current_role or "").lower()

        # which dashboard is active for this role?
        dash_key = None
        if "patient" in role_low:
            dash_key = "PatientDashboard"
        elif (
            "provider" in role_low
            or "physio" in role_low
            or "doctor" in role_low
        ):
            dash_key = "ProviderDashboard"
        elif "coach" in role_low:
            dash_key = "CoachDashboard"
        else:
            dash_key = "PatientDashboard"

        dash = self.views.get(dash_key)
        if dash is None:
            # if somehow dashboard not created yet, create it now
            self.show_dashboard(self.user)
            dash = self.views.get(dash_key)

        if dash is None or not hasattr(dash, "clear_body"):
            messagebox.showerror(
                "Error",
                "Dashboard not ready for video review."
            )
            return

        # clear dashboard body
        dash.clear_body()

        # lazily import here to avoid circular import
        from views.review_videos import ReviewVideosPanel

        panel = ReviewVideosPanel(
            dash.body,
            app_ref=self,
            clinician_user=self.user,
        )
        panel.pack(fill="both", expand=True)

        # make sure correct dashboard frame is raised
        self.show(dash_key)

    # -------------------------------------------------
    # auth flow
    # -------------------------------------------------
    def on_auth_success(self, user_info: Dict[str, str]):
        """
        Called by AuthView after sign-in/up.
        user_info: {"uid","name","email","role"}
        """
        self.user = user_info or {}
        self.current_role = (self.user.get("role") or "").strip()

        # Re-init schedule helper with authenticated fb
        self.schedule = FirestoreSchedule(self.fb)

        # For patients, guess a default provider to route uploads to
        if self.current_role.lower().startswith("patient"):
            providers = self.fb.list_providers() or []
            if providers:
                self.current_provider_id = providers[0].get("uid", "")
                self.current_provider_name = (
                    providers[0].get("name", "")
                    or providers[0].get("email", "")
                )

        self.show_dashboard(self.user)

    def show_dashboard(self, user: Optional[Dict[str, str]] = None):
        """
        Pick dashboard type by role, create it if missing,
        refresh it with latest user info, and raise it.
        """
        if user is None:
            user = self.user

        if not user:
            self.show("AuthView")
            return

        role = (user.get("role") or "").strip()
        # map role -> dashboard key
        if "patient" in role.lower():
            page_key = "PatientDashboard"
            if page_key not in self.views:
                dash = PatientDashboard(self.container, self)
                self.views[page_key] = dash
                dash.grid(row=0, column=0, sticky="nsew")
                if hasattr(dash, "set_controller"):
                    dash.set_controller(self)

        elif (
            "provider" in role.lower()
            or "physio" in role.lower()
            or "doctor" in role.lower()
        ):
            page_key = "ProviderDashboard"
            if page_key not in self.views:
                dash = ProviderDashboard(self.container, self)
                self.views[page_key] = dash
                dash.grid(row=0, column=0, sticky="nsew")
                if hasattr(dash, "set_controller"):
                    dash.set_controller(self)

        elif "coach" in role.lower():
            page_key = "CoachDashboard"
            if page_key not in self.views:
                dash = CoachDashboard(self.container, self)
                self.views[page_key] = dash
                dash.grid(row=0, column=0, sticky="nsew")
                if hasattr(dash, "set_controller"):
                    dash.set_controller(self)

        else:
            # fallback treat as patient
            page_key = "PatientDashboard"
            if page_key not in self.views:
                dash = PatientDashboard(self.container, self)
                self.views[page_key] = dash
                dash.grid(row=0, column=0, sticky="nsew")
                if hasattr(dash, "set_controller"):
                    dash.set_controller(self)

        dash_view = self.views[page_key]
        if hasattr(dash_view, "user"):
            dash_view.user = user
        if hasattr(dash_view, "load_user"):
            dash_view.load_user(user)

        self.show(page_key)


if __name__ == "__main__":
    app = PoseCareApp()
    app.mainloop()
