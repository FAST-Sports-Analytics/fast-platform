"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { PageShell } from "../components/PageShell";
import { ProductScreenshot } from "../components/ProductScreenshot";

type Installer = {
  version: string;
  platform: string;
  filename: string;
  size_bytes: number;
  sha256: string;
};

function sizeLabel(bytes: number) {
  if (!bytes) return "—";
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function Downloads() {
  const [installer, setInstaller] = useState<Installer | null>(null);
  const [signedIn, setSignedIn] = useState(false);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

  function token() {
    return typeof window === "undefined" ? "" : window.sessionStorage.getItem("fast_access_token") || "";
  }

  useEffect(() => {
    const auth = token();
    setSignedIn(Boolean(auth));
    if (!auth) {
      setLoading(false);
      return;
    }
    fetch("/api/downloads/launcher/latest", {
      headers: { Authorization: `Bearer ${auth}`, Accept: "application/json" },
      cache: "no-store",
    })
      .then(async response => {
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || "FAST could not load the current Launcher download.");
        setInstaller(data.installer || null);
      })
      .catch(error => setError(error instanceof Error ? error.message : "FAST could not load the current Launcher download."))
      .finally(() => setLoading(false));
  }, []);

  async function downloadLauncher() {
    const auth = token();
    if (!auth || !installer) return;
    setWorking(true);
    setError("");
    try {
      const response = await fetch("/api/downloads/launcher/file", {
        headers: { Authorization: `Bearer ${auth}` },
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || "FAST Launcher could not be downloaded.");
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = installer.filename || `FAST_Launcher_Setup_${installer.version}_Windows_x64.exe`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (error) {
      setError(error instanceof Error ? error.message : "FAST Launcher could not be downloaded.");
    } finally {
      setWorking(false);
    }
  }

  return <PageShell>
    <section className="page-hero split-hero downloads-hero">
      <div>
        <p className="eyebrow">Downloads</p>
        <h1>Install FAST once.<br/><span>Launcher handles the rest.</span></h1>
        <p className="lead">FAST Launcher signs you in, activates your device and installs only the FAST products your organisation has assigned to you.</p>
        <div className="hero-actions">
          {signedIn
            ? <Link className="button button-quiet" href="/account">Back to account</Link>
            : <Link className="button button-primary" href="/login">Sign in to download</Link>}
          <Link className="button button-quiet" href="/docs">Installation guide</Link>
        </div>
      </div>
      <ProductScreenshot src="/product-screenshots/launcher.webp" alt="FAST Sports Analytics Launcher" label="FAST Launcher · Windows" priority className="launcher-screenshot"/>
    </section>

    <section className="content-section">
      <div className="download-list">
        <article>
          <span>01</span>
          <div>
            <small>{installer ? `Version ${installer.version}` : "Windows x64"}</small>
            <h2>FAST Launcher for Windows</h2>
            <p>Install Launcher, sign in with your FAST account and let Launcher manage Analysis, Viewer and future updates automatically.</p>
            {installer && <p><strong>{installer.platform}</strong> · {sizeLabel(installer.size_bytes)}</p>}
          </div>
          {!signedIn
            ? <Link className="button button-primary" href="/login">Sign in</Link>
            : loading
              ? <button className="button" disabled>Checking…</button>
              : installer
                ? <button className="button button-primary" type="button" disabled={working} onClick={downloadLauncher}>{working ? "Preparing…" : "Download FAST Launcher"}</button>
                : <button className="button" disabled>Installer unavailable</button>}
        </article>
      </div>

      {error && <p className="auth-error">{error}</p>}

      <div className="info-panel">
        <div><p className="eyebrow">How it works</p><h2>One installer. Account-based products.</h2></div>
        <p>You do not download FAST Analysis or FAST Viewer separately. Launcher checks your organisation role, licensed products and device allowance, then installs and updates the applications you are permitted to use.</p>
        <Link className="inline-link" href="/account">Manage your FAST account <span>→</span></Link>
      </div>
    </section>

    <section className="content-section soft-section">
      <div className="section-heading compact">
        <p className="eyebrow">Windows requirements</p>
        <h2>Prepared for professional video workflows.</h2>
      </div>
      <div className="requirements-grid">
        <article><small>Operating system</small><strong>Windows 10/11 · 64-bit</strong></article>
        <article><small>Memory</small><strong>16 GB minimum · 32 GB recommended</strong></article>
        <article><small>Graphics</small><strong>Dedicated GPU recommended for video</strong></article>
        <article><small>Connection</small><strong>Internet required for sign-in, licensing and updates</strong></article>
      </div>
      <div className="release-flow"><span>01<strong>Download</strong></span><i>→</i><span>02<strong>Install</strong></span><i>→</i><span>03<strong>Sign in</strong></span><i>→</i><span>04<strong>Use FAST</strong></span></div>
    </section>
  </PageShell>;
}
