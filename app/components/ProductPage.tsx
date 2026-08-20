import Link from "next/link";
import { products } from "./site-data";
import { PageShell } from "./PageShell";
import { CTA } from "./CTA";
import { ProductScreenshot } from "./ProductScreenshot";

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

const productScreens: Record<string, readonly { src: string; label: string; title: string; text: string; alt: string }[]> = {
  analysis: [
    { src: "/product-screenshots/analysis-workspace.webp", label: "FAST Analysis · Live workspace", title: "One workspace for the whole match", text: "Code events, manage the formation, review the timeline and monitor live statistics without leaving the analysis screen.", alt: "Current FAST Analysis football workspace with match video, coding buttons, formation, event log and live statistics" },
    { src: "/product-screenshots/analysis-home.webp", label: "FAST Analysis · Workflow selection", title: "Start from one focused analysis home", text: "Enter Live Match Analysis immediately, with the future Post-Match Analysis workspace clearly marked as coming soon.", alt: "Current FAST Analysis home screen with Live Match Analysis and disabled Coming Soon Post-Match Analysis option" },
    { src: "/product-screenshots/analysis-modes.webp", label: "FAST Analysis · Analysis modes", title: "Use the same structure with any media source", text: "Run live video, analyse an existing file, log events without video or return to a saved match.", alt: "Current FAST Analysis mode selection showing Live Video, Video File, No Video and Previous Analysis" },
  ],
  viewer: [
    { src: "/product-screenshots/viewer-match-browser.webp", label: "FAST Viewer · Match Browser", title: "Open the right match and the right sport workspace", text: "Licensed matches are presented in one focused browser so coaches can move straight into the review environment.", alt: "Current FAST Viewer Match Browser showing a licensed football match ready to open" },
    { src: "/product-screenshots/viewer-dashboard.webp", label: "FAST Viewer · Dashboard", title: "A review space that is ready when the coach opens it", text: "Match context, clip counts, quick actions and recent clips arrive in a focused Viewer dashboard built for fast conversations.", alt: "Current FAST Viewer football dashboard with recent clips and clip breakdown" },
    { src: "/product-screenshots/viewer-clips.webp", label: "FAST Viewer · Clip library", title: "Every key moment, organised and searchable", text: "Filter clips, review their status, add flags and capture coach comments in the same workspace.", alt: "Current FAST Viewer football clip library with review flags and coach comments" },
    { src: "/product-screenshots/viewer-playlists.webp", label: "FAST Viewer · Playlists", title: "Build half-time and post-match presentations in minutes", text: "Group clips, reorder the message and save discussion notes before presenting to the team.", alt: "Current FAST Viewer playlist workspace with half-time review controls" },
    { src: "/product-screenshots/viewer-players.webp", label: "FAST Viewer · Player review", title: "Review every clip attached to an individual player", text: "Move from the team view to player-specific moments, then open or export the clips needed for individual feedback.", alt: "Current FAST Viewer Players section showing player-tagged football clips" },
  ],
  cloud: [
    { src: "/product-screenshots/cloud-organisation.webp", label: "FAST Cloud · Organisation management", title: "Control the organisation from one place", text: "See subscriptions, seats, users, products, sports, devices and recent activity through a single administration layer.", alt: "FAST organisation management dashboard showing subscription, seats, devices, users and products" },
  ],
};

export function ProductPage({ slug }: { slug: string }) {
  const product = products.find((item) => item.slug === slug)!;
  const planned = product.status === "In development";
  const workflow = productWorkflows[slug] ?? [];
  const screens = productScreens[slug] ?? [];

  return <PageShell>
    <section className={`page-hero split-hero product-page-hero ${screens.length ? "product-page-hero-real" : ""}`}>
      <div><p className="eyebrow">{product.status} · Product {product.number}</p><h1>{product.name}</h1><p className="lead">{product.description}</p><div className="hero-actions"><Link className="button button-primary" href="/trial">{planned ? "Register interest" : "Request access"} <span>↗</span></Link><Link className="button button-quiet" href="/contact">Talk to FAST</Link></div></div>
      {screens.length ? <ProductScreenshot {...screens[0]} caption={screens[0].text} priority className="product-hero-screenshot"/> : <div className={`product-demo product-demo-${slug}`}><div className="demo-bar"><span/><span/><span/><small>{product.name}</small></div><div className="demo-body"><div className="demo-sidebar"><b>FAST</b><i className="active"/><i/><i/><i/></div><div className="demo-workspace"><div className="demo-title"><small>{product.label} workspace</small><strong>{product.name}</strong></div><div className="demo-stat-row"><span><small>Workspace</small><b>Ready</b></span><span><small>Access</small><b>Secure</b></span><span><small>Status</small><b>{planned ? "Roadmap" : "Live"}</b></span></div><div className="demo-chart"><i/><i/><i/><i/><i/><i/></div><div className="demo-list"><span/><span/><span/></div></div></div></div>}
    </section>
    {planned && <section className="notice-band"><strong>Product roadmap</strong><p>{product.name} is in active development. The scope shown here describes the intended product direction and may evolve before release.</p></section>}
    {screens.length > 1 && <section className="content-section product-tour"><div className="section-heading compact"><p className="eyebrow">Inside {product.name}</p><h2>Real software. Built around the working environment.</h2><p>Explore the current private-beta interface. Select any image to view it in full.</p></div><div className="product-tour-list">{screens.slice(1).map((screen, index) => <article className="product-tour-item" key={screen.src}><div className="product-tour-copy"><span>{String(index + 1).padStart(2, "0")}</span><h3>{screen.title}</h3><p>{screen.text}</p></div><ProductScreenshot {...screen}/></article>)}</div></section>}
    <section className="content-section"><div className="section-heading compact"><p className="eyebrow">Core capabilities</p><h2>{planned ? "The planned foundation for" : "Everything needed to"} {product.label.toLowerCase()} with confidence.</h2></div><div className="feature-cards">{product.features.map((feature,index)=><article key={feature}><span>{String(index+1).padStart(2,"0")}</span><h3>{feature}</h3><p>Designed within one connected FAST workflow, with consistent organisation context, access control and a clear user experience.</p></article>)}</div></section>
    <section className="content-section product-workflow"><div className="section-heading compact"><p className="eyebrow">How it fits</p><h2>A clear workflow from first action to useful outcome.</h2><p>{product.name} is structured around the way analysts, coaches and administrators actually work—not around isolated features.</p></div><div className="workflow-steps">{workflow.map(([title,text],index)=><article key={title}><span>{String(index+1).padStart(2,"0")}</span><div><h3>{title}</h3><p>{text}</p></div></article>)}</div></section>
    <section className="workflow-band"><p className="eyebrow">Connected by design</p><h2>{product.name} belongs to one shared platform—not another isolated tool.</h2><Link href="/platform">Explore the full platform <span>→</span></Link></section><CTA />
  </PageShell>;
}
