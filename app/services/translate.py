def translate_segments(segments: list, target_lang: str, tokenizer, nllb_model) -> list:
    translated_lines = []
    if not segments:
        return []

    texts = [s["text"].strip() for s in segments]

    # 1. Tokenize
    source_tokens = []
    for text in texts:
        # Use src_lang if you know it, otherwise it defaults to the tokenizer's default
        encoded = tokenizer(text, add_special_tokens=True) 
        tokens = tokenizer.convert_ids_to_tokens(encoded["input_ids"])
        source_tokens.append(tokens)

    # 2. Target prefix
    # Ensure target_lang is the full NLLB code like 'fra_Latn'
    target_prefix = [[target_lang]] * len(source_tokens)

    # 3. Translate
    # asynchronous=False ensures it waits for the result (standard behavior)
    results = nllb_model.translate_batch(
        source_tokens,
        target_prefix=target_prefix,
        beam_size=4,
        max_batch_size=16,
        # asynchronous=False 
    )

    # 4. Decode results
    for i, result in enumerate(results):
        output_tokens = result.hypotheses[0]

        # CTranslate2 often returns the target_lang as the first token because of target_prefix
        if output_tokens and output_tokens[0] == target_lang:
            output_tokens = output_tokens[1:]
        
        # Also strip the </s> token if it appears at the end
        if output_tokens and output_tokens[-1] == "</s>":
            output_tokens = output_tokens[:-1]

        translation = tokenizer.convert_tokens_to_string(output_tokens).strip()
        
        start_time = segments[i]["start"]
        translated_lines.append(f"[{start_time:.2f}] {translation}")

    print(f"Translated {len(segments)} segments via CTranslate2.")
    return translated_lines