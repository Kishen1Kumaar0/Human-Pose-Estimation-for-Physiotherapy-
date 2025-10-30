from __future__ import annotations
import time
import requests
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from .config import PROJECT_ID, WEB_API_KEY

ITK = "https://identitytoolkit.googleapis.com/v1"
SECURETOKEN = "https://securetoken.googleapis.com/v1"
FS_BASE = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents"


# ---------- ISO / date helpers ----------
def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def date_only(iso_str: str) -> str:
    return (iso_str or "")[:10]


def parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


class FirebaseError(RuntimeError):
    pass


class FirebaseClient:
    """
    Firebase REST client for Auth + Firestore.
    Handles:
    - accounts (sign up / sign in)
    - users
    - provider_directory
    - patients
    - feedback
    - sessions (availability / bookings)
    - exercise_logs (metrics)
    - NEW: exerciseVideos (patient-submitted exercise videos)
    """

    def __init__(self, api_key: str, project_id: str):
        self.api_key = api_key
        self.project_id = project_id
        self.id_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.uid: Optional[str] = None
        self.exp: int = 0

    # ---------- helpers ----------
    @staticmethod
    def _is_provider_role(role: str) -> bool:
        """
        We consider these "provider" roles for scheduling / messaging.
        """
        r = (role or "").strip().lower()
        return (
            r.startswith("physiotherapist")
            or r.startswith("doctor")
            or r.startswith("provider")
            or r.startswith("coach")
        )

    # ---------- Auth ----------
    def sign_up(self, email: str, password: str, display_name: str, role: str):
        r = requests.post(
            f"{ITK}/accounts:signUp?key={self.api_key}",
            json={"email": email, "password": password, "returnSecureToken": True},
        )
        if r.status_code != 200:
            raise FirebaseError(f"SignUp failed: {r.text}")
        data = r.json()

        self._save_tokens(data)
        self.uid = data["localId"]

        # set displayName
        requests.post(
            f"{ITK}/accounts:update?key={self.api_key}",
            json={
                "idToken": self.id_token,
                "displayName": display_name,
                "returnSecureToken": True,
            },
        )

        # create Firestore profile /users/{uid}
        self._ensure_token()
        self._patch_doc(
            f"users/{self.uid}",
            {
                "name": display_name,
                "email": email,
                "role": role,
                "createdAt": iso_now(),
            },
        )

        # keep provider_directory in sync if clinician
        self._ensure_provider_directory(self.uid, display_name, email, role)

        return {
            "uid": self.uid,
            "name": display_name,
            "email": email,
            "role": role,
        }

    def sign_in(self, email: str, password: str):
        r = requests.post(
            f"{ITK}/accounts:signInWithPassword?key={self.api_key}",
            json={"email": email, "password": password, "returnSecureToken": True},
        )
        if r.status_code != 200:
            raise FirebaseError(f"SignIn failed: {r.text}")
        data = r.json()

        self._save_tokens(data)
        self.uid = data["localId"]

        self._ensure_token()
        prof = self._get_doc(f"users/{self.uid}") or {}
        if not prof:
            # first login ever -> default Patient profile
            name = email.split("@")[0].title()
            self._patch_doc(
                f"users/{self.uid}",
                {
                    "name": name,
                    "email": email,
                    "role": "Patient",
                    "createdAt": iso_now(),
                },
            )
            prof = {"name": name, "email": email, "role": "Patient"}

        # sync provider_directory if needed
        self._ensure_provider_directory(
            self.uid,
            prof.get("name", ""),
            email,
            prof.get("role", ""),
        )

        return {
            "uid": self.uid,
            "name": prof.get("name", ""),
            "email": email,
            "role": prof.get("role", "Patient"),
        }

    def _save_tokens(self, j: Dict[str, Any]):
        self.id_token = j["idToken"]
        self.refresh_token = j["refreshToken"]
        self.exp = int(time.time()) + int(j.get("expiresIn", "3600")) - 60

    def _ensure_token(self):
        """
        Refresh id_token if it's expired.
        """
        if not self.id_token or time.time() >= self.exp:
            r = requests.post(
                f"{SECURETOKEN}/token?key={self.api_key}",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                },
            )
            if r.status_code != 200:
                raise FirebaseError(f"Refresh token failed: {r.text}")
            j = r.json()
            self.id_token = j["id_token"]
            self.refresh_token = j["refresh_token"]
            self.exp = int(time.time()) + int(j.get("expires_in", "3600")) - 60

    # ---------- Firestore helpers ----------
    def _fv(self, v: Any) -> Dict[str, Any]:
        """
        Convert python -> Firestore REST "fields" JSON.
        """
        if v is None:
            return {"nullValue": None}
        if isinstance(v, bool):
            return {"booleanValue": v}
        if isinstance(v, int):
            return {"integerValue": str(v)}
        if isinstance(v, float):
            return {"doubleValue": v}
        if isinstance(v, str):
            return {"stringValue": v}
        if isinstance(v, dict):
            return {"mapValue": {"fields": {k: self._fv(v[k]) for k in v}}}
        if isinstance(v, list):
            return {"arrayValue": {"values": [self._fv(x) for x in v]}}
        return {"stringValue": str(v)}

    def _from_fields(self, fields: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert Firestore REST "fields" JSON -> python.
        """
        def pv(x: Dict[str, Any]):
            if "stringValue" in x:
                return x["stringValue"]
            if "integerValue" in x:
                return int(x["integerValue"])
            if "doubleValue" in x:
                return float(x["doubleValue"])
            if "booleanValue" in x:
                return bool(x["booleanValue"])
            if "nullValue" in x:
                return None
            if "arrayValue" in x:
                arr = x["arrayValue"].get("values", [])
                return [pv(v) for v in arr]
            if "mapValue" in x:
                return {
                    k: pv(x["mapValue"]["fields"][k])
                    for k in x["mapValue"].get("fields", {})
                }
            return None

        return {k: pv(fields[k]) for k in (fields or {})}

    def _doc_url(self, path: str) -> str:
        return f"{FS_BASE}/{path}"

    def _patch_doc(self, path: str, data: Dict[str, Any]):
        self._ensure_token()
        h = {"Authorization": f"Bearer {self.id_token}"}
        r = requests.patch(
            self._doc_url(path),
            headers=h,
            json={"fields": {k: self._fv(v) for k, v in data.items()}},
        )
        if r.status_code not in (200, 201):
            raise FirebaseError(f"Set doc failed: {r.text}")

    def _get_doc(self, path: str) -> Optional[Dict[str, Any]]:
        self._ensure_token()
        h = {"Authorization": f"Bearer {self.id_token}"}
        r = requests.get(self._doc_url(path), headers=h)
        if r.status_code == 200:
            return self._from_fields(r.json().get("fields", {}))
        if r.status_code == 404:
            return None
        raise FirebaseError(f"Get doc failed: {r.text}")

    def _run_query(
        self,
        collection: str,
        where_filters: List[tuple[str, str, str]] | None = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """
        Run a Firestore structuredQuery against a collection (EQUAL filters only),
        like you already use for sessions, feedback, etc.
        """
        self._ensure_token()
        h = {"Authorization": f"Bearer {self.id_token}"}

        filters = None
        if where_filters:
            for fp, op, val in where_filters:
                f = {
                    "fieldFilter": {
                        "field": {"fieldPath": fp},
                        "op": op,
                        "value": {"stringValue": val},
                    }
                }
                if filters is None:
                    filters = f
                else:
                    filters = {
                        "compositeFilter": {"op": "AND", "filters": [filters, f]}
                    }

        body = {
            "structuredQuery": {
                "from": [{"collectionId": collection}],
                "limit": limit
            }
        }
        if filters is not None:
            body["structuredQuery"]["where"] = filters

        r = requests.post(f"{FS_BASE}:runQuery", headers=h, json=body)
        if r.status_code != 200:
            raise FirebaseError(f"Query {collection} failed: {r.text}")

        out: List[Dict[str, Any]] = []
        for row in r.json():
            doc = row.get("document")
            if not doc:
                continue
            f = self._from_fields(doc.get("fields", {}))
            f["_id"] = doc["name"].split("/")[-1]
            out.append(f)
        return out

    # ---------- Provider directory ----------
    def _ensure_provider_directory(self, uid: str, name: str, email: str, role: str):
        try:
            if self._is_provider_role(role):
                self._patch_doc(
                    f"provider_directory/{uid}",
                    {
                        "name": name or "",
                        "email": email or "",
                        "role": role or "",
                        "updatedAt": iso_now(),
                    },
                )
        except Exception:
            pass

    def list_providers(self) -> List[Dict[str, Any]]:
        """
        Returns [{uid,name,email,role}, ...] sorted by name.
        """
        self._ensure_token()

        def normalize(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            out, seen = [], set()
            for u in rows:
                _id = u.get("_id")
                if not _id or _id in seen:
                    continue
                seen.add(_id)
                out.append(
                    {
                        "uid": _id,
                        "name": u.get("name", ""),
                        "email": u.get("email", ""),
                        "role": u.get("role", ""),
                    }
                )
            out.sort(key=lambda x: (x.get("name") or "").lower())
            return out

        # try provider_directory first
        try:
            rows = self._run_query("provider_directory", None, 1000)
            rows = [r for r in rows if self._is_provider_role(r.get("role", ""))]
            if rows:
                return normalize(rows)
        except Exception:
            pass

        # fallback: scan users for clinician-looking roles
        phys = []
        docs = []
        everyone = []
        try:
            phys = self._run_query(
                "users", [("role", "EQUAL", "Physiotherapist")], 500
            )
        except Exception:
            pass
        try:
            docs = self._run_query("users", [("role", "EQUAL", "Doctor")], 500)
        except Exception:
            pass

        rows = phys + docs
        if not rows:
            try:
                everyone = self._run_query("users", None, 1000)
            except Exception:
                pass
            rows = [u for u in everyone if self._is_provider_role(u.get("role", ""))]

        return normalize(rows)

    # ---------- Patients ----------
    def add_patient(
        self,
        owner_uid: str,
        name: str,
        dob: str,
        notes: str,
        patient_auth_uid: Optional[str] = None,
    ):
        self._ensure_token()
        h = {"Authorization": f"Bearer {self.id_token}"}

        fields = {
            "ownerUid": self._fv(owner_uid),
            "name": self._fv(name),
            "dob": self._fv(dob),
            "notes": self._fv(notes),
            "createdAt": self._fv(iso_now()),
        }
        if patient_auth_uid:
            fields["patientAuthUid"] = self._fv(patient_auth_uid)

        payload = {"fields": fields}
        r = requests.post(f"{FS_BASE}/patients", headers=h, json=payload)
        if r.status_code not in (200, 201):
            raise FirebaseError(f"Add patient failed: {r.text}")
        return True

    def _ensure_patient_link(
        self,
        owner_uid: str,
        patient_auth_uid: str,
        patient_name: str,
        patient_email: str,
    ):
        """
        Make sure provider sees a patient in 'patients' after contact.
        """
        if not owner_uid or not patient_auth_uid:
            return
        try:
            rows = self._run_query(
                "patients",
                where_filters=[
                    ("ownerUid", "EQUAL", owner_uid),
                    ("patientAuthUid", "EQUAL", patient_auth_uid),
                ],
                limit=1,
            )
            if rows:
                return

            self.add_patient(
                owner_uid,
                patient_name or patient_email or "Patient",
                dob="",
                notes="(auto-link)",
                patient_auth_uid=patient_auth_uid,
            )
        except Exception:
            pass

    def list_patients(self, owner_uid: str) -> List[Dict[str, Any]]:
        rows = []
        try:
            rows = self._run_query(
                "patients",
                where_filters=[("ownerUid", "EQUAL", owner_uid)],
                limit=500,
            )
        except Exception:
            rows = []

        # also infer from sessions
        try:
            sess = self._run_query(
                "sessions",
                where_filters=[("clinicianUid", "EQUAL", owner_uid)],
                limit=500,
            )
        except Exception:
            sess = []

        by_auth = {
            r.get("patientAuthUid", ""): r
            for r in rows
            if r.get("patientAuthUid")
        }

        for s in sess:
            pau = s.get("patientAuthUid", "")
            if pau and pau not in by_auth:
                by_auth[pau] = {
                    "_id": "",
                    "ownerUid": owner_uid,
                    "patientAuthUid": pau,
                    "name": s.get("patientName", "") or "(patient)",
                    "dob": "",
                    "notes": "(from sessions)",
                }

        merged = list(by_auth.values())
        merged.sort(key=lambda x: (x.get("name") or "").lower())
        return merged

    # ---------- Feedback ----------
    def add_feedback(
        self,
        patient_uid: str,
        clinician_uid: str,
        clinician_name: str,
        text: str,
        patient_email: str = "",
        patient_name: str = "",
        patient_auth_uid: str = "",
    ):
        self._ensure_token()
        h = {"Authorization": f"Bearer {self.id_token}"}

        payload = {
            "fields": {
                "patientUid": self._fv(patient_uid),
                "patientEmail": self._fv(patient_email),
                "patientName": self._fv(patient_name),
                "patientAuthUid": self._fv(patient_auth_uid),
                "clinicianUid": self._fv(clinician_uid),
                "clinicianName": self._fv(clinician_name),
                "text": self._fv(text),
                "authorUid": self._fv(self.uid or ""),
                "createdAt": self._fv(iso_now()),
            }
        }

        r = requests.post(f"{FS_BASE}/feedback", headers=h, json=payload)
        if r.status_code not in (200, 201):
            raise FirebaseError(f"Add feedback failed: {r.text}")

        try:
            if clinician_uid:
                self._ensure_patient_link(
                    owner_uid=clinician_uid,
                    patient_auth_uid=patient_auth_uid or patient_uid,
                    patient_name=patient_name,
                    patient_email=patient_email,
                )
        except Exception:
            pass

        return True

    def list_feedback_for_patient(
        self,
        patient_auth_uid: Optional[str],
        patient_email: Optional[str],
        patient_name: Optional[str],
        limit: int = 50,
    ):
        def _eq(field_path: str, value: str):
            return self._run_query(
                "feedback",
                where_filters=[(field_path, "EQUAL", value)],
                limit=limit,
            )

        merged, seen = [], set()
        for field, val in (
            ("patientAuthUid", patient_auth_uid),
            ("patientEmail", patient_email),
            ("patientName", patient_name),
        ):
            if val:
                for r in _eq(field, val):
                    if r["_id"] not in seen:
                        seen.add(r["_id"])
                        merged.append(r)

        merged.sort(key=lambda d: d.get("createdAt", ""), reverse=True)
        return merged

    def list_feedback_for_clinician(
        self, clinician_uid: str, limit: int = 100
    ):
        self._ensure_token()
        rows = self._run_query(
            "feedback",
            where_filters=[("clinicianUid", "EQUAL", clinician_uid)],
            limit=limit,
        )
        rows.sort(key=lambda d: d.get("createdAt", ""), reverse=True)
        return rows

    # ---------- Sessions ----------
    def create_session(
        self,
        start_iso: str,
        end_iso: str,
        clinician_uid: str,
        clinician_name: str,
        patient_auth_uid: str,
        patient_name: str,
        status: str,
        created_by_uid: str,
    ):
        self._ensure_token()
        h = {"Authorization": f"Bearer {self.id_token}"}

        payload = {
            "fields": {
                "startAt": self._fv(start_iso),
                "endAt": self._fv(end_iso),
                "clinicianUid": self._fv(clinician_uid),
                "clinicianName": self._fv(clinician_name),
                "patientAuthUid": self._fv(patient_auth_uid),
                "patientName": self._fv(patient_name),
                "status": self._fv(status),
                "createdByUid": self._fv(created_by_uid),
                "createdAt": self._fv(iso_now()),
            }
        }

        r = requests.post(f"{FS_BASE}/sessions", headers=h, json=payload)
        if r.status_code not in (200, 201):
            raise FirebaseError(f"Create session failed: {r.text}")

        try:
            if clinician_uid:
                self._ensure_patient_link(
                    owner_uid=clinician_uid,
                    patient_auth_uid=patient_auth_uid,
                    patient_name=patient_name,
                    patient_email="",
                )
        except Exception:
            pass

        return True

    def list_sessions_for_user(
        self,
        role: str,
        uid: str,
        display_name: str,
        date_iso: Optional[str] = None,
    ):
        """
        Provider: sessions where they're clinicianUid
        Patient:  sessions where they're patientAuthUid
        """
        if role.startswith("Physiotherapist") or role.startswith("Doctor") or role.startswith("Provider") or role.startswith("Coach"):
            rows = self._run_query(
                "sessions",
                where_filters=[("clinicianUid", "EQUAL", uid)],
                limit=400,
            )
        else:
            rows = self._run_query(
                "sessions",
                where_filters=[("patientAuthUid", "EQUAL", uid)],
                limit=400,
            )

        if date_iso:
            d = date_iso[:10]
            rows = [
                s for s in rows
                if date_only(s.get("startAt", "")) == d
            ]

        rows.sort(key=lambda s: s.get("startAt", ""))
        return rows

    def cancel_session(self, session_id: str):
        self._ensure_token()
        h = {"Authorization": f"Bearer {self.id_token}"}

        url = self._doc_url(f"sessions/{session_id}")
        r = requests.get(url, headers=h)
        if r.status_code != 200:
            raise FirebaseError(f"Load session failed: {r.text}")
        fields = r.json().get("fields", {})
        fields["status"] = self._fv("cancelled")

        r2 = requests.patch(url, headers=h, json={"fields": fields})
        if r2.status_code not in (200, 201):
            raise FirebaseError(f"Cancel session failed: {r2.text}")
        return True

    # ---------- Exercise logs / metrics ----------
    def add_exercise_log(
        self,
        patient_uid: str,
        date_yyyy_mm_dd: str,
        exercise: str,
        reps: int,
    ):
        self._ensure_token()
        h = {"Authorization": f"Bearer {self.id_token}"}

        payload = {
            "fields": {
                "patientAuthUid": self._fv(patient_uid),
                "date": self._fv(date_yyyy_mm_dd),
                "exercise": self._fv(exercise),
                "reps": self._fv(int(reps)),
                "createdAt": self._fv(iso_now()),
            }
        }

        r = requests.post(f"{FS_BASE}/exercise_logs", headers=h, json=payload)
        if r.status_code not in (200, 201):
            raise FirebaseError(f"Add exercise log failed: {r.text}")
        return True

    def get_patient_metrics(self, patient_auth_uid: str) -> dict:
        today = datetime.now(timezone.utc).date()
        week_ago = today - timedelta(days=7)
        now_utc = datetime.now(timezone.utc)

        sessions = self._run_query(
            "sessions",
            where_filters=[("patientAuthUid", "EQUAL", patient_auth_uid)],
            limit=400,
        )

        sessions_7d = 0
        next_session_iso = ""
        next_dt = None
        for s in sessions:
            st = parse_iso(s.get("startAt", ""))
            if not st:
                continue
            d = st.date()
            status = s.get("status", "")
            if week_ago <= d <= today and status in ("scheduled", "completed"):
                sessions_7d += 1
            if st > now_utc and status == "scheduled":
                if next_dt is None or st < next_dt:
                    next_dt = st
                    next_session_iso = s.get("startAt", "")[:16].replace("T", " ")

        logs = self._run_query(
            "exercise_logs",
            where_filters=[("patientAuthUid", "EQUAL", patient_auth_uid)],
            limit=1000,
        )

        total_reps = 0
        days_with_logs = set()
        for l in logs:
            total_reps += int(l.get("reps", 0) or 0)
            d = (l.get("date", "") or "")[:10]
            if d:
                days_with_logs.add(d)

        # streak calc
        streak = 0
        cursor = today
        while cursor.strftime("%Y-%m-%d") in days_with_logs:
            streak += 1
            cursor = cursor - timedelta(days=1)

        return {
            "sessions_7d": sessions_7d,
            "total_reps": total_reps,
            "streak_days": streak,
            "next_session": next_session_iso,
        }

    # ---------- NEW: Exercise Videos ----------
    def record_exercise_video_submission(
        self,
        patient_auth_uid: str,
        patient_name: str,
        clinician_uid: str,
        clinician_name: str,
        exercise_name: str,
        note: str,
        video_path: str,
    ):
        """
        Store a row in Firestore collection 'exerciseVideos'.
        We save local file path as 'videoPath' so provider can open it.
        """
        self._ensure_token()
        h = {"Authorization": f"Bearer {self.id_token}"}

        payload = {
            "fields": {
                "patientAuthUid": self._fv(patient_auth_uid),
                "patientName": self._fv(patient_name),
                "clinicianUid": self._fv(clinician_uid),
                "clinicianName": self._fv(clinician_name),
                "exerciseName": self._fv(exercise_name),
                "note": self._fv(note),
                "videoPath": self._fv(video_path),
                "createdAt": self._fv(iso_now()),
            }
        }

        r = requests.post(f"{FS_BASE}/exerciseVideos", headers=h, json=payload)
        if r.status_code not in (200, 201):
            raise FirebaseError(f"Video record failed: {r.text}")
        return True

    def list_exercise_videos_for_provider(self, clinician_uid: str) -> List[Dict[str, Any]]:
        """
        Return newest-first exercise videos addressed to this clinician.
        """
        rows = self._run_query(
            "exerciseVideos",
            where_filters=[("clinicianUid", "EQUAL", clinician_uid)],
            limit=400,
        )
        rows.sort(key=lambda r: r.get("createdAt", ""), reverse=True)
        return rows
