import os
from dotenv import load_dotenv

# Load .env from the app/ directory before any module that reads env vars is imported.
# Override MINIO_ENDPOINT so tests reach the Docker-exposed port on localhost
# instead of the Docker-internal hostname "minio".
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
os.environ["MINIO_ENDPOINT"] = "http://localhost:9000"

import pytest
from faster_whisper import WhisperModel
from transformers import AutoTokenizer
from huggingface_hub import snapshot_download
import ctranslate2

@pytest.fixture(scope="session")
def whisper_model():
    return WhisperModel("base", device="cpu", compute_type="int8")

@pytest.fixture(scope="session")
def nllb_models():
    model_path = snapshot_download("JustFrederik/nllb-200-distilled-600M-ct2-int8")
    tokenizer = AutoTokenizer.from_pretrained("facebook/nllb-200-distilled-600M")
    model = ctranslate2.Translator(model_path, device="cpu")
    return tokenizer, model
