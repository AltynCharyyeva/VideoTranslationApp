import React, { useEffect, useState } from "react";
import styles from "./style/Translations.module.css";
import { getLanguageNameByNLLB, getLanguageNameByWhisper } from "./constants/languages";

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

  const downloadSRT = async (translationId, filename) => {
    try {
      const response = await fetch(
        `http://localhost:8000/videos/${translationId}/download/srt`,
        { headers: { Authorization: `Bearer ${token}` } },
      );
      if (!response.ok) throw new Error("Download failed");

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      const safeName = filename.replace(/[^a-zA-Z0-9 _-]/g, "").trim().slice(0, 60) || "subtitles";
      a.href = url;
      a.download = `${safeName}.srt`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
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
                <span className={styles.languages}>
                  {t.source_language
                    ? getLanguageNameByWhisper(t.source_language)
                    : "Detecting..."}{" "}
                  &rarr;{" "}
                  {t.target_language
                    ? getLanguageNameByNLLB(t.target_language)
                    : "—"}
                </span>
                <div
                  className={`${styles.status} ${styles[t.status.toLowerCase()]}`}
                >
                  {t.status}
                </div>
              </div>

              {t.status === "COMPLETED" && t.srt_path && (
                <button
                  onClick={() => downloadSRT(t.id, t.filename)}
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
