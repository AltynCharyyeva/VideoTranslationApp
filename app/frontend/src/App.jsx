import React, { useState, useEffect } from "react";
import VideoWorkbench from "./VideoWorkbench";
import Auth from "./Auth";
import AdminPanel from "./AdminPanel"; // Assuming you named the component this
import styles from "./style/App.module.css";

function App() {
  const [view, setView] = useState("landing"); // 'landing' | 'workbench' | 'login' | 'admin'
  const [videoData, setVideoData] = useState({
    file: null,
    url: null,
    isYouTube: false,
  });
  const [youtubeInput, setYoutubeInput] = useState("");
  const [token, setToken] = useState(localStorage.getItem("token"));
  const [user, setUser] = useState(null);
  const [initialAuthMode, setInitialAuthMode] = useState("login");

  // 1. Fetch user profile whenever the token changes
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
        .catch(() => {
          handleLogout();
        });
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

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    if (!checkAuth()) return;

    setVideoData({
      file: file,
      url: URL.createObjectURL(file),
      isYouTube: false,
    });
    setView("workbench");
  };

  const handleYoutubeSubmit = (e) => {
    e.preventDefault();
    if (!youtubeInput.trim()) return;
    if (!checkAuth()) return;

    setVideoData({
      file: null,
      url: youtubeInput,
      isYouTube: true,
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
            <>
              {/* Only show Admin button if user has admin role */}
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

      {/* --- VIEW TOGGLE --- */}

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

      {/* WORKBENCH VIEW */}
      {view === "workbench" && (
        <VideoWorkbench
          videoData={videoData}
          onBack={() => {
            setYoutubeInput("");
            setView("landing");
          }}
        />
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
