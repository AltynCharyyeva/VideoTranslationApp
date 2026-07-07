WHISPER_TO_NLLB = {
    "en": "eng_Latn", "tr": "tur_Latn", "de": "deu_Latn",
    "fr": "fra_Latn", "es": "spa_Latn", "it": "ita_Latn",
    "ru": "rus_Cyrl", "zh": "zho_Hans", "ja": "jpn_Jpan",
    "ko": "kor_Hang", "ar": "arb_Arab", "pt": "por_Latn",
    "nl": "nld_Latn", "pl": "pol_Latn", "uk": "ukr_Cyrl",
    "tk": "tuk_Latn", "kk": "kaz_Cyrl", "uz": "uzn_Latn", "ky": "kir_Cyrl",
}


def translate_segments(segments: list, target_lang: str, tokenizer, nllb_model, source_lang: str = None) -> list:
    translated_lines = []
    if not segments:
        return []

    texts = [s["text"].strip() for s in segments]

    tokenizer.src_lang = WHISPER_TO_NLLB.get(source_lang, "eng_Latn")

    source_tokens = []
    for text in texts:
        encoded = tokenizer(text, add_special_tokens=True)
        tokens = tokenizer.convert_ids_to_tokens(encoded["input_ids"])
        source_tokens.append(tokens)


    target_prefix = [[target_lang]] * len(source_tokens)

    results = nllb_model.translate_batch(
        source_tokens,
        target_prefix=target_prefix,
        beam_size=4,
        max_batch_size=16,
    )


    for result in results:
        output_tokens = result.hypotheses[0][1:]
        translation = tokenizer.decode(
            tokenizer.convert_tokens_to_ids(output_tokens),
            skip_special_tokens=True,
        ).strip()
        translated_lines.append(translation)

    print(f"Translated {len(segments)} segments via CTranslate2.")
    return translated_lines
