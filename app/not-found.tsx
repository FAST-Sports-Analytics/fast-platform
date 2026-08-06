import Link from "next/link";
import { PageShell } from "./components/PageShell";

export default function NotFound(){return <PageShell><section className="page-hero"><p className="eyebrow">404 · Page not found</p><h1>This page is<br/><span>not in the match plan.</span></h1><p className="lead">The page may have moved or the address may be incorrect.</p><Link className="button button-primary" href="/">Return home <span>→</span></Link></section></PageShell>}
