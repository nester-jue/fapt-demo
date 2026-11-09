import React, { useState } from "react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8001";

function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState("login");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    confirmPassword: "",
    role: "investor",
  });

  function handleChange(event) {
    setForm({
      ...form,
      [event.target.name]: event.target.value,
    });
  }

  async function handleSubmit(event) {
    event.preventDefault();

    setError("");
    setSuccess("");

    if (mode === "register" && form.password !== form.confirmPassword) {
      setError("Your passwords do not match.");
      return;
    }

    setLoading(true);

    try {
      if (mode === "register") {
        const response = await fetch(`${API_URL}/auth/register`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            full_name: form.full_name,
            email: form.email,
            password: form.password,
            role: form.role,
          }),
        });

        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.detail || "Registration failed.");
        }

        setSuccess("Account created successfully. You can now log in.");

        setForm({
          full_name: "",
          email: form.email,
          password: "",
          confirmPassword: "",
          role: "investor",
        });

        setMode("login");
      } else {
        const response = await fetch(`${API_URL}/auth/login`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            email: form.email,
            password: form.password,
          }),
        });

        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.detail || "Login failed.");
        }

        const profileResponse = await fetch(`${API_URL}/auth/me`, {
          headers: {
            Authorization: `Bearer ${data.access_token}`,
          },
        });

        const profile = await profileResponse.json();

        if (!profileResponse.ok) {
          throw new Error("Unable to retrieve your account details.");
        }

        const storage = rememberMe ? localStorage : sessionStorage;

        storage.setItem("nexa_token", data.access_token);
        storage.setItem("nexa_user", JSON.stringify(profile));

        onAuthenticated(profile, data.access_token);
      }
    } catch (err) {
      setError(err.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-background-glow"></div>

      <div className="auth-card">
        <div className="auth-brand">
          <div className="auth-brand-icon">N</div>

          <div>
            <h1>NEXA</h1>
            <span>ASSET TOKENISATION PLATFORM</span>
          </div>
        </div>

        <div className="auth-heading">
          <p className="auth-eyebrow">DIGITAL ASSET INFRASTRUCTURE</p>

          <h2>
            {mode === "login"
              ? "Welcome back."
              : "Create your account."}
          </h2>

          <p>
            {mode === "login"
              ? "Sign in to access your NEXA workspace."
              : "Register to access the NEXA platform."}
          </p>
        </div>

        <div className="auth-tabs">
          <button
            type="button"
            className={mode === "login" ? "auth-tab active" : "auth-tab"}
            onClick={() => {
              setMode("login");
              setError("");
              setSuccess("");
            }}
          >
            Sign In
          </button>

          <button
            type="button"
            className={mode === "register" ? "auth-tab active" : "auth-tab"}
            onClick={() => {
              setMode("register");
              setError("");
              setSuccess("");
            }}
          >
            Register
          </button>
        </div>

        {error && <div className="auth-alert error">{error}</div>}

        {success && (
          <div className="auth-alert success">{success}</div>
        )}

        <form onSubmit={handleSubmit}>
          {mode === "register" && (
            <div className="auth-field">
              <label>FULL NAME</label>

              <input
                type="text"
                name="full_name"
                placeholder="Enter your full name"
                value={form.full_name}
                onChange={handleChange}
                minLength={2}
                maxLength={150}
                required
              />
            </div>
          )}

          {mode === "register" && (
            <div className="auth-field">
              <label>ACCOUNT TYPE</label>
              <select name="role" value={form.role} onChange={handleChange}>
                <option value="investor">Investor</option>
                <option value="property_owner">Property Owner</option>
              </select>
            </div>
          )}

          <div className="auth-field">
            <label>EMAIL ADDRESS</label>

            <input
              type="email"
              name="email"
              placeholder="you@example.com"
              value={form.email}
              onChange={handleChange}
              required
            />
          </div>

          <div className="auth-field">
            <label>PASSWORD</label>

            <div className="password-wrapper">
              <input
                type={showPassword ? "text" : "password"}
                name="password"
                placeholder="Enter your password"
                value={form.password}
                onChange={handleChange}
                minLength={mode === "register" ? 8 : undefined}
                maxLength={128}
                required
              />

              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? "Hide" : "Show"}
              </button>
            </div>
          </div>

          {mode === "register" && (
            <div className="auth-field">
              <label>CONFIRM PASSWORD</label>

              <input
                type={showPassword ? "text" : "password"}
                name="confirmPassword"
                placeholder="Confirm your password"
                value={form.confirmPassword}
                onChange={handleChange}
                required
              />
            </div>
          )}

          {mode === "login" && (
            <div className="auth-options">
              <label className="remember-option">
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(event) =>
                    setRememberMe(event.target.checked)
                  }
                />
                Remember me
              </label>

              <span className="forgot-password">
                Forgot password?
              </span>
            </div>
          )}

          <button
            type="submit"
            className="auth-submit"
            disabled={loading}
          >
            {loading
              ? "Please wait..."
              : mode === "login"
              ? "Sign In to NEXA"
              : "Create Account"}
          </button>
        </form>

        <div className="auth-divider">
          <span>SECURE PLATFORM ACCESS</span>
        </div>

        <div className="auth-security">
          <span className="security-dot"></span>
          Protected authentication
        </div>

        <footer className="auth-footer">
          NEXA TOKENISATION PLATFORM · DEMONSTRATION BUILD
        </footer>
      </div>
    </div>
  );
}

export default AuthScreen;