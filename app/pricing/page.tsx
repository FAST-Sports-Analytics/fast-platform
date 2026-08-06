import Link from "next/link";
import { CTA } from "../components/CTA";
import { PageShell } from "../components/PageShell";

const tiers=[
{name:"Analysis",for:"Individual analysts and developing teams",items:["FAST Analysis desktop access","Live and post-match coding","Multi-sport templates","Clip and data exports"]},
{name:"Team",for:"Clubs and performance departments",items:["Everything in Analysis","FAST Viewer access","Cloud match delivery","Team users and roles"],featured:true},
{name:"Organisation",for:"Multi-team clubs and larger programmes",items:["Everything in Team","Multiple teams and licences","Central administration","Tailored onboarding and support"]}
];
const faq=[
["Can we start with one product?","Yes. The commercial structure is being designed so organisations can begin with the products they need and expand as their workflow develops."],
["Will licences be tied to users?","FAST Cloud is being built around organisation access, roles, product entitlements and controlled device use. Final licence terms will be published before launch."],
["Are FAST Scout and FAST AI included?","Both products are in development. Availability, packaging and final feature scope will be confirmed separately."],
["Can you support multiple teams?","The Organisation tier is intended for clubs and programmes that need central control across multiple teams, users or departments."]
];
export default function Pricing(){return <PageShell><section className="page-hero"><p className="eyebrow">Pricing</p><h1>Start focused.<br/><span>Scale when ready.</span></h1><p className="lead">Final subscription pricing will be published before public launch. Register your interest for early-access availability and tailored team options.</p></section><section className="content-section"><div className="pricing-grid">{tiers.map(tier=><article className={tier.featured?"featured":""} key={tier.name}>{tier.featured&&<small className="recommended">Recommended</small>}<p>FAST {tier.name}</p><h2>{tier.name}</h2><span className="price">Coming soon</span><p className="tier-for">{tier.for}</p><ul>{tier.items.map(item=><li key={item}>{item}</li>)}</ul><Link className={`button ${tier.featured?"button-primary":"button-quiet"}`} href="/contact">Register interest</Link></article>)}</div><p className="pricing-note">All plans are expected to use secure account access and product entitlements through FAST Cloud. Exact features and commercial terms may change before launch.</p></section><section className="content-section soft-section"><div className="section-heading compact"><p className="eyebrow">Pricing questions</p><h2>Clear commercial terms before you commit.</h2></div><div className="faq-grid">{faq.map(([q,a])=><article key={q}><h3>{q}</h3><p>{a}</p></article>)}</div></section><CTA title="Need a package for your club or organisation?" text="Tell us about your teams, analysts and review workflow and we will shape the right early-access setup."/></PageShell>}
