import React, { useState, useEffect, useRef } from "react";
import ReactPlayer from "react-player/youtube";
import styles from "./style/App.module.css";

const VideoWorkbench = ({ videoData, onBack }) => {
  // States: 'idle', 'uploading', 'processing', 'ready'
  const [status, setStatus] = useState("idle");
  const [targetLanguage, setTargetLanguage] = useState("tuk_Latn");
  const [subtitles, setSubtitles] = useState([]);
  const [translationId, setTranslationId] = useState(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [backendStatus, setBackendStatus] = useState("");

  const activeLineRef = useRef(null);
  const playerRef = useRef(null); // Ref for both ReactPlayer and HTML5 Video

  const languages = [
    { code: "tuk_Latn", name: "Turkmen" },
    { code: "ron_Latn", name: "Romanian" },
    { code: "deu_Latn", name: "German" },
    { code: "tur_Latn", name: "Turkish" },
    { code: "rus_Cyrl", name: "Russian" },
    { code: "eng_Latn", name: "English" },
  ];

  const STATUS_LABELS = {
    EXTRACTING_AUDIO: "Extracting audio track...",
    TRANSCRIBING: "Speech-to-Text in progress...",
    TRANSLATING: "Translating transcript...",
    GENERATING_VOICE: "Generating AI voiceover...",
    MIXING_VIDEO: "Syncing audio and video...",
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

  // Update the Polling useEffect
  useEffect(() => {
    let pollInterval;
    if (status === "processing" && translationId) {
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

          // Capture the specific status from your backend
          setBackendStatus(data.status);

          if (data.status === "COMPLETED") {
            setSubtitles(parseSRT(data.srt_content));
            setStatus("ready");
            clearInterval(pollInterval);
          } else if (data.status === "FAILED") {
            alert("AI Processing failed.");
            onBack();
            clearInterval(pollInterval);
          }
        } catch (e) {
          console.error("Polling error", e);
        }
      }, 3000);
    }
    return () => clearInterval(pollInterval);
  }, [status, translationId, onBack]);

  // Auto-scroll Transcript
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
          width="100%"
          height="100%"
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

  // --- RENDER STATES ---

  if (status === "idle") {
    return (
      <div className={styles.loaderContainer}>
        <h2>Configure Translation</h2>
        <div style={{ margin: "20px 0" }}>
          <label style={{ display: "block", marginBottom: "10px" }}>
            Target Language:
          </label>
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
        <button onClick={startWorkflow} className={styles.loginBtn}>
          Start translation
        </button>
        <button
          onClick={onBack}
          className={styles.registerBtn}
          style={{ marginLeft: "10px" }}
        >
          Cancel
        </button>
      </div>
    );
  }

  if (status === "uploading" || status === "processing") {
    return (
      <div className={styles.loaderContainer}>
        <div className={styles.spinner}></div>
        <h2>
          {status === "uploading" ? "Uploading Video..." : "Processing Content"}
        </h2>

        {/* Dynamic Status Display */}
        <div className={styles.statusBox}>
          <p className={styles.statusText}>
            {STATUS_LABELS[backendStatus] || "Initializing AI engine..."}
          </p>
          <div className={styles.progressBar}>
            <div
              className={styles.progressFill}
              style={{
                width: backendStatus === "MIXING_VIDEO" ? "80%" : "40%",
              }}
            ></div>
          </div>
        </div>

        <p className={styles.langNote}>
          Target: {languages.find((l) => l.code === targetLanguage)?.name}
        </p>
      </div>
    );
  }

  return (
    <div className={styles.workbench}>
      <button onClick={onBack} className={styles.backBtn}>
        ← Back
      </button>
      <div className={styles.workspaceLayout}>
        <div className={styles.videoSection}>
          <div className={styles.videoContainer}>
            {renderPlayer()}
            <div className={styles.subtitleOverlay}>
              {
                subtitles.find(
                  (s) => currentTime >= s.start && currentTime <= s.end,
                )?.text
              }
            </div>
          </div>
        </div>

        <div className={styles.transcriptSection}>
          <h3 className={styles.transcriptTitle}>Transcript</h3>
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
