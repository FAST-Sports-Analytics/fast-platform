"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

type ResetState = "ready" | "submitting" | "success" | "error" | "missing-token";

const DEFAULT_FAST_CLOUD_URL = "http://127.0.0.1:8766";

function normaliseApiBase(value: string) {
  return value.replace(/\/+$/, "");
}

export function ResetPasswordForm() {
  const [token, setToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [state, setState] = useState<ResetState>("ready");
  const [message, setMessage] = useState("");

  const apiBase = useMemo(
    () => normaliseApiBase(process.env.NEXT_PUBLIC_FAST_CLOUD_URL || DEFAULT_FAST_CLOUD_URL),
    [],
  );

  useEffect(() => {
    const urlToken = new URLSearchParams(window.location.search).get("token")?.trim() || "";
    setToken(urlToken);
    if (!urlToken) {
      setState("missing-token");
      setMessage("This password reset link is incomplete. Request a new password reset from FAST Launcher.");
    }
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");

    if (!token) {
      setState("missing-token");
      setMessage("This password reset link is incomplete. Request a new password reset from FAST Launcher.");
      return;
    }
    if (newPassword.length < 10) {
      setState("error");
      setMessage("Your new password must contain at least 10 characters.");
      return;
    }
    if (newPassword.length > 128) {
      setState("error");
      setMessage("Your new password must contain no more than 128 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setState("error");
      setMessage("The passwords do not match.");
      return;
    }

    setState("submitting");
    try {
      const response = await fetch(`${apiBase}/api/v1/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, new_password: newPassword }),
      });

      let payload: { message?: string; detail?: string } = {};
      try {
        payload = await response.json();
      } catch {
        payload = {};
      }

      if (!response.ok) {
        const detail = payload.detail || "The password reset could not be completed.";
        if (/invalid|expired/i.test(detail)) {
          setMessage("This password reset link is invalid, expired, or has already been used. Request a new reset from FAST Launcher.");
        } else if (/suspended/i.test(detail)) {
          setMessage("This FAST account is suspended. Contact your administrator for assistance.");
        } else {
          setMessage(detail);
        }
        setState("error");
        return;
      }

      setNewPassword("");
      setConfirmPassword("");
      setState("success");
      setMessage(payload.message || "Password reset complete. You can now sign in to FAST Launcher.");
    } catch {
      setState("error");
      setMessage(
        "FAST Cloud could not be reached. If you are testing locally, make sure FAST Cloud is running on this computer, then try again.",
      );
    }
  }

  if (state === "success") {
    return <section className="reset-card reset-success" aria-live="polite">
      <div className="reset-status-icon">✓</div>
      <p className="eyebrow">Password updated</p>
      <h1>Your FAST password has been reset.</h1>
      <p>{message}</p>
      <div className="reset-actions">
        <Link className="button button-primary" href="/downloads">Return to FAST Launcher</Link>
        <Link className="button button-quiet" href="/">FAST Sports Analytics website</Link>
      </div>
      <small>You can close this browser tab and sign in to FAST Launcher with your new password.</small>
    </section>;
  }

  return <section className="reset-card" aria-live="polite">
    <p className="eyebrow">Account security</p>
    <h1>Reset your FAST password</h1>
    <p>Choose a new password for your FAST Sports Analytics account. This secure link can only be used once.</p>

    <form className="reset-form" onSubmit={submit}>
      <label>
        New password
        <input
          type="password"
          autoComplete="new-password"
          minLength={10}
          maxLength={128}
          value={newPassword}
          onChange={(event) => setNewPassword(event.target.value)}
          disabled={state === "submitting" || state === "missing-token"}
          required
        />
      </label>
      <label>
        Confirm new password
        <input
          type="password"
          autoComplete="new-password"
          minLength={10}
          maxLength={128}
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          disabled={state === "submitting" || state === "missing-token"}
          required
        />
      </label>
      <div className="reset-password-guidance">Use at least 10 characters. Avoid reusing a password from another account.</div>
      {message && <div className={state === "error" || state === "missing-token" ? "reset-message error" : "reset-message"}>{message}</div>}
      <button className="button button-primary reset-submit" type="submit" disabled={state === "submitting" || state === "missing-token"}>
        {state === "submitting" ? "Resetting password…" : "Reset password"}
      </button>
    </form>

    <div className="reset-security-note">
      <strong>Secure recovery link</strong>
      <span>If this link has expired or has already been used, request another reset from the FAST Launcher sign-in screen.</span>
    </div>
  </section>;
}
