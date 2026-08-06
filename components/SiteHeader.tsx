import Image from "next/image";
import Link from "next/link";

export function SiteHeader() {
  return (
    <header className="site-header">
      <Link className="brand" href="/" aria-label="FAST Sports Analytics home">
        <Image src="/branding/fast-logo.png" alt="FAST Sports Analytics" width={500} height={170} priority />
      </Link>
      <nav aria-label="Primary navigation">
        <Link href="/platform">Platform</Link>
        <Link href="/sports">Sports</Link>
        <Link href="/pricing">Pricing</Link>
        <Link href="/downloads">Downloads</Link>
        <Link href="/docs">Docs</Link>
      </nav>
      <div className="header-actions">
        <Link className="text-link" href="/login">Log in</Link>
        <Link className="button button-small button-primary" href="/trial">Start trial</Link>
      </div>
    </header>
  );
}
