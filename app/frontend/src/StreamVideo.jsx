// StreamVideo.jsx
import React, { useState, useEffect, useRef } from "react";
import ReactPlayer from "react-player/youtube";
import styles from "./style/StreamVideo.module.css";

// Tuned to feel like YouTube's live captions: words trickle in instead of
// the whole line appearing at once, and longer final lines stay up longer.
const WORD_REVEAL_MS = 90;
const MIN_CLEAR_MS = 1200;
const CLEAR_MS_PER_WORD = 350;

const LANGUAGES = [
  { code: "tuk_Latn", name: "Turkmen" },
  { code: "ron_Latn", name: "Romanian" },
  { code: "deu_Latn", name: "German" },
  { code: "tur_Latn", name: "Turkish" },
  { code: "rus_Cyrl", name: "Russian" },
  { code: "eng_Latn", name: "English" },
  { code: "kaz_Cyrl", name: "Kazakh" },
  { code: "uzn_Latn", name: "Uzbek" },
  { code: "kir_Cyrl", name: "Kyrgyz" },
];

function StreamVideo({ videoData, token, onBack }) {
  const [targetLang, setTargetLang] = useState("");
  const [connectionStatus, setConnectionStatus] = useState("DISCONNECTED");
  const [subtitles, setSubtitles] = useState({ original: "", translation: "" });

  const playerRef = useRef(null);
  const nativeVideoRef = useRef(null); // Dedicated ref for the native local player
  const wsRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioContextRef = useRef(null);

  // Timeout pointer to maintain readability when buffers clear
  const subtitleTimeoutRef = useRef(null);
  // Interval pointer for the word-by-word reveal animation
  const revealIntervalRef = useRef(null);
  // Playback position captured on stop, so the next connect resumes here
  const resumeTimeRef = useRef(0);
  // True while the YouTube player is paused — gates incoming subtitles
  const isPausedRef = useRef(false);

  // Clean up streaming buffers when unmounting
  useEffect(() => {
    return () => {
      stopStreamingPipeline();
      if (subtitleTimeoutRef.current) clearTimeout(subtitleTimeoutRef.current);
      if (revealIntervalRef.current) clearInterval(revealIntervalRef.current);
    };
  }, []);

  // Monitor connection status changes to safely initialize the capture loop
  useEffect(() => {
    if (connectionStatus === "CONNECTED" && !videoData.isYouTube) {
      initLocalPipeline();
    }
  }, [connectionStatus]);

  const startStreamingPipeline = () => {
    setConnectionStatus("CONNECTING");
    isPausedRef.current = false;

    const isYouTube = videoData.isYouTube;
    const encodedSource = encodeURIComponent(videoData.url);

    const wsUrl = `ws://localhost:8000/streams/ws?target_lang=${targetLang}&is_youtube=${isYouTube}&source=${encodedSource}&token=${encodeURIComponent(token)}&start_seconds=${resumeTimeRef.current}`;
    wsRef.current = new WebSocket(wsUrl);

    wsRef.current.onopen = () => {
      // FIX: If it's a local video, kick off playback immediately on connect!
      // Do not block and wait for a subtitle response loop.
      if (!videoData.isYouTube) {
        setConnectionStatus("CONNECTED");
      }
    };

    wsRef.current.onmessage = (event) => {
      console.log("RAW MESSAGE:", event.data); // add this
      const payload = JSON.parse(event.data);
      console.log("PARSED:", payload);
      // Handle handshake confirmations
      if (payload.status === "CONNECTED") {
        setConnectionStatus("CONNECTED");
        return;
      }

      // Backend signals this the moment it starts decoding YouTube audio —
      // start the video here so it shares the same clock as the decoder,
      // instead of waiting for the first subtitle (which is already behind).
      if (payload.status === "READY") {
        if (videoData.isYouTube) {
          triggerInternalPlayback();
        }
        return;
      }

      if (payload.status === "SUBTITLE" || payload.source_text !== undefined) {
        // Drop captions that arrive while the player is paused, instead of
        // letting them roll in over a frozen frame
        if (isPausedRef.current) return;

        const data = payload.data || payload;

        revealSubtitle(
          data.source_text || "",
          data.translated_text || "",
          data.is_final,
        );
      }
    };

    wsRef.current.onerror = (err) => {
      console.error("WebSocket Error Encountered:", err);
      setConnectionStatus("ERROR");
    };

    wsRef.current.onclose = () => {
      console.log("WS CLOSED:", event.code, event.reason);
      setConnectionStatus("DISCONNECTED");
      stopStreamingPipeline();
    };
  };

  // Reveals a new caption word-by-word instead of slamming the whole line
  // in at once, and scales the post-final readability window to sentence
  // length instead of a flat delay.
  const revealSubtitle = (sourceText, translatedText, isFinal) => {
    if (revealIntervalRef.current) clearInterval(revealIntervalRef.current);
    if (subtitleTimeoutRef.current) clearTimeout(subtitleTimeoutRef.current);

    const originalWords = sourceText ? sourceText.split(/\s+/) : [];
    const translationWords = translatedText ? translatedText.split(/\s+/) : [];
    const totalSteps = Math.max(
      originalWords.length,
      translationWords.length,
      1,
    );

    let step = 0;
    setSubtitles({ original: "", translation: "" });

    revealIntervalRef.current = setInterval(() => {
      step += 1;
      setSubtitles({
        original: originalWords.slice(0, step).join(" "),
        translation: translationWords.slice(0, step).join(" "),
      });

      if (step >= totalSteps) {
        clearInterval(revealIntervalRef.current);
        revealIntervalRef.current = null;

        if (isFinal) {
          const wordCount = Math.max(
            originalWords.length,
            translationWords.length,
          );
          const delay = MIN_CLEAR_MS + wordCount * CLEAR_MS_PER_WORD;
          subtitleTimeoutRef.current = setTimeout(() => {
            setSubtitles({ original: "", translation: "" });
          }, delay);
        }
      }
    }, WORD_REVEAL_MS);
  };

  const initLocalPipeline = () => {
    const videoElement = nativeVideoRef.current;
    if (videoElement && videoElement instanceof HTMLMediaElement) {
      setupLocalAudioCapture(videoElement);

      // Resume from where streaming was last stopped, not from the start
      if (resumeTimeRef.current > 0) {
        videoElement.currentTime = resumeTimeRef.current;
      }

      // Unmute and trigger actual playback loops now that connection is active
      videoElement.muted = false;
      videoElement.play().catch((err) => {
        console.log("Autoplay context interaction block encountered:", err);
      });
    }
  };

  const setupLocalAudioCapture = (videoElement) => {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      const audioCtx = new AudioContext();
      audioContextRef.current = audioCtx;

      const source = audioCtx.createMediaElementSource(videoElement);
      const destination = audioCtx.createMediaStreamDestination();

      source.connect(destination);
      source.connect(audioCtx.destination);

      const mediaRecorder = new MediaRecorder(destination.stream, {
        mimeType: "audio/webm",
      });
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = async (e) => {
        if (e.data.size > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
          const arrayBuffer = await e.data.arrayBuffer();

          // CRITICAL DYNAMIC RE-STRUCTURE:
          // Transform standard bytes into a numeric array wrapper with an active video clock anchor.
          const uint8Array = new Uint8Array(arrayBuffer);
          const binaryArray = Array.from(uint8Array);

          const payloadPacket = {
            timestamp: videoElement.currentTime || 0.0,
            audio: binaryArray,
          };

          wsRef.current.send(JSON.stringify(payloadPacket));
        }
      };

      // Slice the audio input tracks at continuous 1-second interval milestones
      mediaRecorder.start(1000);
      console.log("Pipeline processing attached.");
    } catch (err) {
      console.error("Audio routing error:", err);
    }
  };

  const triggerInternalPlayback = () => {
    if (videoData.isYouTube) {
      const internalPlayer = playerRef.current?.getInternalPlayer();
      if (internalPlayer && typeof internalPlayer.playVideo === "function") {
        // Resume from where streaming was last stopped, not from the start
        if (
          resumeTimeRef.current > 0 &&
          typeof internalPlayer.seekTo === "function"
        ) {
          internalPlayer.seekTo(resumeTimeRef.current, true);
        }
        internalPlayer.playVideo();
      }
    } else {
      if (nativeVideoRef.current) {
        nativeVideoRef.current
          .play()
          .catch((err) => console.log("Local playback deferred:", err));
      }
    }
  };

  const stopStreamingPipeline = () => {
    // Capture and pause at the current position so the next connect resumes here
    if (videoData.isYouTube) {
      const internalPlayer = playerRef.current?.getInternalPlayer();
      if (internalPlayer && typeof internalPlayer.pauseVideo === "function") {
        const currentTime = playerRef.current?.getCurrentTime?.();
        if (typeof currentTime === "number" && currentTime > 0) {
          resumeTimeRef.current = currentTime;
        }
        internalPlayer.pauseVideo();
      }
    } else if (nativeVideoRef.current) {
      resumeTimeRef.current = nativeVideoRef.current.currentTime || 0;
      nativeVideoRef.current.pause();
    }

    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state !== "inactive"
    ) {
      try {
        mediaRecorderRef.current.stop();
      } catch (e) {}
    }
    if (audioContextRef.current && audioContextRef.current.state !== "closed") {
      try {
        audioContextRef.current.close();
      } catch (e) {}
    }
    if (wsRef.current) {
      try {
        wsRef.current.close();
      } catch (e) {}
    }
    setConnectionStatus("DISCONNECTED");
    setSubtitles({ original: "", translation: "" });
    if (subtitleTimeoutRef.current) clearTimeout(subtitleTimeoutRef.current);
    if (revealIntervalRef.current) clearInterval(revealIntervalRef.current);
  };

  return (
    <div className={styles.workbenchWrapper}>
      <header className={styles.header}>
        <button onClick={onBack} className={styles.backBtn}>
          ⬅️ Exit
        </button>

        <div className={styles.controls}>
          <select
            value={targetLang}
            onChange={(e) => setTargetLang(e.target.value)}
            disabled={connectionStatus === "CONNECTED"}
            className={styles.langSelect}
          >
            {/* 1. Add the placeholder option here */}
            <option value="" disabled>
              Select language
            </option>

            {LANGUAGES.map((lang) => (
              <option key={lang.code} value={lang.code}>
                {lang.name}
              </option>
            ))}
          </select>

          {connectionStatus !== "CONNECTED" ? (
            <button
              onClick={startStreamingPipeline}
              className={styles.startBtn}
            >
              ⚡ Start
            </button>
          ) : (
            <button onClick={stopStreamingPipeline} className={styles.stopBtn}>
              🛑 Stop
            </button>
          )}
        </div>

        <span className={`${styles.statusBadge} ${styles[connectionStatus]}`}>
          {connectionStatus}
        </span>
      </header>

      <div className={styles.playerContainer}>
        {videoData.isYouTube ? (
          <ReactPlayer
            ref={playerRef}
            url={videoData.url}
            controls
            width="100%"
            height="100%"
            className={styles.videoPlayer}
            onPause={() => {
              isPausedRef.current = true;
              if (revealIntervalRef.current)
                clearInterval(revealIntervalRef.current);
              if (subtitleTimeoutRef.current)
                clearTimeout(subtitleTimeoutRef.current);
              setSubtitles({ original: "", translation: "" });
              if (wsRef.current?.readyState === WebSocket.OPEN) {
                wsRef.current.send(JSON.stringify({ control: "PAUSE" }));
              }
            }}
            onPlay={() => {
              isPausedRef.current = false;
              if (wsRef.current?.readyState === WebSocket.OPEN) {
                wsRef.current.send(JSON.stringify({ control: "RESUME" }));
              }
            }}
            config={{
              youtube: {
                playerVars: { autoplay: 0, modestbranding: 1, rel: 0 },
              },
            }}
          />
        ) : (
          <video
            ref={nativeVideoRef}
            src={videoData.url}
            controls
            crossOrigin="anonymous"
            width="100%"
            height="100%"
            className={styles.videoPlayer}
          />
        )}

        {(subtitles.original || subtitles.translation) && (
          <div className={styles.subtitleOverlay}>
            {subtitles.original && (
              <p className={styles.srcSub}>{subtitles.original}</p>
            )}
            {subtitles.translation && (
              <p className={styles.targetSub}>{subtitles.translation}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default StreamVideo;
