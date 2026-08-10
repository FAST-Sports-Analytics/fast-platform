"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";

type InviteState = "ready" | "submitting" | "success" | "error" | "missing-token";

const DEFAULT_FAST_CLOUD_URL = "http://127.0.0.1:8766";

function normaliseApiBase(value: string) {
  return value.replace(/\/+$/, "");
}

export function AcceptInviteForm() {
  const [token, setToken] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [state, setState] = useState<InviteState>("ready");
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
      setMessage("This invitation link is incomplete. Ask your FAST administrator to resend the invitation.");
    }
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");

    if (!token) {
      setState("missing-token");
      setMessage("This invitation link is incomplete. Ask your FAST administrator to resend the invitation.");
      return;
    }
    if (newPassword.length < 10) {
      setState("error");
      setMessage("Your password must contain at least 10 characters.");
      return;
    }
    if (newPassword.length > 128) {
      setState("error");
      setMessage("Your password must contain no more than 128 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setState("error");
      setMessage("The passwords do not match.");
      return;
    }

    setState("submitting");
    try {
      const response = await fetch(`${apiBase}/api/v1/auth/accept-invitation`, {
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
        const detail = payload.detail || "The invitation could not be accepted.";
        if (/invalid|expired/i.test(detail)) {
          setMessage("This invitation is invalid, expired, or has already been used. Ask your FAST administrator to resend it.");
        } else if (/suspended|no longer available/i.test(detail)) {
          setMessage("This invitation is no longer available. Contact your FAST administrator.");
        } else {
          setMessage(detail);
        }
        setState("error");
        return;
      }

      setNewPassword("");
      setConfirmPassword("");
      setState("success");
      setMessage(payload.message || "Invitation accepted. You can now sign in to FAST Launcher.");
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
      <p className="eyebrow">Account activated</p>
      <h1>Welcome to FAST.</h1>
      <p>{message}</p>
      <div className="reset-actions">
        <Link className="button button-primary" href="/downloads">Open FAST downloads</Link>
        <Link className="button button-quiet" href="/">FAST Sports Analytics website</Link>
      </div>
      <small>You can close this tab and sign in to FAST Launcher using the email address that received this invitation.</small>
    </section>;
  }

  return <section className="reset-card" aria-live="polite">
    <p className="eyebrow">Secure invitation</p>
    <h1>Activate your FAST account</h1>
    <p>Create your password to accept the invitation and activate your FAST Sports Analytics account.</p>

    <form className="reset-form" onSubmit={submit}>
      <label>
        Create password
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
        Confirm password
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
      <div className="reset-password-guidance">Use at least 10 characters and a password you do not use elsewhere.</div>
      {message && <div className={state === "error" || state === "missing-token" ? "reset-message error" : "reset-message"}>{message}</div>}
      <button className="button button-primary reset-submit" type="submit" disabled={state === "submitting" || state === "missing-token"}>
        {state === "submitting" ? "Activating account…" : "Accept invitation"}
      </button>
    </form>

    <div className="reset-security-note">
      <strong>Single-use invitation</strong>
      <span>This invitation expires automatically and can only be used once. If it has expired, ask your FAST administrator to resend it.</span>
    </div>
  </section>;
}
