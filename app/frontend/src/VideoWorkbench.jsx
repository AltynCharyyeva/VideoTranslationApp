import React, { useState, useEffect, useRef } from "react";
import ReactPlayer from "react-player/youtube";
import styles from "./style/VideoWorkbench.module.css";

const VideoWorkbench = ({ videoData, onBack }) => {
  const [status, setStatus] = useState("idle");
  const [targetLanguage, setTargetLanguage] = useState("tuk_Latn");
  const [subtitles, setSubtitles] = useState([]);
  const [translationId, setTranslationId] = useState(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [backendStatus, setBackendStatus] = useState("");
  const [progress, setProgress] = useState({ completed: 0, total: 0 });

  const activeLineRef = useRef(null);
  const playerRef = useRef(null);

  const languages = [
    { code: "tuk_Latn", name: "Turkmen" },
    { code: "ron_Latn", name: "Romanian" },
    { code: "deu_Latn", name: "German" },
    { code: "tur_Latn", name: "Turkish" },
    { code: "rus_Cyrl", name: "Russian" },
    { code: "eng_Latn", name: "English" },
  ];

  const STATUS_LABELS = {
    PENDING: "Initializing AI engine...",
    EXTRACTING_AUDIO: "Extracting audio track...",
    AUDIO_EXTRACTED: "Audio ready, preparing transcription...",
    TRANSCRIBING: "Speech-to-Text in progress...",
    TRANSLATING: "Translating...",
    COMPLETED: "Finishing up!",
    FAILED: "Processing failed.",
  };

  const formatTime = (seconds) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins}:${secs.toString().padStart(2, "0")}`;
  };

  const timeToSeconds = (timeStr) => {
    const [hms, ms] = timeStr.replace(",", ".").split(".");
    const [h, m, s] = hms.split(":").map(Number);
    return h * 3600 + m * 60 + s + Number(ms || 0) / 1000;
  };

  const parseSRT = (srtString) => {
    if (!srtString) return [];
    const normalized = srtString.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    const segments = normalized.trim().split(/\n\s*\n/);

    return segments
      .map((segment) => {
        const lines = segment.trim().split("\n");
        if (lines.length < 3) return null;
        const timeMatch = lines[1].match(
          /(\d+:\d+:\d+,\d+) --> (\d+:\d+:\d+,\d+)/,
        );
        if (!timeMatch) return null;
        return {
          id: lines[0],
          start: timeToSeconds(timeMatch[1]),
          end: timeToSeconds(timeMatch[2]),
          text: lines
            .slice(2)
            .join(" ")
            .replace(/^\[\d+\.\d+\]\s*/, ""),
        };
      })
      .filter((s) => s !== null);
  };

  const startWorkflow = async () => {
    setStatus("uploading");
    const token = localStorage.getItem("token");

    try {
      const formData = new FormData();
      formData.append("target_language", targetLanguage);

      if (videoData.isYouTube) {
        formData.append("youtube_url", videoData.url);
      } else {
        formData.append("file", videoData.file);
      }

      const response = await fetch("http://localhost:8000/videos/translate", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "Upload failed");
      }

      const data = await response.json();
      setTranslationId(data.translation_id);
      setStatus("processing");
    } catch (err) {
      console.error("Workflow error:", err);
      alert(`Error: ${err.message}`);
      onBack();
    }
  };

  const loadedChunks = useRef(new Set());
  useEffect(() => {
    let pollInterval;
    if ((status === "processing" || status === "partial") && translationId) {
      const token = localStorage.getItem("token");

      pollInterval = setInterval(async () => {
        try {
          const res = await fetch(
            `http://localhost:8000/videos/${translationId}`,
            {
              headers: { Authorization: `Bearer ${token}` },
            },
          );
          const data = await res.json();

          setBackendStatus(data.status);
          console.log("[POLL] raw data:", data);

          if (data.chunks?.length > 0) {
            const newChunks = data.chunks.filter(
              (c) => !loadedChunks.current.has(c.chunk_index),
            );
            console.log(
              "[CHUNKS] total:",
              data.chunks.length,
              "new:",
              newChunks.length,
              "loaded set:",
              [...loadedChunks.current],
            );
            if (newChunks.length > 0) {
              newChunks.forEach((c) => loadedChunks.current.add(c.chunk_index));
              setStatus((s) => (s === "processing" ? "partial" : s));
              setSubtitles((prev) => {
                const incoming = newChunks.flatMap((c) =>
                  parseSRT(c.srt_content),
                );
                return [...prev, ...incoming].sort((a, b) => a.start - b.start);
              });
            }
          }

          if (data.status === "COMPLETED") {
            setStatus("ready");
            clearInterval(pollInterval);
          } else if (data.status === "FAILED") {
            alert("AI Processing failed.");
            onBack();
            clearInterval(pollInterval);
          }

          if (data.total_chunks > 0) {
            setProgress({
              completed: data.completed_chunks,
              total: data.total_chunks,
            });
          }
        } catch (e) {
          console.error("Polling error", e);
        }
      }, 3000);
    }
    return () => clearInterval(pollInterval);
  }, [status, translationId, onBack]);

  useEffect(() => {
    if (activeLineRef.current) {
      activeLineRef.current.scrollIntoView({
        behavior: "smooth",
        block: "center",
      });
    }
  }, [currentTime]);

  const seekTo = (seconds) => {
    if (videoData.isYouTube) {
      playerRef.current?.seekTo(seconds, "seconds");
    } else {
      if (playerRef.current) playerRef.current.currentTime = seconds;
    }
  };

  const renderPlayer = () => {
    if (videoData.isYouTube) {
      return (
        <ReactPlayer
          ref={playerRef}
          url={videoData.url}
          controls
          onProgress={(state) => setCurrentTime(state.playedSeconds)}
          className={styles.mainVideo}
        />
      );
    }
    return (
      <video
        ref={playerRef}
        src={videoData.url}
        controls
        className={styles.mainVideo}
        onTimeUpdate={() => setCurrentTime(playerRef.current?.currentTime || 0)}
      />
    );
  };

  if (status === "idle") {
    return (
      <div className={styles.loaderContainer}>
        <h2>Configure Translation</h2>
        <div className={styles.languageSelectWrapper}>
          <label className={styles.languageSelectLabel}>Target Language:</label>
          <select
            value={targetLanguage}
            onChange={(e) => setTargetLanguage(e.target.value)}
            className={styles.languageSelect}
          >
            {languages.map((lang) => (
              <option key={lang.code} value={lang.code}>
                {lang.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <button onClick={startWorkflow} className={styles.actionBtn}>
            Start translation
          </button>
          <button onClick={onBack} className={styles.cancelBtn}>
            Cancel
          </button>
        </div>
      </div>
    );
  }

  if (status === "uploading") {
    return (
      <div className={styles.loaderContainer}>
        <div className={styles.spinner}></div>
        <h2>Uploading Video...</h2>
      </div>
    );
  }

  if (status === "processing") {
    return (
      <div className={styles.loaderContainer}>
        <div className={styles.spinner}></div>
        <h2>Processing Content</h2>
        <div className={styles.statusBox}>
          <p className={styles.statusText}>
            {STATUS_LABELS[backendStatus] || "Initializing AI engines..."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.workbench}>
      <button onClick={onBack} className={styles.backBtn}>
        &larr; Back
      </button>

      {status === "partial" && (
        <div className={styles.progressBanner}>
          Processing chunks: {progress.completed} / {progress.total} complete
          <div className={styles.progressBar}>
            <div
              className={styles.progressFill}
              style={{
                width: `${progress.total ? (progress.completed / progress.total) * 100 : 0}%`,
              }}
            />
          </div>
        </div>
      )}

      <div className={styles.workspaceLayout}>
        <div className={styles.videoSection}>
          <div className={styles.videoContainer}>{renderPlayer()}</div>
        </div>

        <div className={styles.transcriptSection}>
          <h3 className={styles.transcriptTitle}>Translation</h3>
          <div className={styles.transcriptList}>
            {subtitles.map((sub, index) => {
              const isActive =
                currentTime >= sub.start && currentTime <= sub.end;
              return (
                <div
                  key={index}
                  ref={isActive ? activeLineRef : null}
                  className={`${styles.transcriptLine} ${isActive ? styles.activeLine : ""}`}
                  onClick={() => seekTo(sub.start)}
                >
                  <span className={styles.timestamp}>
                    {formatTime(sub.start)}
                  </span>
                  <p className={styles.transcriptText}>{sub.text}</p>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
};

export default VideoWorkbench;
