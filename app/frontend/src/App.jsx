import React, { useState, useEffect } from "react";
import VideoWorkbench from "./VideoWorkbench";
import StreamVideo from "./StreamVideo";
import Auth from "./Auth";
import AdminPanel from "./AdminPanel";
import styles from "./style/App.module.css";

function App() {
  const [view, setView] = useState("landing"); // 'landing' | 'modeSelect' | 'workbench' | 'stream' | 'login' | 'admin'
  const [videoData, setVideoData] = useState({
    file: null,
    url: null,
    isYouTube: false,
  });
  const [youtubeInput, setYoutubeInput] = useState("");
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [user, setUser] = useState(null);
  const [initialAuthMode, setInitialAuthMode] = useState("login");

  useEffect(() => {
    if (token) {
      fetch("http://localhost:8000/users/me", {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then((res) => {
          if (!res.ok) throw new Error("Unauthorized");
          return res.json();
        })
        .then((data) => setUser(data))
        .catch(() => handleLogout());
    } else {
      setUser(null);
    }
  }, [token]);

  const checkAuth = () => {
    if (!token) {
      setInitialAuthMode("login");
      setView("login");
      return false;
    }
    return true;
  };

  const handleLogout = () => {
    localStorage.removeItem("token");
    setToken(null);
    setUser(null);
    setView("landing");
  };

  // Instead of going straight to workbench, stop at mode selection
  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (!checkAuth()) return;

    setVideoData({ file, url: URL.createObjectURL(file), isYouTube: false });
    setView("modeSelect");
  };

  const handleYoutubeSubmit = (e) => {
    e.preventDefault();
    if (!youtubeInput.trim()) return;
    if (!checkAuth()) return;

    setVideoData({ file: null, url: youtubeInput, isYouTube: true });
    setView("modeSelect");
  };

  const handleNavToAuth = (mode) => {
    setInitialAuthMode(mode);
    setView("login");
  };

  const handleBack = () => {
    setYoutubeInput("");
    setVideoData({ file: null, url: null, isYouTube: false });
    setView("landing");
  };

  return (
    <div className={styles.pageWrapper}>
      {/* --- TOP NAVBAR --- */}
      <nav className={styles.navbar}>
        <div
          className={styles.logoSection}
          onClick={() => setView("landing")}
          style={{ cursor: "pointer" }}
        >
          <span className={styles.logoIcon}>🌐</span>
          <span className={styles.logoText}>VideoTranslate</span>
        </div>

        <div className={styles.navActions}>
          {token ? (
            <>
              {user?.role === "admin" && (
                <button
                  className={styles.adminBtn}
                  onClick={() => setView("admin")}
                >
                  ⚙️ Manage Users
                </button>
              )}
              <button className={styles.loginBtn} onClick={handleLogout}>
                Logout
              </button>
            </>
          ) : (
            <>
              <button
                className={styles.loginBtn}
                onClick={() => handleNavToAuth("login")}
              >
                Login
              </button>
              <button
                className={styles.registerBtn}
                onClick={() => handleNavToAuth("register")}
              >
                Register
              </button>
            </>
          )}
        </div>
      </nav>

      {/* LANDING VIEW */}
      {view === "landing" && (
        <main className={styles.hero}>
          <h1 className={styles.appName}>
            Video<span>TRANSLATE</span>
          </h1>
          <p className={styles.tagline}>
            Breaking language barriers with AI-powered translation.
          </p>

          <div className={styles.uploadContainer}>
            <form onSubmit={handleYoutubeSubmit} className={styles.youtubeForm}>
              <input
                type="text"
                placeholder="Paste YouTube URL here..."
                value={youtubeInput}
                onChange={(e) => setYoutubeInput(e.target.value)}
                className={styles.urlInput}
              />
              <button type="submit" className={styles.urlSubmitBtn}>
                Go
              </button>
            </form>

            <div className={styles.divider}>
              <span>OR</span>
            </div>

            <label htmlFor="video-upload" className={styles.uploadCard}>
              <div className={styles.uploadIcon}>📤</div>
              <h3>Click to upload video</h3>
              <p>SRT will be generated automatically</p>
              <input
                type="file"
                id="video-upload"
                onChange={handleFileUpload}
                accept="video/*"
                hidden
              />
            </label>
          </div>
        </main>
      )}

      {/* MODE SELECTION VIEW — shown after a file/URL is chosen */}
      {view === "modeSelect" && (
        <main className={styles.hero}>
          <h2 className={styles.appName} style={{ fontSize: "2rem" }}>
            Choose Translation Mode
          </h2>
          <p className={styles.tagline}>
            {videoData.isYouTube ? videoData.url : videoData.file?.name}
          </p>

          <div className={styles.uploadContainer} style={{ gap: "1.5rem" }}>
            {/* Real-time streaming mode */}
            <div
              className={styles.uploadCard}
              onClick={() => setView("stream")}
              style={{ cursor: "pointer" }}
            >
              <div className={styles.uploadIcon}>⚡</div>
              <h3>Live Stream</h3>
              <p>Subtitles appear in real time as the video plays</p>
            </div>

            {/* Full video translation mode */}
            <div
              className={styles.uploadCard}
              onClick={() => setView("workbench")}
              style={{ cursor: "pointer" }}
            >
              <div className={styles.uploadIcon}>🎬</div>
              <h3>Full Translation</h3>
              <p>Process the entire video first, then watch with subtitles</p>
            </div>

            <button onClick={handleBack} className={styles.loginBtn}>
              ← Cancel
            </button>
          </div>
        </main>
      )}

      {/* STREAM VIEW */}
      {view === "stream" && (
        <StreamVideo videoData={videoData} token={token} onBack={handleBack} />
      )}

      {/* WORKBENCH VIEW */}
      {view === "workbench" && (
        <VideoWorkbench videoData={videoData} onBack={handleBack} />
      )}

      {/* ADMIN VIEW */}
      {view === "admin" && (
        <AdminPanel token={token} onBack={() => setView("landing")} />
      )}

      {/* AUTH VIEW */}
      {view === "login" && (
        <Auth
          initialMode={initialAuthMode}
          setToken={(t) => {
            setToken(t);
            setView("landing");
          }}
        />
      )}
    </div>
  );
}

export default App;
