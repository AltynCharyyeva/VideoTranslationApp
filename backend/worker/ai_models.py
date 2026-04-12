# app/core/ai_models.py
import os
from faster_whisper import WhisperModel
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR", "/app/ai_models")

def load_ai_models():
    global _whisper, _tokenizer, _nllb
    _whisper = WhisperModel(
        "tiny",
        device="cpu",
        compute_type="int8",
        download_root=MODEL_CACHE_DIR
    )

    _tokenizer = AutoTokenizer.from_pretrained(
        "facebook/nllb-200-distilled-600M",
        cache_dir=MODEL_CACHE_DIR
    )

    _nllb = AutoModelForSeq2SeqLM.from_pretrained(
        "facebook/nllb-200-distilled-600M",
        cache_dir=MODEL_CACHE_DIR
    )
    print("Worker: AI models loaded.")

def get_whisper():
    return _whisper

def get_tokenizer():
    return _tokenizer

def get_nllb():
    return _nllb