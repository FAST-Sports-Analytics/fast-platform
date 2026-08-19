import type { Metadata } from "next";
import Link from "next/link";
import { CTA } from "../components/CTA";
import { PageShell } from "../components/PageShell";
import { sports } from "../components/site-data";

export const metadata: Metadata = {
  title: "Sports",
  description: "Explore the sport-specific FAST Analysis, FAST Viewer and FAST Cloud workflows available across fourteen sports.",
};

export default function Sports(){return <PageShell><section className="page-hero"><p className="eyebrow">Multi-sport platform</p><h1>Built for your sport.<br/><span>Connected by FAST.</span></h1><p className="lead">Every supported sport has its own match logic while keeping the same familiar analysis, review and delivery workflow.</p></section><section className="content-section"><div className="sport-cards">{sports.map((sport,index)=><Link className="sport-card-link" href={`/sports/${sport.slug}`} key={sport.slug}><article><span>{String(index+1).padStart(2,"0")}</span><h2>{sport.name}</h2><p>{sport.description}</p><small>Explore {sport.name} workflows <b>→</b></small></article></Link>)}</div></section><CTA title="Bring your sport into one connected workflow." /></PageShell>}
