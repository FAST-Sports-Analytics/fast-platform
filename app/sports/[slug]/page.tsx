import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CTA } from "../../components/CTA";
import { PageShell } from "../../components/PageShell";
import { sports } from "../../components/site-data";

type Props = { params: Promise<{ slug: string }> };

export function generateStaticParams() {
  return sports.map((sport) => ({ slug: sport.slug }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { slug } = await params;
  const sport = sports.find((item) => item.slug === slug);
  if (!sport) return {};
  return {
    title: `${sport.name} Analysis Software`,
    description: `${sport.description} Discover the connected FAST workflow for ${sport.name.toLowerCase()}.`,
  };
}

export default async function SportPage({ params }: Props) {
  const { slug } = await params;
  const sport = sports.find((item) => item.slug === slug);
  if (!sport) notFound();

  return <PageShell>
    <section className="page-hero split-hero">
      <div><p className="eyebrow">FAST for {sport.name}</p><h1>{sport.name}<br/><span>analysis, connected.</span></h1><p className="lead">{sport.description}</p><div className="hero-actions"><Link className="button button-primary" href="/trial">Request early access <span>↗</span></Link><Link className="button button-quiet" href="/contact">Discuss your workflow</Link></div></div>
      <div className="product-visual sport-visual"><small>Sport-specific workflow</small><strong>{sport.name}</strong><div className="visual-lines"><i/><i/><i/><i/></div></div>
    </section>
    <section className="content-section"><div className="section-heading compact"><p className="eyebrow">Designed for the game</p><h2>Sport-specific context without a disconnected product.</h2><p>FAST adapts match structure, players and coding logic to {sport.name.toLowerCase()}, while retaining the same analysis, review and cloud workflow across the platform.</p></div><div className="feature-cards">{sport.highlights.map((highlight,index)=><article key={highlight}><span>{String(index+1).padStart(2,"0")}</span><h3>{highlight}</h3><p>Built into the shared FAST environment so analysts and coaches can move from match context to useful video insight without unnecessary friction.</p></article>)}</div></section>
    <section className="workflow-band"><p className="eyebrow">Connected products</p><h2>Code in FAST Analysis. Review in FAST Viewer. Control access through FAST Cloud.</h2><Link href="/platform">Explore the FAST platform <span>→</span></Link></section>
    <CTA title={`Build a clearer ${sport.name.toLowerCase()} analysis workflow.`}/>
  </PageShell>;
}
