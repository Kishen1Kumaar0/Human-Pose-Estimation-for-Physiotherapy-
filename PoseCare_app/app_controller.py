# PoseCare_app/app_controller.py
from __future__ import annotations
from typing import List, Dict, Optional
from datetime import date

import requests

from services.config import WEB_API_KEY, PROJECT_ID
from services.firebase_client import FirebaseClient
from services.schedule import FirestoreSchedule

def _to_iso(d: date) -> str:
    return d.strftime("%Y-%m-%d")

class AppController:
    """
    Adapter so dashboards can call a consistent API regardless of backend naming.
    Uses your FirebaseClient and FirestoreSchedule under the hood.
    """

    def __init__(self, current_user: Dict[str, str]):
        # Authenticated REST client + schedule helper
        # NOTE: We assume FirebaseClient is already signed in before we pass it here.
        self.fb = FirebaseClient(api_key=WEB_API_KEY, project_id=PROJECT_ID)
        # When we construct this, caller must immediately copy tokens into self.fb
        # (we’ll do that in app.py after sign-in).
        self.schedule = FirestoreSchedule(self.fb)

        # Current signed-in user data {uid, name, email, role}
        self.current_user = current_user or {}
        self.current_user_id: str = self.current_user.get("uid", "")
        self.current_user_name: str = self.current_user.get("name", "") or self.current_user.get("email", "")

    # ---------- Provider directory ----------
    def list_providers(self) -> List[Dict]:
        """
        Returns list like: [{"id": "...", "name": "Dr. A", "email": "..."}]
        Maps from FirebaseClient.list_providers() which returns {"uid","name","email","role"}.
        """
        rows = self.fb.list_providers()  # normalized & sorted by client
        out = []
        for r in rows or []:
            out.append({
                "id": r.get("uid") or r.get("_id") or r.get("id") or "",
                "name": r.get("name") or r.get("email") or "(unnamed)",
                "email": r.get("email", "")
            })
        return out

    # ---------- Patient-side calendar ----------
    def get_availability(self, provider_id: str, d: date) -> List[str]:
        """
        Returns a list of "HH:MM" strings from FirestoreSchedule.fetch_available_slots(...)
        """
        day_iso = _to_iso(d)
        slots = self.schedule.fetch_available_slots(day_iso, provider_id)
        return [s.get("time", "") for s in slots]

    def get_my_bookings(self, d: date) -> List[Dict]:
        """
        Returns list of dicts: {"id","time","provider_name","status"}
        Uses FirestoreSchedule.fetch_patient_bookings(...)
        """
        day_iso = _to_iso(d)
        rows = self.schedule.fetch_patient_bookings(day_iso, self.current_user_id)
        # Already mapped by schedule to id/time/provider_name/status
        return rows

    def create_booking(self, provider_id: str, d: date, time_24: str) -> str:
        """
        Creates or claims an 'open' slot at given time. Returns booking/session id.
        """
        # find provider name for nice UI
        pname = ""
        for r in self.list_providers():
            if r["id"] == provider_id:
                pname = r["name"]
                break
        bid = self.schedule.request_slot(
            day_iso=_to_iso(d),
            time_24=time_24,
            patient_id=self.current_user_id,
            provider_id=provider_id,
            patient_name=self.current_user_name,
            provider_name=pname,
        )
        return bid

    def cancel_booking(self, booking_id: str) -> None:
        self.schedule.cancel_request(booking_id, patient_id=self.current_user_id)

    def send_message_to_provider(self, provider_id: str, message: str) -> None:
        """
        Your client does not have a strict 'messages' collection; we will store this as feedback addressed to clinician.
        """
        pname = ""
        for r in self.list_providers():
            if r["id"] == provider_id:
                pname = r["name"]
                break
        # Map to your feedback helper (author is current user)
        self.fb.add_feedback(
            patient_uid=self.current_user_id,
            clinician_uid=provider_id,
            clinician_name=pname,
            text=message,
            patient_name=self.current_user_name,
            patient_auth_uid=self.current_user_id,
        )

    # ---------- Provider-side calendar ----------
    def get_day_requests(self, d: date) -> List[Dict]:
        """
        Provider's incoming requests for that day.
        We reuse fetch_provider_bookings (sessions with patient bound), and treat any with 'request' as incoming.
        """
        day_iso = _to_iso(d)
        rows = self.schedule.fetch_provider_bookings(day_iso, self.current_user_id)
        # shape: {"id","date","time","patient_name","status"}
        return rows

    def accept_request(self, booking_id: str) -> None:
        """
        Set session.status = 'scheduled'.
        There is no explicit method in your services for 'accept', so we patch via REST using FirebaseClient creds.
        """
        self.fb._ensure_token()
        h = {"Authorization": f"Bearer {self.fb.id_token}"}
        # Load; then patch status
        url = self.fb._doc_url(f"sessions/{booking_id}")
        r = requests.get(url, headers=h)
        if r.status_code != 200:
            raise RuntimeError(f"Load session failed: {r.text}")
        fields = r.json().get("fields", {})
        fields["status"] = self.fb._fv("scheduled")
        r2 = requests.patch(url, headers=h, json={"fields": fields})
        if r2.status_code not in (200, 201):
            raise RuntimeError(f"Accept failed: {r2.text}")

    def reject_request(self, booking_id: str) -> None:
        """
        Set session.status = 'rejected' (or you can use 'cancelled' if you prefer).
        """
        self.fb._ensure_token()
        h = {"Authorization": f"Bearer {self.fb.id_token}"}
        url = self.fb._doc_url(f"sessions/{booking_id}")
        r = requests.get(url, headers=h)
        if r.status_code != 200:
            raise RuntimeError(f"Load session failed: {r.text}")
        fields = r.json().get("fields", {})
        fields["status"] = self.fb._fv("rejected")
        r2 = requests.patch(url, headers=h, json={"fields": fields})
        if r2.status_code not in (200, 201):
            raise RuntimeError(f"Reject failed: {r2.text}")

    def set_availability(self, d: date, slots: List[str]) -> None:
        """
        Provider creates 'open' slots for the chosen day and times if they don't exist.
        We'll create sessions with status='open' (patientAuthUid left empty).
        """
        self.fb._ensure_token()
        h = {"Authorization": f"Bearer {self.fb.id_token}"}
        day_iso = _to_iso(d)

        # Fetch existing sessions for that day/provider so we don't duplicate
        existing = self.fb._run_query("sessions", [("clinicianUid", "EQUAL", self.current_user_id)], limit=400)
        existing_times = { (s.get("startAt") or "")[11:16] for s in existing if (s.get("startAt") or "")[:10] == day_iso }

        for t in slots:
            t = t.strip()
            if not t or t in existing_times:
                continue
            start_at = f"{day_iso}T{t}:00+00:00"
            # 45-min default end time not critical for marking availability; a simple same-time end is fine
            payload = {
                "fields": {
                    "startAt": self.fb._fv(start_at),
                    "endAt": self.fb._fv(start_at),
                    "clinicianUid": self.fb._fv(self.current_user_id),
                    "clinicianName": self.fb._fv(self.current_user_name),
                    "status": self.fb._fv("open"),
                    "createdByUid": self.fb._fv(self.current_user_id),
                    "createdAt": self.fb._fv(self.fb.iso_now() if hasattr(self.fb, "iso_now") else ""),
                }
            }
            r = requests.post(self.fb._doc_url("sessions"), headers=h, json=payload)
            if r.status_code not in (200, 201):
                raise RuntimeError(f"Set availability failed: {r.text}")
