import Link from "next/link";
import { products } from "./site-data";
import { PageShell } from "./PageShell";
import { CTA } from "./CTA";

const productWorkflows: Record<string, readonly [string, string][]> = {
  analysis: [
    ["Prepare", "Choose the sport, squad, formation and coding template before the match begins."],
    ["Code", "Capture live or video-based events with player, team and attribute context."],
    ["Review", "Return to the full timeline, refine events and build decision-ready clips."],
    ["Publish", "Export data or deliver selected moments securely through FAST Cloud."],
  ],
  viewer: [
    ["Receive", "Approved matches and clips arrive automatically for the signed-in user."],
    ["Organise", "Build playlists around meetings, phases, players or coaching themes."],
    ["Explain", "Use comments, freeze-frame and telestration to make the message clear."],
    ["Review", "Keep half-time and post-match conversations focused on the moments that matter."],
  ],
  cloud: [
    ["Organise", "Create organisations, teams and the users who belong to each workflow."],
    ["Control", "Assign roles, product access, licences and approved devices centrally."],
    ["Deliver", "Move matches and selected media securely between FAST products."],
    ["Audit", "Keep account, release and access activity visible to administrators."],
  ],
  scout: [
    ["Observe", "Record structured assessments against a consistent organisation framework."],
    ["Compare", "Review players against agreed attributes, roles and recruitment needs."],
    ["Shortlist", "Bring observations and supporting context into a decision-ready view."],
    ["Connect", "Link future scouting decisions with wider FAST video and organisation context."],
  ],
  ai: [
    ["Discover", "Surface relevant clips, events and match context more quickly."],
    ["Organise", "Reduce repetitive workflow steps while preserving the analyst's structure."],
    ["Support", "Assist with interpretation and reporting without making the final decision."],
    ["Approve", "Keep every suggested output under human review and organisation control."],
  ],
};

export function ProductPage({ slug }: { slug: string }) {
  const product = products.find((item) => item.slug === slug)!;
  const planned = product.status === "In development";
  const workflow = productWorkflows[slug] ?? [];

  return <PageShell>
    <section className="page-hero split-hero product-page-hero"><div><p className="eyebrow">{product.status} · Product {product.number}</p><h1>{product.name}</h1><p className="lead">{product.description}</p><div className="hero-actions"><Link className="button button-primary" href="/trial">{planned ? "Register interest" : "Request access"} <span>↗</span></Link><Link className="button button-quiet" href="/contact">Talk to FAST</Link></div></div><div className={`product-demo product-demo-${slug}`}><div className="demo-bar"><span/><span/><span/><small>{product.name}</small></div><div className="demo-body"><div className="demo-sidebar"><b>FAST</b><i className="active"/><i/><i/><i/></div><div className="demo-workspace"><div className="demo-title"><small>{product.label} workspace</small><strong>{product.name}</strong></div><div className="demo-stat-row"><span><small>Workspace</small><b>Ready</b></span><span><small>Access</small><b>Secure</b></span><span><small>Status</small><b>{planned ? "Roadmap" : "Live"}</b></span></div><div className="demo-chart"><i/><i/><i/><i/><i/><i/></div><div className="demo-list"><span/><span/><span/></div></div></div></div></section>
    {planned && <section className="notice-band"><strong>Product roadmap</strong><p>{product.name} is in active development. The scope shown here describes the intended product direction and may evolve before release.</p></section>}
    <section className="content-section"><div className="section-heading compact"><p className="eyebrow">Core capabilities</p><h2>{planned ? "The planned foundation for" : "Everything needed to"} {product.label.toLowerCase()} with confidence.</h2></div><div className="feature-cards">{product.features.map((feature,index)=><article key={feature}><span>{String(index+1).padStart(2,"0")}</span><h3>{feature}</h3><p>Designed within one connected FAST workflow, with consistent organisation context, access control and a clear user experience.</p></article>)}</div></section>
    <section className="content-section product-workflow"><div className="section-heading compact"><p className="eyebrow">How it fits</p><h2>A clear workflow from first action to useful outcome.</h2><p>{product.name} is structured around the way analysts, coaches and administrators actually work—not around isolated features.</p></div><div className="workflow-steps">{workflow.map(([title,text],index)=><article key={title}><span>{String(index+1).padStart(2,"0")}</span><div><h3>{title}</h3><p>{text}</p></div></article>)}</div></section>
    <section className="workflow-band"><p className="eyebrow">Connected by design</p><h2>{product.name} belongs to one shared platform—not another isolated tool.</h2><Link href="/platform">Explore the full platform <span>→</span></Link></section><CTA />
  </PageShell>;
}
