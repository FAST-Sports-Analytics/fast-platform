import Link from "next/link";

export function CTA({ title = "Build a clearer analysis workflow.", text = "Start with the products your team needs today and connect the full platform as your operation grows." }) {
  return <section className="cta"><div><p className="eyebrow dark">Get started</p><h2>{title}</h2><p>{text}</p></div><div className="cta-actions"><Link className="button button-light" href="/trial">Start trial <span>↗</span></Link><Link className="button button-dark" href="/contact">Talk to FAST</Link></div></section>;
}
