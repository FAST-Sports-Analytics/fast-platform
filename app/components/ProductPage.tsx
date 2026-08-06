import Link from "next/link";
import { products } from "./site-data";
import { PageShell } from "./PageShell";
import { CTA } from "./CTA";

export function ProductPage({ slug }: { slug: string }) {
  const product = products.find((item) => item.slug === slug)!;
  const planned = product.status === "In development";
  return <PageShell>
    <section className="page-hero split-hero"><div><p className="eyebrow">{product.status} · Product {product.number}</p><h1>{product.name}</h1><p className="lead">{product.description}</p><div className="hero-actions"><Link className="button button-primary" href="/trial">{planned ? "Register interest" : "Request access"} <span>↗</span></Link><Link className="button button-quiet" href="/contact">Talk to FAST</Link></div></div><div className="product-visual"><span>{product.number}</span><small>FAST platform</small><strong>{product.label}</strong><div className="visual-lines"><i/><i/><i/><i/></div></div></section>
    {planned && <section className="notice-band"><strong>Product roadmap</strong><p>{product.name} is in active development. The scope shown here describes the intended product direction and may evolve before release.</p></section>}
    <section className="content-section"><div className="section-heading compact"><p className="eyebrow">Core capabilities</p><h2>{planned ? "The planned foundation for" : "Everything needed to"} {product.label.toLowerCase()} with confidence.</h2></div><div className="feature-cards">{product.features.map((feature,index)=><article key={feature}><span>{String(index+1).padStart(2,"0")}</span><h3>{feature}</h3><p>Designed within one connected FAST workflow, with consistent organisation context, access control and a clear user experience.</p></article>)}</div></section>
    <section className="workflow-band"><p className="eyebrow">Connected by design</p><h2>{product.name} belongs to one shared platform—not another isolated tool.</h2><Link href="/platform">Explore the full platform <span>→</span></Link></section><CTA />
  </PageShell>;
}
