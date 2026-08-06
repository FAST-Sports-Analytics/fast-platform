import Link from "next/link";
import { products } from "./site-data";
import { PageShell } from "./PageShell";
import { CTA } from "./CTA";

export function ProductPage({ slug }: { slug: string }) {
  const product = products.find((item) => item.slug === slug)!;
  return <PageShell>
    <section className="page-hero split-hero"><div><p className="eyebrow">{product.label} · Product {product.number}</p><h1>{product.name}</h1><p className="lead">{product.description}</p><div className="hero-actions"><Link className="button button-primary" href="/trial">Start trial <span>↗</span></Link><Link className="button button-quiet" href="/contact">Request a demo</Link></div></div><div className="product-visual"><span>{product.number}</span><small>FAST platform</small><strong>{product.label}</strong><div className="visual-lines"><i/><i/><i/><i/></div></div></section>
    <section className="content-section"><div className="section-heading compact"><p className="eyebrow">Core capabilities</p><h2>Everything needed to {product.label.toLowerCase()} with confidence.</h2></div><div className="feature-cards">{product.features.map((feature, index) => <article key={feature}><span>{String(index + 1).padStart(2, "0")}</span><h3>{feature}</h3><p>Designed as part of one connected FAST workflow, with a consistent interface and structured match context.</p></article>)}</div></section>
    <section className="workflow-band"><p className="eyebrow">Connected by design</p><h2>{product.name} works better as part of the complete FAST platform.</h2><Link href="/platform">Explore the full platform <span>→</span></Link></section>
    <CTA />
  </PageShell>;
}
