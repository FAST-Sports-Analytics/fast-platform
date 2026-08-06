"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";

const navigation = [
  ["Platform", "/platform"],
  ["Sports", "/sports"],
  ["Pricing", "/pricing"],
  ["Downloads", "/downloads"],
  ["Docs", "/docs"],
] as const;

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  return (
    <header className="site-header">
      <Link className="brand" href="/" aria-label="FAST Sports Analytics home" onClick={close}>
        <Image src="/branding/fast-logo.png" alt="FAST Sports Analytics" width={500} height={170} priority />
      </Link>
      <nav className={open ? "primary-nav open" : "primary-nav"} aria-label="Primary navigation">
        {navigation.map(([label, href]) => <Link href={href} key={href} onClick={close}>{label}</Link>)}
        <Link className="mobile-only-link" href="/login" onClick={close}>Log in</Link>
      </nav>
      <div className="header-actions">
        <Link className="text-link" href="/login">Log in</Link>
        <Link className="button button-small button-primary" href="/trial">Start trial</Link>
        <button className="menu-toggle" type="button" aria-label="Toggle navigation" aria-expanded={open} onClick={() => setOpen(value => !value)}>
          <span/><span/><span/>
        </button>
      </div>
    </header>
  );
}
