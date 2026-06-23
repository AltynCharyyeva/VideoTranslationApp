import pytest
from services.translate import translate_segments

KNOWN_INPUTS = [
    {"start": 0.0, "end": 2.0, "text": "Hello, how are you?"},
    {"start": 2.0, "end": 4.0, "text": "The weather is nice today."},
]

def test_translation_changes_the_text(nllb_models):
    tokenizer, model = nllb_models
    results = translate_segments(KNOWN_INPUTS, "ron_Latn", tokenizer, model, source_lang="en")
    assert len(results) == 2
    assert results[0] != "Hello, how are you?"   # was actually translated
    assert all(len(r) > 0 for r in results)

def test_no_unk_tokens_in_output(nllb_models):
    tokenizer, model = nllb_models
    results = translate_segments(KNOWN_INPUTS, "ron_Latn", tokenizer, model, source_lang="en")
    assert not any("<unk>" in r for r in results)

def test_no_timestamp_prefix_in_output(nllb_models):
    # regression: old bug embedded [21.30] prefixes in translations
    tokenizer, model = nllb_models
    results = translate_segments(KNOWN_INPUTS, "ron_Latn", tokenizer, model, source_lang="en")
    import re
    assert not any(re.match(r"^\[\d+\.\d+\]", r) for r in results)

def test_translation_unknown_source_language_defaults_gracefully(nllb_models):
    tokenizer, model = nllb_models
    results = translate_segments(KNOWN_INPUTS, "ron_Latn", tokenizer, model, source_lang=None)
    assert len(results) == 2
    assert all(len(r) > 0 for r in results)
