WHISPER_TO_NLLB = {
    "en": "eng_Latn", "tr": "tur_Latn", "de": "deu_Latn",
    "fr": "fra_Latn", "es": "spa_Latn", "it": "ita_Latn",
    "ru": "rus_Cyrl", "zh": "zho_Hans", "ja": "jpn_Jpan",
    "ko": "kor_Hang", "ar": "arb_Arab", "pt": "por_Latn",
    "nl": "nld_Latn", "pl": "pol_Latn", "uk": "ukr_Cyrl",
    "tk": "tuk_Latn", "kk": "kaz_Cyrl", "uz": "uzb_Latn", "ky": "kir_Cyrl",
}


def translate_segments(segments: list, target_lang: str, tokenizer, nllb_model, source_lang: str = None) -> list:
    translated_lines = []
    if not segments:
        return []

    texts = [s["text"].strip() for s in segments]

    # Tell NLLB what language the source text is in, so it picks the right vocab/prefix
    tokenizer.src_lang = WHISPER_TO_NLLB.get(source_lang, "eng_Latn")

    # 1. Tokenize
    source_tokens = []
    for text in texts:
        encoded = tokenizer(text, add_special_tokens=True)
        tokens = tokenizer.convert_ids_to_tokens(encoded["input_ids"])
        source_tokens.append(tokens)

    # 2. Target prefix
    # Ensure target_lang is the full NLLB code like 'fra_Latn'
    target_prefix = [[target_lang]] * len(source_tokens)

    # 3. Translate
    results = nllb_model.translate_batch(
        source_tokens,
        target_prefix=target_prefix,
        beam_size=4,
        max_batch_size=16,
    )

    # 4. Decode results
    for result in results:
        # Drop the forced target-language prefix token, then decode and
        # let skip_special_tokens clean up any remaining special/unknown tokens
        output_tokens = result.hypotheses[0][1:]
        translation = tokenizer.decode(
            tokenizer.convert_tokens_to_ids(output_tokens),
            skip_special_tokens=True,
        ).strip()
        translated_lines.append(translation)

    print(f"Translated {len(segments)} segments via CTranslate2.")
    return translated_lines
