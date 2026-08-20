"use client";

import Image from "next/image";
import Link from "next/link";
import { FormEvent, useState } from "react";

export default function Signup() {
  const [form, setForm] = useState({ full_name: "", email: "", organisation_name: "", country: "United Kingdom", password: "", confirm: "", accept_terms: false, accept_dpa: false, confirm_admin_age: false });
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
      const response = await fetch("/api/onboarding/register", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          full_name: form.full_name, email: form.email, organisation_name: form.organisation_name,
          country: form.country, password: form.password, accept_terms: form.accept_terms,
          accept_dpa: form.accept_dpa, confirm_admin_age: form.confirm_admin_age,
          terms_version: "2026-08-20", dpa_version: "2026-08-20", privacy_version: "2026-08-20",
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = typeof data.detail === "string"
          ? data.detail
          : "FAST could not create your account.";
        throw new Error(detail);
      }
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
        <Link className="button button-primary" href="/login" style={{ color: "#04150d" }}>Go to sign in</Link>
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
          <label className="auth-check"><input type="checkbox" checked={form.confirm_admin_age} onChange={e=>set("confirm_admin_age",e.target.checked)} required/><span>I confirm that I am at least 18 years old and authorised to create/manage this organisation's FAST account.</span></label>
          <label className="auth-check"><input type="checkbox" checked={form.accept_terms} onChange={e=>set("accept_terms",e.target.checked)} required/><span>I agree on behalf of my organisation to the <Link href="/terms">FAST Terms of Service</Link>.</span></label>
          <label className="auth-check"><input type="checkbox" checked={form.accept_dpa} onChange={e=>set("accept_dpa",e.target.checked)} required/><span>I agree on behalf of my organisation to the <Link href="/dpa">FAST Data Processing Agreement</Link> where FAST processes Customer Personal Data for us.</span></label>
          <small>FAST's <Link href="/privacy">Privacy Notice</Link> explains how FAST handles personal information. It is provided for transparency and is not treated as consent to unnecessary processing.</small>
          {message && <p className="auth-error">{message}</p>}
          <button className="button button-primary" type="submit" disabled={submitting}>{submitting ? "Creating account…" : "Create account"}</button>
        </form>
        <small>Already have a FAST account? <Link href="/login">Sign in</Link>.</small>
      </>}
    </section>
    <Link className="back-link" href="/">← Back to website</Link>
  </main>;
}
