
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = "/app/storage"

UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
AUDIOS_DIR = os.path.join(BASE_DIR, "audios")
TRANSLATIONS_DIR = os.path.join(BASE_DIR, "translations")
TRANSCRIPTIONS_DIR = os.path.join(BASE_DIR, "transcriptions")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(AUDIOS_DIR, exist_ok=True)
os.makedirs(TRANSLATIONS_DIR, exist_ok=True)
os.makedirs(TRANSCRIPTIONS_DIR, exist_ok=True)
