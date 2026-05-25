import uuid
import asyncio
import traceback
from concurrent.futures import ProcessPoolExecutor
from fastapi import APIRouter, WebSocket, Query, WebSocketDisconnect
from strategies.video_strategy import (
    YouTubeVideoProcessing,
    UploadVideoProcessing,
    run_whisper_only,
    run_translation_only,
)
from strategies.ai_models import load_whisper_process, load_nllb_process

router = APIRouter(prefix="/streams", tags=["streams"])
active_streams = {}

# ── Two dedicated pools — models never share memory, no contention ──
# Whisper pool: 1 worker is enough, it uses all CPU cores internally
# NLLB pool:    1 worker, runs concurrently with Whisper pool
whisper_executor = ProcessPoolExecutor(max_workers=1, initializer=load_whisper_process)
nllb_executor    = ProcessPoolExecutor(max_workers=1, initializer=load_nllb_process)

STRATEGY_MAP = {
    "true": YouTubeVideoProcessing,
    "false": UploadVideoProcessing,
}

# How many new source words trigger a translation update
TRANSLATE_EVERY_N_WORDS = 5


@router.websocket("/ws")
async def websocket_stream_endpoint(
    websocket: WebSocket,
    target_lang: str = Query(...),
    is_youtube: str = Query("false"),
    source: str = None,
):
    await websocket.accept()
    stream_id = str(uuid.uuid4())
    active_streams[stream_id] = websocket
    stop_event = asyncio.Event()

    await websocket.send_json({"status": "CONNECTED", "stream_id": stream_id})

    strategy_class = STRATEGY_MAP.get(is_youtube.lower(), UploadVideoProcessing)
    strategy = strategy_class(stop_event)          # no executor needed in strategy anymore

    audio_queue  = asyncio.Queue(maxsize=10)
    result_queue = asyncio.Queue()

    # ── TASK 1: READ ──
    async def reader_task():
        print(f"[{stream_id}] Reader started")
        try:
            async for chunk in strategy.read_stream(source, websocket):
                if stop_event.is_set():
                    break
                try:
                    audio_queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    # Drop oldest, keep newest — prevents lag buildup
                    try:
                        audio_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    await audio_queue.put(chunk)
        except WebSocketDisconnect:
            print(f"[{stream_id}] Reader: client disconnected")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[{stream_id}] Reader exception: {type(e).__name__}: {e}")
            traceback.print_exc()
        finally:
            print(f"[{stream_id}] Reader finished")
            await audio_queue.put(None)
            stop_event.set()

    # ── TASK 2: INFERENCE — two-phase, two pools ──
    async def inference_task():
        print(f"[{stream_id}] Inference started")
        loop = asyncio.get_running_loop()

        # Per-stream incremental state
        words_since_last_translation = 0
        last_source_text = ""
        last_translated_text = ""

        try:
            while True:
                # Drain queue — always work on freshest chunk
                chunk = await audio_queue.get()
                if chunk is None:
                    print(f"[{stream_id}] Inference: got None sentinel, stopping")
                    break
                while not audio_queue.empty():
                    drained = audio_queue.get_nowait()
                    if drained is None:
                        await result_queue.put(None)
                        return
                    chunk = drained

                if stop_event.is_set():
                    break

                pcm_bytes, timestamp = chunk
                print(f"[{stream_id}] Inference: got chunk {len(pcm_bytes)} bytes @ {timestamp:.2f}s")

                # ── PHASE 1: Whisper only (~200-600ms) ──
                # Runs in whisper_executor, NLLB executor is free during this time
                try:
                    whisper_result = await loop.run_in_executor(
                        whisper_executor,
                        run_whisper_only,
                        pcm_bytes,
                    )
                except Exception as e:
                    print(f"[{stream_id}] Whisper exception: {e}")
                    traceback.print_exc()
                    continue
                print(f"[{stream_id}] Whisper result: {whisper_result}")
                
                if not whisper_result:
                    print(f"[{stream_id}] Whisper returned empty — skipping")
                    continue

                source_text   = whisper_result["source_text"]
                detected_lang = whisper_result["detected_lang"]
                is_final      = whisper_result["is_final"]
                last_detected_lang = detected_lang

                # Count new words since last translation pass
                current_word_count  = len(source_text.split())
                previous_word_count = len(last_source_text.split())
                new_words = max(current_word_count - previous_word_count, 0)
                words_since_last_translation += new_words
                last_source_text = source_text

                # ── PHASE 2: NLLB — only when we have enough new words or sentence ends ──
                should_translate = (
                    words_since_last_translation >= TRANSLATE_EVERY_N_WORDS
                    or is_final
                    or not last_translated_text   # always translate at least once
                )

                if should_translate:
                    # Runs in nllb_executor concurrently — whisper_executor is free
                    try:
                        translated = await loop.run_in_executor(
                            nllb_executor,
                            run_translation_only,
                            source_text,
                            detected_lang,
                            target_lang,
                        )
                        last_translated_text = translated
                        words_since_last_translation = 0
                    except Exception as e:
                        print(f"[{stream_id}] NLLB exception: {e}")
                        traceback.print_exc()
                        translated = last_translated_text  # fall back to last good translation
                else:
                    # Reuse last translation — source text updates, translation holds
                    translated = last_translated_text

                await result_queue.put({
                    "source_text": source_text,
                    "translated_text": translated,
                    "is_final": is_final,
                })

                # Reset on sentence boundary
                if is_final:
                    last_source_text = ""
                    last_translated_text = ""
                    words_since_last_translation = 0

        except asyncio.CancelledError:
            pass
        finally:
            print(f"[{stream_id}] Inference finished")
            await result_queue.put(None)

    # ── TASK 3: SEND ──
    async def sender_task():
        print(f"[{stream_id}] Sender started")
        try:
            while True:
                result = await result_queue.get()
                if result is None:
                    break
                if stop_event.is_set():
                    break

                if isinstance(result, dict) and result.get("status") == "ERROR":
                    try:
                        await websocket.send_json(result)
                    except Exception:
                        pass
                    break

                try:
                    await websocket.send_json({
                        "status": "SUBTITLE",
                        "data": {
                            "source_text":    result.get("source_text", ""),
                            "translated_text": result.get("translated_text", ""),
                            "is_final":        result.get("is_final", False),
                        }
                    })
                    print(f"[{stream_id}] Sent ({'FINAL' if result.get('is_final') else 'interim'}): "
                          f"{result.get('source_text', '')[:50]}")
                except WebSocketDisconnect:
                    print(f"[{stream_id}] Sender: client disconnected")
                    break
                except Exception as e:
                    print(f"[{stream_id}] Sender exception: {e}")
                    break
        except asyncio.CancelledError:
            pass
        finally:
            print(f"[{stream_id}] Sender finished")
            stop_event.set()

    reader   = asyncio.create_task(reader_task())
    inference = asyncio.create_task(inference_task())
    sender   = asyncio.create_task(sender_task())

    try:
        await asyncio.wait_for(stop_event.wait(), timeout=3600)
    except asyncio.TimeoutError:
        print(f"[{stream_id}] 1 hour timeout reached.")
    except WebSocketDisconnect:
        print(f"[{stream_id}] Main: client disconnected.")
    finally:
        active_streams.pop(stream_id, None)
        stop_event.set()
        reader.cancel()
        inference.cancel()
        sender.cancel()
        await asyncio.gather(reader, inference, sender, return_exceptions=True)
        try:
            await websocket.close()
        except Exception:
            pass