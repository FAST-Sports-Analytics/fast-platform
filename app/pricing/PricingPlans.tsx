"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type Plan = {
  id: number;
  name: string;
  description: string;
  monthly_price_pence: number;
  annual_price_pence: number;
  included_seats: number;
  max_devices: number;
  products: string[];
  sports: string[];
  cloud_storage_gb: number;
};

type PlansPayload = { billing_available?: boolean; billing_mode?: "test" | "live" | "unconfigured"; currency?: string; plans?: Plan[] };

const fallback: Plan[] = [
  { id: -1, name: "Starter", description: "For individual analysts and developing teams.", monthly_price_pence: 3900, annual_price_pence: 39000, included_seats: 2, max_devices: 2, products: ["analysis"], sports: ["football"], cloud_storage_gb: 25 },
  { id: -2, name: "Professional", description: "For clubs and performance departments using connected analysis and review.", monthly_price_pence: 8900, annual_price_pence: 89000, included_seats: 5, max_devices: 5, products: ["analysis", "viewer"], sports: [], cloud_storage_gb: 100 },
  { id: -3, name: "Enterprise", description: "For larger organisations that need more users, devices and central control.", monthly_price_pence: 0, annual_price_pence: 0, included_seats: 25, max_devices: 25, products: ["analysis", "viewer"], sports: [], cloud_storage_gb: 500 },
];

function apiBase() {
  return (process.env.NEXT_PUBLIC_FAST_CLOUD_URL || "http://127.0.0.1:8766").replace(/\/+$/, "");
}

function money(pence: number) {
  return new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: pence % 100 === 0 ? 0 : 2 }).format(pence / 100);
}

export function PricingPlans() {
  const [payload, setPayload] = useState<PlansPayload>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let active = true;
    fetch(`${apiBase()}/api/v1/subscriptions/public-plans`, { headers: { Accept: "application/json" } })
      .then(async response => response.ok ? response.json() : Promise.reject(new Error("plans unavailable")))
      .then(data => { if (active) setPayload(data); })
      .catch(() => undefined)
      .finally(() => { if (active) setLoaded(true); });
    return () => { active = false; };
  }, []);

  const plans = useMemo(() => {
    const live = (payload.plans || []).filter(plan => plan.name.toLowerCase() !== "custom");
    return live.length ? live : fallback;
  }, [payload]);

  return <>
    <div className="pricing-grid">
      {plans.map((plan, index) => {
        const featured = plan.name.toLowerCase() === "professional" || (!plans.some(p => p.name.toLowerCase() === "professional") && index === 1);
        const priced = plan.monthly_price_pence > 0 || plan.annual_price_pence > 0;
        const productNames = plan.products.length ? plan.products.map(value => `FAST ${value.charAt(0).toUpperCase()}${value.slice(1)}`) : ["Configurable FAST products"];
        return <article className={featured ? "featured" : ""} key={plan.id}>
          {featured && <small className="recommended">Recommended</small>}
          <p>FAST {plan.name}</p>
          <h2>{plan.name}</h2>
          <span className="price">{priced && plan.monthly_price_pence > 0 ? `${money(plan.monthly_price_pence)}/mo` : plan.name.toLowerCase() === "enterprise" ? "Contact us" : "Coming soon"}</span>
          {priced && plan.annual_price_pence > 0 && <p className="tier-for">{money(plan.annual_price_pence)}/year</p>}
          <p className="tier-for">{plan.description}</p>
          <ul>
            {productNames.map(item => <li key={item}>{item}</li>)}
            <li>{plan.included_seats} included seat{plan.included_seats === 1 ? "" : "s"}</li>
            <li>Up to {plan.max_devices} device{plan.max_devices === 1 ? "" : "s"}</li>
            {plan.cloud_storage_gb > 0 && <li>{plan.cloud_storage_gb} GB cloud storage</li>}
            <li>{plan.sports.length ? plan.sports.map(s => s.replaceAll("_", " ")).join(", ") : "Configurable sports access"}</li>
          </ul>
          <Link className={`button ${featured ? "button-primary" : "button-quiet"}`} href="/contact">{plan.name.toLowerCase() === "enterprise" ? "Contact sales" : payload.billing_mode === "live" ? "Get started" : "Register interest"}</Link>
        </article>;
      })}
    </div>
    <p className="pricing-note">
      {loaded && payload.billing_mode === "live"
        ? "FAST Billing is live. Starter is £39/month or £390/year; Professional is £89/month or £890/year. Enterprise is tailored to each organisation."
        : loaded && payload.billing_mode === "test"
        ? "FAST Billing is connected in Stripe test mode. Live purchasing will be enabled after final payment testing."
        : "Final subscription pricing will be published before public launch. FAST Cloud already supports plan, seat, device and billing-state management."}
    </p>
  </>;
}
