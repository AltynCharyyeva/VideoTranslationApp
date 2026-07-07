import uuid
import asyncio
import traceback
from concurrent.futures import ProcessPoolExecutor
from fastapi import APIRouter, WebSocket, Query, WebSocketDisconnect
from fastapi import HTTPException
from strategies.video_strategy import (
    YouTubeVideoProcessing,
    UploadVideoProcessing,
    run_whisper_only,
    run_translation_only,
)
from strategies.ai_models import load_whisper_process, load_nllb_process
from auth.dependencies import decode_token
from database.database import SessionLocal

router = APIRouter(prefix="/streams", tags=["streams"])
active_streams = {}

whisper_executor = ProcessPoolExecutor(max_workers=1, initializer=load_whisper_process)
nllb_executor    = ProcessPoolExecutor(max_workers=1, initializer=load_nllb_process)

STRATEGY_MAP = {
    "true": YouTubeVideoProcessing,
    "false": UploadVideoProcessing,
}

# 3 seconds of f32le PCM at 16 kHz 
WINDOW_BYTES  = int(3.0 * 16000 * 4)
# 0.5 s overlap keeps words at chunk boundaries from being dropped
OVERLAP_BYTES = int(0.5 * 16000 * 4)
# If the buffer grows past 9 s we're falling behind — trim to stay live
MAX_BUFFER_BYTES = WINDOW_BYTES * 3


@router.websocket("/ws")
async def websocket_stream_endpoint(
    websocket: WebSocket,
    target_lang: str = Query(...),
    token: str = Query(...),
    is_youtube: str = Query("false"),
    source: str = None,
    start_seconds: float = Query(0.0),
):
    await websocket.accept()

    db = SessionLocal()
    try:
        decode_token(token, db)
    except HTTPException:
        await websocket.send_json({"status": "ERROR", "detail": "Not authenticated"})
        await websocket.close(code=1008)
        return
    finally:
        db.close()

    stream_id = str(uuid.uuid4())
    active_streams[stream_id] = websocket
    stop_event = asyncio.Event()
    pause_event = asyncio.Event()
    is_youtube_stream = is_youtube.lower() == "true"

    await websocket.send_json({"status": "CONNECTED", "stream_id": stream_id})

    strategy_class = STRATEGY_MAP.get(is_youtube.lower(), UploadVideoProcessing)
    strategy = strategy_class(stop_event)

    audio_queue  = asyncio.Queue(maxsize=20)
    result_queue = asyncio.Queue()

    ###############################################################################################################
    # CONTROL — listen for pause/resume from the YouTube player 
    async def control_task():
        if not is_youtube_stream:
            return
        print(f"[{stream_id}] Control listener started")
        try:
            while not stop_event.is_set():
                msg = await websocket.receive_json()
                control = msg.get("control")
                if control == "PAUSE":
                    pause_event.set()
                elif control == "RESUME":
                    pause_event.clear()
        except WebSocketDisconnect:
            print(f"[{stream_id}] Client disconnected")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[{stream_id}] Control task exception: {e}")

    ###############################################################################################################
    #  READ
    async def reader_task():
        print(f"[{stream_id}] Reader started")
        try:
            async for chunk in strategy.read_stream(source, websocket, start_seconds, pause_event):
                if stop_event.is_set():
                    break
                try:
                    audio_queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    # Drop the oldest queued item so the reader never blocks ffmpeg
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

    ###############################################################################################################
    #  INFERENCE: whisper to  nllb 
    async def inference_task():
        print(f"[{stream_id}] Inference started")
        loop = asyncio.get_running_loop()

        audio_buffer: bytearray = bytearray()
        last_source_text   = ""
        last_translated    = ""
        pending_nllb       = None  

        async def process_window(window_bytes: bytes, is_end: bool = False):
            nonlocal last_source_text, last_translated, pending_nllb

            
            whisper_future = loop.run_in_executor(
                whisper_executor, run_whisper_only, window_bytes
            )

            if pending_nllb is not None:
                try:
                    result = await pending_nllb
                    if result:
                        last_translated = result
                except Exception as e:
                    print(f"[{stream_id}] NLLB exception: {e}")
                pending_nllb = None

            whisper_result = await whisper_future
            if not whisper_result:
                return

            source_text   = whisper_result["source_text"]
            detected_lang = whisper_result["detected_lang"]
            is_final      = whisper_result["is_final"] or is_end
            last_source_text = source_text

            
            await result_queue.put({
                "source_text":     source_text,
                "translated_text": last_translated,
                "is_final":        False,
            })

            
            pending_nllb = asyncio.ensure_future(
                loop.run_in_executor(
                    nllb_executor, run_translation_only,
                    source_text, detected_lang, target_lang,
                )
            )

            if is_final:
                try:
                    result = await pending_nllb
                    if result:
                        last_translated = result
                except Exception as e:
                    print(f"[{stream_id}] NLLB final exception: {e}")
                pending_nllb = None

                await result_queue.put({
                    "source_text":     source_text,
                    "translated_text": last_translated,
                    "is_final":        True,
                })
                last_source_text = ""
                last_translated  = ""

        try:
            while True:
                chunk = await audio_queue.get()

                if chunk is None:
                    if len(audio_buffer) > OVERLAP_BYTES:
                        await process_window(bytes(audio_buffer), is_end=True)
                    elif pending_nllb is not None:
                        try:
                            result = await pending_nllb
                            if result and last_source_text:
                                last_translated = result
                                await result_queue.put({
                                    "source_text":     last_source_text,
                                    "translated_text": last_translated,
                                    "is_final":        True,
                                })
                        except Exception:
                            pass
                    break

                if stop_event.is_set():
                    break

                pcm_bytes, _ = chunk
                audio_buffer.extend(pcm_bytes)

                # If we're falling behind real-time, throw the oldest audio
                if len(audio_buffer) > MAX_BUFFER_BYTES:
                    print(f"[{stream_id}] Buffer overflow — trimming to latest window")
                    del audio_buffer[:-WINDOW_BYTES]

                while len(audio_buffer) >= WINDOW_BYTES:
                    window_bytes = bytes(audio_buffer[:WINDOW_BYTES])
                    del audio_buffer[:WINDOW_BYTES - OVERLAP_BYTES]
                    await process_window(window_bytes)

        except asyncio.CancelledError:
            pass
        finally:
            if pending_nllb is not None:
                pending_nllb.cancel()
            print(f"[{stream_id}] Inference finished")
            await result_queue.put(None)

    ###############################################################################################################
    #  SEND 
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
                            "source_text":     result.get("source_text", ""),
                            "translated_text": result.get("translated_text", ""),
                            "is_final":        result.get("is_final", False),
                        }
                    })
                    print(f"[{stream_id}] Sent ({'FINAL' if result.get('is_final') else 'interim'}): "
                          f"{result.get('translated_text', '')[:50]}")
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

    control   = asyncio.create_task(control_task())
    reader    = asyncio.create_task(reader_task())
    inference = asyncio.create_task(inference_task())
    sender    = asyncio.create_task(sender_task())

    try:
        await asyncio.wait_for(stop_event.wait(), timeout=3600)
    except asyncio.TimeoutError:
        print(f"[{stream_id}] 1 hour timeout reached.")
    except WebSocketDisconnect:
        print(f"[{stream_id}] Main: client disconnected.")
    finally:
        active_streams.pop(stream_id, None)
        stop_event.set()
        control.cancel()
        reader.cancel()
        inference.cancel()
        sender.cancel()
        await asyncio.gather(control, reader, inference, sender, return_exceptions=True)
        try:
            await websocket.close()
        except Exception:
            pass
