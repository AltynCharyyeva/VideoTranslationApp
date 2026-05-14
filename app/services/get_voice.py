def get_voice_for_lang(target_lang: str) -> str:
    """
    Maps ISO language codes to Microsoft Edge TTS Neural voices.
    """
    voice_map = {
        "eng": "en-US-GuyNeural",
        "deu": "de-DE-ConradNeural",
        "rus": "ru-RU-DmitryNeural",
        "ron": "ro-RO-EmilNeural",   
        "tur": "tr-TR-AhmetNeural",  
    }
    return voice_map.get(target_lang.lower()[:3], "en-US-GuyNeural")