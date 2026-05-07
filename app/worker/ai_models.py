# app/core/ai_models.py
import os
from faster_whisper import WhisperModel
import ctranslate2
from transformers import AutoTokenizer #AutoModelForSeq2SeqLM,
from huggingface_hub import snapshot_download

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
    model_path = snapshot_download(
        "JustFrederik/nllb-200-distilled-600M-ct2-int8",
        cache_dir=MODEL_CACHE_DIR
    )
    _nllb = ctranslate2.Translator(model_path, device="cpu")

    # _nllb = AutoModelForSeq2SeqLM.from_pretrained(
    #     "facebook/nllb-200-distilled-600M",
    #     cache_dir=MODEL_CACHE_DIR
    # )
    print("Worker: AI models loaded.")

def get_whisper():
    return _whisper

def get_tokenizer():
    return _tokenizer

def get_nllb():
    return _nllb