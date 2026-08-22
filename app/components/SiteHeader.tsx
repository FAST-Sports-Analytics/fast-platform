"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

const navigation = [["Platform", "/platform"], ["Sports", "/sports"], ["Pricing", "/pricing"], ["Downloads", "/downloads"], ["Docs", "/docs"]] as const;

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    setOpen(false);
    setSignedIn(Boolean(window.sessionStorage.getItem("fast_access_token")));
  }, [pathname]);

  function signOut() {
    window.sessionStorage.removeItem("fast_access_token");
    window.sessionStorage.removeItem("fast_refresh_token");
    window.sessionStorage.removeItem("fast_user");
    setSignedIn(false);
    window.location.assign("/login");
  }

  return <header className="site-header">
    <Link className="brand" href="/" aria-label="FAST Sports Analytics home"><Image src="/branding/fast-logo.png" alt="FAST Sports Analytics" width={500} height={170} priority /></Link>
    <nav className={open ? "primary-nav open" : "primary-nav"} aria-label="Primary navigation" id="primary-navigation">
      {navigation.map(([label, href]) => <Link className={pathname === href || pathname.startsWith(`${href}/`) ? "active" : ""} href={href} key={href}>{label}</Link>)}
      {signedIn
        ? <><Link className="mobile-only-link" href="/account">My account</Link><button className="mobile-only-link nav-button-link" type="button" onClick={signOut}>Sign out</button></>
        : <><Link className="mobile-only-link" href="/login">Sign in</Link><Link className="mobile-only-link" href="/signup">Get started</Link></>}
    </nav>
    <div className="header-actions">
      {signedIn
        ? <><Link className="text-link" href="/account">My account</Link><button className="button button-small button-primary" type="button" onClick={signOut}>Sign out</button></>
        : <><Link className="text-link" href="/login">Sign in</Link><Link className="button button-small button-primary" href="/signup">Get started</Link></>}
      <button className="menu-toggle" type="button" aria-label="Toggle navigation" aria-controls="primary-navigation" aria-expanded={open} onClick={() => setOpen(value => !value)}><span/><span/><span/></button>
    </div>
  </header>;
}
