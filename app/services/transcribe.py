def transcribe_audio(audio_path: str, whisper_model) -> tuple[str, list]:
    segments_generator, info = whisper_model.transcribe(
        audio_path,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )
    segments = [
        {"start": s.start, "end": s.end, "text": s.text}
        for s in segments_generator
    ]
    return info.language, segments
