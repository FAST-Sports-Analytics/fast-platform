import { CTA } from "../components/CTA";
import { PageShell } from "../components/PageShell";
import { PricingPlans } from "./PricingPlans";

const faq=[
["How many sports can we licence?","Starter includes one sport, Professional includes up to five, and Enterprise includes all 14 supported sports."],
["How are licences controlled?","FAST Cloud manages organisation access, user roles, product entitlements, seat limits and controlled device use."],
["Is FAST Scout included?","No. FAST Scout is not part of the launch plans and will only be packaged after it has been developed and tested."],
["Is VAT added?","No. FAST Sports Analytics Ltd is not currently VAT registered, so VAT is not added to launch prices. Customers still receive normal commercial payment records through the billing system."],
];

export default function Pricing(){return <PageShell><section className="page-hero"><p className="eyebrow">Pricing</p><h1>Start focused.<br/><span>Scale when ready.</span></h1><p className="lead">Plans, seats, devices and product access are managed centrally through FAST Cloud. Starter and Professional have fixed launch pricing, while Enterprise is tailored to the organisation.</p></section><section className="content-section"><PricingPlans/></section><section className="content-section soft-section"><div className="section-heading compact"><p className="eyebrow">Pricing questions</p><h2>Clear commercial terms before you commit.</h2></div><div className="faq-grid">{faq.map(([q,a])=><article key={q}><h3>{q}</h3><p>{a}</p></article>)}</div></section><CTA title="Need a package for your club or organisation?" text="Tell us about your teams, analysts and review workflow and we will shape the right early-access setup."/></PageShell>}
