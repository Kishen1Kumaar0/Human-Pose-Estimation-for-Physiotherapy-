# PoseCare_app/views/shared_store.py
from __future__ import annotations
import datetime as _dt
import random, string
from typing import Dict, List, Optional

class LocalStore:
    """In-memory demo store so the UI works without Firestore. Swap with your adapters later."""
    def __init__(self):
        self.providers = [
            {"uid": "prov_aaron", "name": "Dr. Aaron"},
            {"uid": "prov_bella", "name": "Dr. Bella"},
        ]
        self.feedback: List[Dict] = []      # simple feed of notes/feedback
        self.bookings: List[Dict] = []      # {'id','date','time','patient_id','provider_id','status','patient_name','provider_name'}
        self.availability: List[Dict] = []  # {'date','time','provider_id','provider_name','is_free':bool}
        self._seed_availability()

    def _seed_availability(self):
        today = _dt.date.today()
        for d in range(-1, 6):
            day = (today + _dt.timedelta(days=d)).strftime("%Y-%m-%d")
            for t in ("09:00", "10:30", "14:00", "15:30"):
                self.availability.append({"date": day, "time": t, "provider_id": "prov_aaron",
                                          "provider_name": "Dr. Aaron", "is_free": True})
            for t in ("11:00", "13:00", "16:30"):
                self.availability.append({"date": day, "time": t, "provider_id": "prov_bella",
                                          "provider_name": "Dr. Bella", "is_free": True})

    # ---------- “backend” surface (replace with Firestore later) ----------
    def list_providers(self) -> List[Dict]:
        return self.providers

    def add_feedback(self, *, patient_uid: str, clinician_uid: str, clinician_name: str,
                     text: str, patient_name: str = "", by: str = "patient") -> str:
        fid = "fb_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        self.feedback.append({
            "id": fid, "when": _dt.datetime.now().isoformat(timespec="seconds"),
            "patient_uid": patient_uid, "patient_name": patient_name,
            "clinician_uid": clinician_uid, "clinician_name": clinician_name,
            "text": text, "by": by
        })
        return fid

    def fetch_patient_bookings(self, day_iso: str, patient_id: str) -> List[Dict]:
        return sorted((b for b in self.bookings if b["date"] == day_iso and b["patient_id"] == patient_id),
                      key=lambda x: x["time"])

    def fetch_provider_bookings(self, day_iso: str, provider_id: str) -> List[Dict]:
        return sorted((b for b in self.bookings if b["date"] == day_iso and b["provider_id"] == provider_id),
                      key=lambda x: x["time"])

    def fetch_available_slots(self, day_iso: str, provider_id: str) -> List[Dict]:
        return sorted((s for s in self.availability
                       if s["date"] == day_iso and s["provider_id"] == provider_id and s["is_free"]),
                      key=lambda x: x["time"])

    def request_slot(self, day_iso: str, time_24: str, patient_id: str, provider_id: str,
                     patient_name: str = "", provider_name: str = "") -> str:
        for s in self.availability:
            if s["date"] == day_iso and s["time"] == time_24 and s["provider_id"] == provider_id and s["is_free"]:
                s["is_free"] = False
                provider_name = provider_name or s.get("provider_name", "")
                break
        bid = "bk_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        self.bookings.append({
            "id": bid, "date": day_iso, "time": time_24,
            "patient_id": patient_id, "patient_name": patient_name,
            "provider_id": provider_id, "provider_name": provider_name,
            "status": "requested"
        })
        return bid

    def cancel_request(self, booking_id: str, *, patient_id: Optional[str] = None,
                       provider_id: Optional[str] = None) -> None:
        bk = next((b for b in self.bookings if b["id"] == booking_id), None)
        if not bk: return
        if patient_id and bk["patient_id"] != patient_id: return
        if provider_id and bk["provider_id"] != provider_id: return
        bk["status"] = "cancelled"
        for s in self.availability:
            if s["date"] == bk["date"] and s["time"] == bk["time"] and s["provider_id"] == bk["provider_id"]:
                s["is_free"] = True
                break


# singleton demo store
STORE = LocalStore()


def get_user_ids(controller) -> Dict[str, str]:
    """Get IDs/names from controller with safe fallbacks."""
    return {
        "patient_id": getattr(controller, "current_user_id", "demo_patient"),
        "patient_name": getattr(controller, "current_user_name", "You"),
        "provider_id": getattr(controller, "current_provider_id", "prov_aaron"),
        "provider_name": getattr(controller, "current_provider_name", "Dr. Aaron"),
    }


def get_services(controller):
    """
    Return (schedule, feedback) services. If controller doesn't expose them,
    fall back to the demo STORE for both.
    """
    schedule = getattr(controller, "schedule", None) or STORE
    feedback = getattr(controller, "fb", None) or STORE
    return schedule, feedback
