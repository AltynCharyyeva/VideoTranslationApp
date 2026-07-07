import os
from faster_whisper import WhisperModel
from transformers import AutoTokenizer
from huggingface_hub import snapshot_download
import ctranslate2

#MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR", "/app/ai_models")

_whisper = None
_translator = None
_tokenizer = None

def load_whisper_process():
    global _whisper
    _whisper = WhisperModel(
        "base",
        device="cpu",
        compute_type="int8",
        #download_root=MODEL_CACHE_DIR
    )

def load_nllb_process():
    global _translator, _tokenizer
    model_path = snapshot_download(
        "JustFrederik/nllb-200-distilled-600M-ct2-int8",
        #cache_dir=MODEL_CACHE_DIR
    )
    _translator = ctranslate2.Translator(model_path, device="cpu")
    _tokenizer = AutoTokenizer.from_pretrained(
        "facebook/nllb-200-distilled-600M",
        #cache_dir=MODEL_CACHE_DIR
    )

def load_ai_models():
    load_whisper_process()
    load_nllb_process()

def get_whisper(): return _whisper
def get_nllb(): return _translator
def get_tokenizer(): return _tokenizer