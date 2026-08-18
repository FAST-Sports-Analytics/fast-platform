"use client";

import Image from "next/image";
import Link from "next/link";
import { FormEvent, useState } from "react";

function apiBase() {
  return (process.env.NEXT_PUBLIC_FAST_CLOUD_URL || "http://127.0.0.1:8766").replace(/\/+$/, "");
}

export default function Signup() {
  const [form, setForm] = useState({ full_name: "", email: "", organisation_name: "", country: "United Kingdom", password: "", confirm: "", accept_terms: false });
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [complete, setComplete] = useState(false);
  const set = (key: string, value: string | boolean) => setForm(current => ({ ...current, [key]: value }));

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    if (form.password !== form.confirm) return setMessage("Passwords do not match.");
    setSubmitting(true);
    try {
      const response = await fetch(`${apiBase()}/api/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          full_name: form.full_name, email: form.email, organisation_name: form.organisation_name,
          country: form.country, password: form.password, accept_terms: form.accept_terms,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "FAST could not create your account.");
      setComplete(true);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "FAST could not create your account.");
    } finally { setSubmitting(false); }
  }

  return <main className="auth-page">
    <Link href="/" className="auth-brand"><Image src="/branding/fast-logo.png" alt="FAST Sports Analytics" width={420} height={142}/></Link>
    <section className="auth-card auth-card-wide">
      <p className="eyebrow">Get started</p>
      {complete ? <>
        <h1>Check your email.</h1>
        <p>We've sent a verification link to <strong>{form.email}</strong>. Verify your address, then sign in to choose your FAST plan.</p>
        <Link className="button button-primary" href="/login">Go to sign in</Link>
      </> : <>
        <h1>Create your FAST account.</h1>
        <p>Create the administrator account for your organisation. You'll choose and pay for your FAST plan after email verification.</p>
        <form className="auth-form" onSubmit={submit}>
          <label>Your name<input value={form.full_name} onChange={e=>set("full_name",e.target.value)} autoComplete="name" required/></label>
          <label>Work email<input type="email" value={form.email} onChange={e=>set("email",e.target.value)} autoComplete="email" required/></label>
          <label>Organisation / club<input value={form.organisation_name} onChange={e=>set("organisation_name",e.target.value)} required/></label>
          <label>Country<input value={form.country} onChange={e=>set("country",e.target.value)} autoComplete="country-name" required/></label>
          <label>Password<input type="password" minLength={10} value={form.password} onChange={e=>set("password",e.target.value)} autoComplete="new-password" required/><small>At least 10 characters.</small></label>
          <label>Confirm password<input type="password" minLength={10} value={form.confirm} onChange={e=>set("confirm",e.target.value)} autoComplete="new-password" required/></label>
          <label className="auth-check"><input type="checkbox" checked={form.accept_terms} onChange={e=>set("accept_terms",e.target.checked)} required/><span>I agree to the <Link href="/terms">FAST Terms</Link> and <Link href="/privacy">Privacy Policy</Link>.</span></label>
          {message && <p className="auth-error">{message}</p>}
          <button className="button button-primary" type="submit" disabled={submitting}>{submitting ? "Creating account…" : "Create account"}</button>
        </form>
        <small>Already have a FAST account? <Link href="/login">Sign in</Link>.</small>
      </>}
    </section>
    <Link className="back-link" href="/">← Back to website</Link>
  </main>;
}
