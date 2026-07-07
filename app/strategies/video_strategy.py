import json
import asyncio
import subprocess
import numpy as np
from abc import ABC, abstractmethod
from yt_dlp import YoutubeDL
from strategies.ai_models import get_whisper, get_nllb, get_tokenizer

WHISPER_TO_NLLB = {
    "en": "eng_Latn", "tr": "tur_Latn", "de": "deu_Latn",
    "fr": "fra_Latn", "es": "spa_Latn", "it": "ita_Latn",
    "ru": "rus_Cyrl", "zh": "zho_Hans", "ja": "jpn_Jpan",
    "ko": "kor_Hang", "ar": "arb_Arab", "pt": "por_Latn",
    "nl": "nld_Latn", "pl": "pol_Latn", "uk": "ukr_Cyrl",
}


def run_whisper_only(pcm_bytes: bytes) -> dict:
    """
    Runs in whisper_executor pool.
    Returns source text + metadata. No translation.
    Fast: ~200-600ms on CPU with int8.
    """
    model = get_whisper()
    if not model:
        print("[whisper worker] model is None!", flush=True)
        return {}

    samples = np.frombuffer(pcm_bytes, dtype=np.float32)
    print(f"[whisper worker] samples={samples.size} rms={float(np.sqrt(np.mean(samples**2))):.4f}", flush=True)
    
    if samples.size == 0:
        print("[whisper worker] empty samples", flush=True)
        return {}

    # RMS energy gate — skip silence
    rms = float(np.sqrt(np.mean(samples ** 2)))
    if rms < 0.01:
        print(f"[whisper worker] below energy threshold (rms={rms:.4f})", flush=True)  # ← ADD
        return {}

    segments, info = model.transcribe(
        samples,
        beam_size=1,
        temperature=0.0,
        best_of=1,
        max_new_tokens=128,
        without_timestamps=True,
        condition_on_previous_text=False,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )
    segments = list(segments)
    print(f"[whisper worker] segments={len(segments)} lang={info.language}", flush=True)
    if not segments:
        print("[whisper worker] no segments returned", flush=True)
        return {}


    NO_SPEECH_PROB_THRESHOLD = 0.6
    speech_segments = [s for s in segments if s.no_speech_prob < NO_SPEECH_PROB_THRESHOLD]
    if not speech_segments:
        print(f"[whisper worker] all segments flagged as non-speech "
              f"(no_speech_prob >= {NO_SPEECH_PROB_THRESHOLD})", flush=True)
        return {}

    text = " ".join(s.text for s in speech_segments).strip()
    print(f"[whisper worker] text='{text}'", flush=True)

    if not text or len(text.split()) < 2:
        print(f"[whisper worker] text too short: '{text}'", flush=True)
        return {}

    is_final = text.endswith(('.', '!', '?', '"', '»', '...'))

    return {
        "source_text": text,
        "detected_lang": info.language,
        "is_final": is_final,
    }


def run_translation_only(text: str, detected_lang: str, target_lang: str) -> str:
    """
    Runs in nllb_executor pool.
    Returns translated string.
    ~200-500ms on CPU.
    """
    translator = get_nllb()
    tokenizer = get_tokenizer()
    if not translator or not tokenizer:
        return ""
    if not text:
        return ""

    src_lang = WHISPER_TO_NLLB.get(detected_lang, "eng_Latn")
    tokenizer.src_lang = src_lang

    encoded = tokenizer(text, return_tensors="pt")
    source_tokens = tokenizer.convert_ids_to_tokens(encoded["input_ids"][0])

    result = translator.translate_batch(
        [source_tokens],
        target_prefix=[[target_lang]],
        beam_size=2,
        max_decoding_length=256,
    )
    output_tokens = result[0].hypotheses[0][1:]
    return tokenizer.decode(
        tokenizer.convert_tokens_to_ids(output_tokens),
        skip_special_tokens=True
    )


# ── STRATEGIES ──

class BaseVideoProcessingStrategy(ABC):
    def __init__(self, stop_event):
        self.stop_event = stop_event

    @abstractmethod
    async def read_stream(self, source: str, websocket, start_time: float = 0.0, pause_event=None):
        pass


class UploadVideoProcessing(BaseVideoProcessingStrategy):

    async def read_stream(self, source: str, websocket, start_time: float = 0.0, pause_event=None):
        command = [
            "ffmpeg", "-i", "pipe:0",
            "-f", "f32le", "-acodec", "pcm_f32le", "-ac", "1", "-ar", "16000",
            "pipe:1"
        ]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )
        try:
            while not self.stop_event.is_set():
                message_text = await websocket.receive_text()
                if not message_text:
                    continue

                packet = json.loads(message_text)
                timestamp = float(packet["timestamp"])
                audio_bytes = bytes(packet["audio"])
                if not audio_bytes:
                    continue

                process.stdin.write(audio_bytes)
                await process.stdin.drain()
                await asyncio.sleep(0.02)

                stdout_data = b""
                while True:
                    try:
                        chunk = await asyncio.wait_for(
                            process.stdout.read(16000), timeout=0.01
                        )
                        if not chunk:
                            break
                        stdout_data += chunk
                        if len(chunk) < 16000:
                            break
                    except asyncio.TimeoutError:
                        break

                if stdout_data:
                    yield (stdout_data, timestamp)

        except asyncio.CancelledError:
            pass
        finally:
            if process.returncode is None:
                try:
                    process.stdin.close()
                    process.terminate()
                    await process.wait()
                except Exception:
                    pass


class YouTubeVideoProcessing(BaseVideoProcessingStrategy):

    def _extract_live_stream_url(self, youtube_url: str) -> str:
        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'cookiefile': '/app/cookies.txt',
            'format_sort': ['abr', 'asr'],
            'extractor_args': {
                'youtube': {'player_client': ['android', 'tv', 'web']},
            },
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            return info['url']

    async def read_stream(self, source: str, websocket, start_time: float = 0.0, pause_event=None):
        if not source:
            return

        loop = asyncio.get_running_loop()
        direct_url = await loop.run_in_executor(
            None, self._extract_live_stream_url, source
        )

        ffmpeg_cmd = ["ffmpeg"]
        if start_time > 0:
            ffmpeg_cmd += ["-ss", str(start_time)]
        ffmpeg_cmd += [
            "-i", direct_url,
            "-f", "f32le", "-acodec", "pcm_f32le", "-ac", "1", "-ar", "16000",
            "pipe:1"
        ]
        ffmpeg_process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL
        )


        try:
            await websocket.send_json({"status": "READY"})
        except Exception:
            pass

        accumulated_seconds = start_time
        bytes_per_second = 16000 * 4
        stream_start_wall = loop.time()

        try:
            while not self.stop_event.is_set():
                if pause_event is not None and pause_event.is_set():
                    pause_started = loop.time()
                    while pause_event.is_set() and not self.stop_event.is_set():
                        await asyncio.sleep(0.1)
                    stream_start_wall += loop.time() - pause_started
                    continue

                chunk_bytes = await ffmpeg_process.stdout.read(64000)
                if not chunk_bytes:
                    break

                timestamp = accumulated_seconds
                chunk_duration = len(chunk_bytes) / bytes_per_second
                accumulated_seconds += chunk_duration

                yield (chunk_bytes, timestamp)


                target_wall = stream_start_wall + (accumulated_seconds - start_time)
                sleep_for = target_wall - loop.time()
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)

        except asyncio.CancelledError:
            pass
        finally:
            if ffmpeg_process and ffmpeg_process.returncode is None:
                try:
                    ffmpeg_process.terminate()
                    await ffmpeg_process.wait()
                except Exception:
                    pass