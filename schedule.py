# PoseCare_app/services/schedule.py
from __future__ import annotations
from typing import Dict, List, Optional
import datetime as _dt
import requests

from services.firebase_client import FirebaseClient
from services.config import PROJECT_ID

FS_BASE = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"


def _date_only(iso_or_date: str) -> str:
    return (iso_or_date or "")[:10]


def _to_time(iso_dt: str) -> str:
    try:
        if "T" in iso_dt:
            return iso_dt.split("T", 1)[1][:5]
        return iso_dt[11:16]
    except Exception:
        return "--:--"


def _combine_iso(day_iso: str, time_24: str) -> str:
    # naive UTC-style string; your DB stores string timestamps
    return f"{day_iso}T{time_24}:00+00:00"


class FirestoreSchedule:
    """
    Thin wrapper around your FirebaseClient (REST).
    Uses collections:
      - provider_directory (doc.id = clinicianUid) fields: {name, email, role}
      - sessions (string fields):
            clinicianUid, clinicianName, startAt, endAt,
            patientAuthUid (optional), patientName (optional), status
      - feedback: createdAt, patientAuthUid, patientName, clinicianUid, clinicianName, text, by
    """

    def __init__(self, client: FirebaseClient):
        self.client = client  # REST client, already has api_key/project_id + id_token

    # ---------- Providers ----------
    def list_providers(self) -> List[Dict]:
        # Delegate to your client method which already normalizes from provider_directory/users
        return self.client.list_providers()

    # ---------- Availability ----------
    def fetch_available_slots(self, day_iso: str, provider_id: str) -> List[Dict]:
        """
        Available if clinicianUid=provider_id and date matches and (status=='open' OR no patientAuthUid).
        """
        rows = self.client._run_query(  # use client's query (it refreshes tokens)
            "sessions",
            where_filters=[("clinicianUid", "EQUAL", provider_id)],
            limit=400,
        )
        out: List[Dict] = []
        for s in rows:
            if _date_only(s.get("startAt", "")) != day_iso:
                continue
            status = (s.get("status") or "").lower()
            free_like = (status == "open") or (not s.get("patientAuthUid"))
            if not free_like:
                continue
            out.append({
                "id": s.get("_id", ""),
                "date": day_iso,
                "time": _to_time(s.get("startAt", "")),
                "provider_name": s.get("clinicianName", ""),
                "provider_id": s.get("clinicianUid", provider_id),
            })
        out.sort(key=lambda r: r["time"])
        return out

    # ---------- Bookings ----------
    def fetch_patient_bookings(self, day_iso: str, patient_id: str) -> List[Dict]:
        rows = self.client.list_sessions_for_user("Patient", patient_id, "", date_iso=day_iso)
        out = []
        for s in rows:
            out.append({
                "id": s.get("_id", ""),
                "date": day_iso,
                "time": _to_time(s.get("startAt", "")),
                "provider_name": s.get("clinicianName", ""),
                "status": (s.get("status") or "").lower(),
            })
        out.sort(key=lambda r: r["time"])
        return out

    def fetch_provider_bookings(self, day_iso: str, provider_id: str) -> List[Dict]:
        rows = self.client.list_sessions_for_user("Doctor", provider_id, "", date_iso=day_iso)
        out = []
        for s in rows:
            # bookings/requests = any session with a patient
            if not s.get("patientAuthUid"):
                continue
            out.append({
                "id": s.get("_id", ""),
                "date": day_iso,
                "time": _to_time(s.get("startAt", "")),
                "patient_name": s.get("patientName", "(patient)"),
                "status": (s.get("status") or "").lower(),
            })
        out.sort(key=lambda r: r["time"])
        return out

    # ---------- Mutations ----------
    def request_slot(self, day_iso: str, time_24: str, patient_id: str, provider_id: str,
                     patient_name: str = "", provider_name: str = "") -> str:
        """
        Claim an existing 'open' slot if present; otherwise create a new session at that time.
        """
        self.client._ensure_token()
        h = {"Authorization": f"Bearer {self.client.id_token}"}

        start_at = _combine_iso(day_iso, time_24)
        # Set a default 45-min end time
        end_dt = _dt.datetime.fromisoformat(start_at.replace("Z", "+00:00")).replace(tzinfo=None) + _dt.timedelta(minutes=45)
        end_at = end_dt.isoformat(timespec="seconds") + "+00:00"

        # try to find an existing 'open' slot
        rows = self.client._run_query("sessions", [("clinicianUid", "EQUAL", provider_id)], limit=200)
        target = None
        for s in rows:
            if s.get("startAt") == start_at and ((s.get("status", "").lower() == "open") or not s.get("patientAuthUid")):
                target = s
                break

        fields = {
            "clinicianUid": self.client._fv(provider_id),
            "clinicianName": self.client._fv(provider_name),
            "startAt": self.client._fv(start_at),
            "endAt": self.client._fv(end_at),
            "patientAuthUid": self.client._fv(patient_id),
            "patientName": self.client._fv(patient_name),
            "status": self.client._fv("request"),
            "createdAt": self.client._fv(_dt.datetime.utcnow().isoformat(timespec="seconds") + "+00:00"),
        }

        if target and target.get("_id"):
            # update existing
            url = f"{FS_BASE}/sessions/{target['_id']}"
            r = requests.patch(url, headers=h, json={"fields": fields})
            if r.status_code not in (200, 201):
                raise RuntimeError(f"Update slot failed: {r.text}")
            return target["_id"]
        else:
            # create new
            r = requests.post(f"{FS_BASE}/sessions", headers=h, json={"fields": fields})
            if r.status_code not in (200, 201):
                raise RuntimeError(f"Create session failed: {r.text}")
            doc = r.json().get("name", "")
            return doc.split("/")[-1] if doc else ""

    def cancel_request(self, booking_id: str, *, patient_id: Optional[str] = None,
                       provider_id: Optional[str] = None) -> None:
        # Use the client’s cancel helper
        self.client.cancel_session(booking_id)

    # ---------- Feedback ----------
    def add_feedback(self, *, patient_uid: str, clinician_uid: str, clinician_name: str,
                     text: str, patient_name: str = "", by: str = "patient") -> str:
        # feed goes into 'feedback' collection with your existing helper
        self.client.add_feedback(
            patient_uid=patient_uid,
            clinician_uid=clinician_uid,
            clinician_name=clinician_name,
            text=text,
            patient_name=patient_name,
            patient_auth_uid=patient_uid,
        )
        return "ok"

    @property
    def feedback(self) -> List[Dict]:
        # best-effort: pull last 100 rows via runQuery order is not guaranteed; dashboards sort by createdAt
        rows = self.client._run_query("feedback", None, 100)
        return rows or []
