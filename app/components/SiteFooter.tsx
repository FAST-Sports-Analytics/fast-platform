import Image from "next/image";
import Link from "next/link";

export function SiteFooter() {
  return <footer className="site-footer">
    <div className="footer-top"><div className="footer-brand"><Image src="/branding/fast-logo.png" alt="FAST Sports Analytics" width={300} height={102}/><p>Connected sports analysis software for analysts, coaches and performance teams.</p></div><div className="footer-status"><span/><div><strong>Private beta</strong><small>Early-access onboarding in progress</small></div></div></div>
    <div className="footer-links"><div><strong>Platform</strong><Link href="/platform/analysis">FAST Analysis</Link><Link href="/platform/viewer">FAST Viewer</Link><Link href="/platform/cloud">FAST Cloud</Link><Link href="/platform/scout">FAST Scout</Link><Link href="/platform/ai">FAST AI</Link></div><div><strong>Explore</strong><Link href="/sports">Sports</Link><Link href="/pricing">Pricing</Link><Link href="/downloads">Downloads</Link><Link href="/docs">Documentation</Link></div><div><strong>Company</strong><Link href="/contact">Contact</Link><Link href="/trial">Request access</Link><Link href="/login">Log in</Link><Link href="/privacy">Privacy Notice</Link><Link href="/dpa">Data Processing Agreement</Link><Link href="/terms">Terms</Link><Link href="/acceptable-use">Acceptable Use</Link><Link href="/cookies">Cookie Notice</Link><Link href="/subprocessors">Subprocessors</Link></div></div>
    <div className="footer-bottom"><span>© 2026 FAST Sports Analytics. All rights reserved.</span><span>Built for modern performance analysis.</span></div>
  </footer>;
}
