"use client";

import Image from "next/image";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

function apiBase() {
  return (process.env.NEXT_PUBLIC_FAST_CLOUD_URL || "http://127.0.0.1:8766").replace(/\/+$/, "");
}

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (window.sessionStorage.getItem("fast_access_token")) {
      router.replace("/account");
    }
  }, [router]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setMessage("");
    try {
      const response = await fetch(`${apiBase()}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "FAST Cloud could not sign you in.");
      if (!data.access_token) throw new Error("FAST Cloud did not return an access token.");

      window.sessionStorage.setItem("fast_access_token", data.access_token);
      window.sessionStorage.setItem("fast_refresh_token", data.refresh_token || "");
      window.sessionStorage.setItem("fast_user", JSON.stringify(data.user || {}));
      router.replace("/account");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "FAST Cloud could not sign you in.");
      setSubmitting(false);
    }
  }

  return <main className="auth-page">
    <Link href="/" className="auth-brand"><Image src="/branding/fast-logo.png" alt="FAST Sports Analytics" width={420} height={142}/></Link>
    <section className="auth-card">
      <p className="eyebrow">FAST Cloud</p>
      <h1>Log in</h1>
      <p>Manage your FAST organisation, subscription and billing securely.</p>
      <form className="auth-form" onSubmit={submit}>
        <label>Email address<input type="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" placeholder="you@club.com" required/></label>
        <label>Password<input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" placeholder="••••••••" required/></label>
        {message && <p className="auth-error">{message}</p>}
        <button className="button button-primary" type="submit" disabled={submitting}>{submitting ? "Signing in…" : "Log in"}</button>
      </form>
      <small>Organisation administrators can manage their FAST plan and billing here. Product access remains controlled by your organisation licence.</small>
      <Link href="/reset-password">Forgot your password? →</Link>
    </section>
    <Link className="back-link" href="/">← Back to website</Link>
  </main>;
}
