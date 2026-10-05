import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR.parent / "clinic.db"))
CLINIC_FILE = os.environ.get("CLINIC_FILE", str(BASE_DIR.parent / "clinic.json"))
EMERGENCY_PRIMARY = os.environ.get("EMERGENCY_PRIMARY", "112")
EMERGENCY_AMBULANCE = os.environ.get("EMERGENCY_AMBULANCE", "108")
DAILY_TOKEN_CAP = int(os.environ.get("DAILY_TOKEN_CAP", "100000"))
RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "60"))

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
EXTRACT_MODE = os.environ.get("EXTRACT_MODE", "auto")


