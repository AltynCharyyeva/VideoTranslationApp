
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = "/app/storage"

UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
AUDIOS_DIR = os.path.join(BASE_DIR, "audios")
TRANSLATIONS_DIR = os.path.join(BASE_DIR, "translations")
TRANSCRIPTIONS_DIR = os.path.join(BASE_DIR, "transcriptions")
DUBBED_AUDIOS_DIR = os.path.join(BASE_DIR, "dubbed_audios")
DUBBED_VIDEOS_DIR = os.path.join(BASE_DIR, "dubbed_videos")

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(AUDIOS_DIR, exist_ok=True)
os.makedirs(TRANSLATIONS_DIR, exist_ok=True)
os.makedirs(TRANSCRIPTIONS_DIR, exist_ok=True)
os.makedirs(DUBBED_AUDIOS_DIR, exist_ok=True)
os.makedirs(DUBBED_VIDEOS_DIR, exist_ok=True)
