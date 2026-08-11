import { CTA } from "../components/CTA";
import { PageShell } from "../components/PageShell";
import { PricingPlans } from "./PricingPlans";

const faq=[
["Can we start with one product?","Yes. FAST plans can be configured around the products and sports your organisation needs, with room to expand later."],
["How are licences controlled?","FAST Cloud manages organisation access, user roles, product entitlements, seat limits and controlled device use."],
["Are FAST Scout and FAST AI included?","Both products are in development. Availability, packaging and final feature scope will be confirmed separately."],
["How will billing work?","FAST Billing is built around secure subscription checkout and account management through Stripe. Public self-service purchasing will be enabled when launch pricing is final."],
];

export default function Pricing(){return <PageShell><section className="page-hero"><p className="eyebrow">Pricing</p><h1>Start focused.<br/><span>Scale when ready.</span></h1><p className="lead">Plans, seats, devices and product access are managed centrally through FAST Cloud. Final launch pricing will appear here as soon as the commercial packages are locked.</p></section><section className="content-section"><PricingPlans/></section><section className="content-section soft-section"><div className="section-heading compact"><p className="eyebrow">Pricing questions</p><h2>Clear commercial terms before you commit.</h2></div><div className="faq-grid">{faq.map(([q,a])=><article key={q}><h3>{q}</h3><p>{a}</p></article>)}</div></section><CTA title="Need a package for your club or organisation?" text="Tell us about your teams, analysts and review workflow and we will shape the right early-access setup."/></PageShell>}
