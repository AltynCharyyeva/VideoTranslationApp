import pytest
from services.transcribe import transcribe_audio

def test_transcription_returns_language_and_segments(whisper_model):
    lang, segments = transcribe_audio("tests/fixtures/song.wav", whisper_model)
    assert isinstance(lang, str) and len(lang) == 2          # ISO 639-1 code
    assert isinstance(segments, list) and len(segments) > 0
    assert all("start" in s and "end" in s and "text" in s for s in segments)

def test_silence_produces_no_segments(whisper_model):
    # VAD filter should suppress silent audio entirely
    lang, segments = transcribe_audio("tests/fixtures/silence.wav", whisper_model)
    assert segments == []

def test_timestamps_are_ordered(whisper_model):
    _, segments = transcribe_audio("tests/fixtures/song.wav", whisper_model)
    starts = [s["start"] for s in segments]
    assert starts == sorted(starts)
    assert all(s["end"] > s["start"] for s in segments)

def test_noisy_audio_still_produces_output(whisper_model):
    # background noise should not crash the pipeline
    lang, segments = transcribe_audio("tests/fixtures/noise.wav", whisper_model)
    assert isinstance(segments, list)   # may be empty — that's acceptable
