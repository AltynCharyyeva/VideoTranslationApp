import React, { useState } from "react";
import VideoWorkbench from "./VideoWorkbench";
import Auth from "./Auth";
import styles from "./style/App.module.css";

function App() {
  const [view, setView] = useState("landing"); // 'landing' | 'workbench' | 'login'
  const [videoData, setVideoData] = useState({ file: null, url: null });
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [initialAuthMode, setInitialAuthMode] = useState("login");

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;

    // Check if user is logged in before allowing upload
    if (!token) {
      setInitialAuthMode("login");
      setView("login");
      return;
    }

    setVideoData({
      file: file,
      url: URL.createObjectURL(file),
    });

    setView("workbench");
  };

  const handleNavToAuth = (mode) => {
    setInitialAuthMode(mode);
    setView("login");
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
            <button
              className={styles.loginBtn}
              onClick={() => {
                localStorage.removeItem("token");
                setToken(null);
                setView("landing");
              }}
            >
              Logout
            </button>
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

      {/* --- VIEW TOGGLE --- */}
      {view === "landing" && (
        <main className={styles.hero}>
          <h1 className={styles.appName}>
            Video<span>TRANSLATE</span>
          </h1>
          <p className={styles.tagline}>
            Breaking language barriers with AI-powered translation.
          </p>

          <div className={styles.uploadContainer}>
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

      {view === "workbench" && (
        <VideoWorkbench
          videoData={videoData}
          onBack={() => setView("landing")}
        />
      )}

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
