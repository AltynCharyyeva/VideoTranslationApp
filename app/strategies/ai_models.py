from faster_whisper import WhisperModel
from transformers import AutoTokenizer
from huggingface_hub import snapshot_download
import ctranslate2

_whisper = None
_translator = None
_tokenizer = None

def load_whisper_process():
    global _whisper
    _whisper = WhisperModel("base", device="cpu", compute_type="int8")

def load_nllb_process():
    global _translator, _tokenizer
    model_path = snapshot_download(
        "JustFrederik/nllb-200-distilled-600M-ct2-int8"
    )
    _translator = ctranslate2.Translator(model_path, device="cpu")
    _tokenizer = AutoTokenizer.from_pretrained("facebook/nllb-200-distilled-600M")

def load_ai_models():
    """Legacy — loads both, used if you want a single pool."""
    load_whisper_process()
    load_nllb_process()

def get_whisper(): return _whisper
def get_nllb(): return _translator
def get_tokenizer(): return _tokenizer