import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


COGNODB_URI = os.getenv("COGNODB_URI", "").strip()
COGNODB_USER = os.getenv("COGNODB_USER", "cognodb").strip()
COGNODB_PASSWORD = os.getenv("COGNODB_PASSWORD", "").strip()

JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-secret")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))
DEBUG_RETURN_OTP = _bool("DEBUG_RETURN_OTP", "true")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SMTP_FROM = os.getenv("SMTP_FROM", "").strip()

FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
HOTEL_ID = os.getenv("HOTEL_ID", "grand-metro")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
RESEND_FROM = os.getenv("RESEND_FROM", "Staywise <onboarding@resend.dev>").strip()

MAILJET_API_KEY = os.getenv("MAILJET_API_KEY", "").strip()
MAILJET_SECRET_KEY = os.getenv("MAILJET_SECRET_KEY", "").strip()
MAIL_FROM_EMAIL = os.getenv("MAIL_FROM_EMAIL", "").strip()
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "Staywise").strip()

OTP_TTL_SECONDS = 300
OTP_RESEND_SECONDS = 45
