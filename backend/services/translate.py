def translate_segments(segments: list, target_lang: str, tokenizer, nllb_model) -> list:
    translated_lines = []
    
    for segment in segments:
        inputs = tokenizer(segment["text"].strip(), return_tensors="pt")
        tokens = nllb_model.generate(
            **inputs,
            forced_bos_token_id=tokenizer.convert_tokens_to_ids(target_lang)
        )
        translation = tokenizer.batch_decode(tokens, skip_special_tokens=True)[0]
        translated_lines.append(f"[{segment['start']:.2f}] {translation}")
    
    print("Transcriptions translated\n")
    return translated_lines