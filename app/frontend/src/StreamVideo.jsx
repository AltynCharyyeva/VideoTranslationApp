// StreamVideo.jsx
import React, { useState, useEffect, useRef } from "react";
import ReactPlayer from "react-player/youtube";
import styles from "./style/StreamVideo.module.css";

const LANGUAGES = [
  { code: "tuk_Latn", name: "Turkmen" },
  { code: "ron_Latn", name: "Romanian" },
  { code: "deu_Latn", name: "German" },
  { code: "tur_Latn", name: "Turkish" },
  { code: "rus_Cyrl", name: "Russian" },
  { code: "eng_Latn", name: "English" },
];

function StreamVideo({ videoData, token, onBack }) {
  const [targetLang, setTargetLang] = useState("ron_Latn");
  const [connectionStatus, setConnectionStatus] = useState("DISCONNECTED");
  const [subtitles, setSubtitles] = useState({ original: "", translation: "" });
  const [hasReceivedFirstSubtitle, setHasReceivedFirstSubtitle] =
    useState(false);

  const playerRef = useRef(null);
  const nativeVideoRef = useRef(null); // Dedicated ref for the native local player
  const wsRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioContextRef = useRef(null);

  // Timeout pointer to maintain readability when buffers clear
  const subtitleTimeoutRef = useRef(null);

  // Clean up streaming buffers when unmounting
  useEffect(() => {
    return () => {
      stopStreamingPipeline();
      if (subtitleTimeoutRef.current) clearTimeout(subtitleTimeoutRef.current);
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
    setHasReceivedFirstSubtitle(false);

    const isYouTube = videoData.isYouTube;
    const encodedSource = encodeURIComponent(videoData.url);

    const wsUrl = `ws://localhost:8000/streams/ws?target_lang=${targetLang}&is_youtube=${isYouTube}&source=${encodedSource}`;
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

      if (payload.status === "SUBTITLE" || payload.source_text !== undefined) {
        const data = payload.data || payload;

        if (subtitleTimeoutRef.current)
          clearTimeout(subtitleTimeoutRef.current);

        setSubtitles({
          original: data.source_text || "",
          translation: data.translated_text || "",
        });

        if (data.is_final) {
          subtitleTimeoutRef.current = setTimeout(() => {
            setSubtitles({ original: "", translation: "" });
          }, 3000);
        }

        setHasReceivedFirstSubtitle((alreadyReceived) => {
          // YouTube clips can stay paused until processing registers frames
          if (!alreadyReceived && videoData.isYouTube) {
            triggerInternalPlayback();
          }
          return true;
        });
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

  const initLocalPipeline = () => {
    const videoElement = nativeVideoRef.current;
    if (videoElement && videoElement instanceof HTMLMediaElement) {
      setupLocalAudioCapture(videoElement);

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
    setHasReceivedFirstSubtitle(false);
    setSubtitles({ original: "", translation: "" });
    if (subtitleTimeoutRef.current) clearTimeout(subtitleTimeoutRef.current);
  };

  return (
    <div className={styles.workbenchWrapper}>
      <header className={styles.header}>
        <button onClick={onBack} className={styles.backBtn}>
          ⬅️ Exit Stream
        </button>

        <div className={styles.controls}>
          <select
            value={targetLang}
            onChange={(e) => setTargetLang(e.target.value)}
            disabled={connectionStatus === "CONNECTED"}
            className={styles.langSelect}
          >
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
              ⚡ Connect & Stream
            </button>
          ) : (
            <button onClick={stopStreamingPipeline} className={styles.stopBtn}>
              🛑 Stop Stream
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
