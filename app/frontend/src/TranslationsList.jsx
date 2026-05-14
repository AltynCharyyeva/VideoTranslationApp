import React, { useEffect, useState } from "react";
import styles from "./style/Translations.module.css";

const TranslationsList = ({ token, onBack }) => {
  const [translations, setTranslations] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("http://localhost:8000/users/me", {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((res) => res.json())
      .then((data) => {
        setTranslations(data.translations || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [token]);

  const downloadSRT = async (srtPath, filename) => {
    try {
      // In a real app, srtPath is the URL to the file on your server
      const response = await fetch(`http://localhost:8000/${srtPath}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${filename.split(".")[0]}.srt`;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (err) {
      alert("Error downloading file");
    }
  };

  if (loading)
    return <div className={styles.loader}>Loading your translations...</div>;

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <button onClick={onBack} className={styles.backBtn}>
          ← Back
        </button>
        <h2>My Translations</h2>
      </div>

      {translations.length === 0 ? (
        <div className={styles.emptyState}>
          <p>You haven't translated any videos yet.</p>
        </div>
      ) : (
        <div className={styles.grid}>
          {translations.map((t) => (
            <div key={t.id} className={styles.card}>
              <div className={styles.cardInfo}>
                <h3>{t.filename}</h3>
                <span className={styles.date}>
                  {new Date(t.created_at).toLocaleDateString()}
                </span>
                <div
                  className={`${styles.status} ${styles[t.status.toLowerCase()]}`}
                >
                  {t.status}
                </div>
              </div>

              {t.status === "COMPLETED" && t.srt_path && (
                <button
                  onClick={() => downloadSRT(t.srt_path, t.filename)}
                  className={styles.downloadBtn}
                >
                  Download .SRT
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default TranslationsList;
