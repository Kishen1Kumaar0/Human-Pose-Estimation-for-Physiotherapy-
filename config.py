APP_TITLE = "PoseCare • Rehab Coach"

# Roles shown in the UI
ROLES = ["Physiotherapist", "Doctor", "Patient", "Researcher"]

# ========= Firebase config (REST) =========
WEB_API_KEY = "AIzaSyBN7BBttMYCsuS6ESc8D_aVFKELev4E3rs"  # must start with AIzaSy
PROJECT_ID  = "posecare-prod"

# Print quick sanity in console (optional)
if __name__ == "__main__":
    print("WEB_API_KEY starts:", WEB_API_KEY[:6])  # AIzaSy...
    print("PROJECT_ID:", PROJECT_ID)
