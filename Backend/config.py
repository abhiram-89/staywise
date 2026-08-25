import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)


COGNODB_URI = os.getenv("COGNODB_URI", "").strip()
COGNODB_USER = os.getenv("COGNODB_USER", "cognodb").strip()
COGNODB_PASSWORD = os.getenv("COGNODB_PASSWORD", "").strip()

JWT_SECRET = os.getenv("JWT_SECRET", "dev-insecure-secret")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")
HOTEL_ID = os.getenv("HOTEL_ID", "grand-metro")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

