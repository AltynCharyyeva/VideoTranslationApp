import React, { useState, useEffect } from "react";
import styles from "./style/auth.module.css";

const Auth = ({ setToken, initialMode }) => {
  const [isLogin, setIsLogin] = useState(initialMode === "login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  // Update internal state if the prop changes
  useEffect(() => {
    setIsLogin(initialMode === "login");
  }, [initialMode]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");

    const endpoint = isLogin ? "/auth/login" : "/auth/register";

    try {
      const response = await fetch(`http://localhost:8000${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Authentication failed");
      }

      if (isLogin) {
        // FastAPI typically returns access_token
        localStorage.setItem("token", data.access_token);
        setToken(data.access_token);
      } else {
        alert("Registration successful! Please login.");
        setIsLogin(true);
        setPassword(""); // Clear password for security
      }
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className={styles.pageWrapper}>
      <div className={styles.authCard}>
        <div className={styles.header}>
          <span className={styles.icon}>🌐</span>
          <h2 className={styles.title}>
            {isLogin ? "Welcome Back" : "Create Account"}
          </h2>
          <p className={styles.subtitle}>
            {isLogin
              ? "Enter your credentials to access your videos"
              : "Join VideoTranslate and start breaking language barriers"}
          </p>
        </div>

        <form onSubmit={handleSubmit} className={styles.form}>
          <div className={styles.inputWrapper}>
            <label className={styles.label}>Email Address</label>
            <input
              type="email"
              placeholder="name@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={styles.input}
              required
            />
          </div>

          <div className={styles.inputWrapper}>
            <label className={styles.label}>Password</label>
            <input
              type="password"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={styles.input}
              required
            />
          </div>

          {error && <div className={styles.errorMessage}>⚠️ {error}</div>}

          <button type="submit" className={styles.button}>
            {isLogin ? "Sign In" : "Get Started"}
          </button>
        </form>

        <p className={styles.toggleText}>
          {isLogin ? "Don't have an account?" : "Already have an account?"}{" "}
          <span
            className={styles.toggleLink}
            onClick={() => {
              setIsLogin(!isLogin);
              setError("");
            }}
          >
            {isLogin ? "Register" : "Login"}
          </span>
        </p>
      </div>
    </div>
  );
};

export default Auth;
