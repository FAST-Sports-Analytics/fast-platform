"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

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
  self_service_upgrades?: boolean;
};

type SportOption = { key: string; name: string };

type PlansPayload = {
  billing_available?: boolean;
  billing_mode?: "test" | "live" | "unconfigured";
  currency?: string;
  supported_sports?: SportOption[];
  plans?: Plan[];
};

type CheckoutPlan = { plan: Plan; interval: "monthly" | "annual" } | null;

const fallback: Plan[] = [
  { id: -1, name: "Starter", description: "For individual analysts and developing teams.", monthly_price_pence: 3900, annual_price_pence: 39000, included_seats: 2, max_devices: 2, products: ["analysis"], sports: ["football"], cloud_storage_gb: 25, self_service_upgrades: true },
  { id: -2, name: "Professional", description: "For clubs and performance departments using connected analysis and review across up to five sports.", monthly_price_pence: 9900, annual_price_pence: 99000, included_seats: 5, max_devices: 5, products: ["analysis", "viewer"], sports: [], cloud_storage_gb: 100, self_service_upgrades: true },
  { id: -3, name: "Enterprise", description: "For larger multi-team and multi-sport organisations.", monthly_price_pence: 0, annual_price_pence: 0, included_seats: 15, max_devices: 25, products: ["analysis", "viewer"], sports: [], cloud_storage_gb: 500, self_service_upgrades: false },
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
  const [sandboxEnabled, setSandboxEnabled] = useState(false);
  const [checkout, setCheckout] = useState<CheckoutPlan>(null);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [checkoutResult, setCheckoutResult] = useState<"success" | "cancelled" | "">("");
  const [selectedSports, setSelectedSports] = useState<string[]>([]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setSandboxEnabled(params.get("stripe_test") === "1");
    const result = params.get("checkout");
    if (result === "success" || result === "cancelled") setCheckoutResult(result);

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

  const supportedSports = payload.supported_sports?.length
    ? payload.supported_sports
    : [
        { key: "football", name: "Football" },
        { key: "futsal", name: "Futsal" },
        { key: "rugby_union", name: "Rugby Union" },
        { key: "rugby_league", name: "Rugby League" },
        { key: "basketball", name: "Basketball" },
        { key: "field_hockey", name: "Field Hockey" },
        { key: "ice_hockey", name: "Ice Hockey" },
        { key: "cricket", name: "Cricket" },
        { key: "netball", name: "Netball" },
        { key: "volleyball", name: "Volleyball" },
        { key: "handball", name: "Handball" },
        { key: "american_football", name: "American Football" },
        { key: "tennis", name: "Tennis" },
        { key: "baseball", name: "Baseball" },
      ];

  const canCheckout = payload.billing_mode === "live" || (payload.billing_mode === "test" && sandboxEnabled);

  function openCheckout(plan: Plan, interval: "monthly" | "annual") {
    const maxSports = plan.name.toLowerCase() === "starter" ? 1 : 5;
    // Never silently choose a sport for a paid subscription. The customer must
    // explicitly select the sport(s) that will be written to their FAST licence.
    const initial = plan.sports.length && plan.name.toLowerCase() === "starter"
      ? plan.sports.slice(0, maxSports)
      : [];
    setSelectedSports(initial);
    setMessage("");
    setCheckout({ plan, interval });
  }

  function toggleSport(key: string, maxSports: number) {
    setSelectedSports(current => {
      if (current.includes(key)) return current.filter(value => value !== key);
      if (current.length >= maxSports) return current;
      return [...current, key];
    });
  }

  async function submitCheckout(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!checkout) return;
    setSubmitting(true);
    setMessage("");
    const form = new FormData(event.currentTarget);
    if (!selectedSports.length) {
      setMessage("Choose at least one licensed sport.");
      setSubmitting(false);
      return;
    }
    try {
      const response = await fetch(`${apiBase()}/api/v1/subscriptions/public-checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          plan_id: checkout.plan.id,
          billing_interval: checkout.interval,
          organisation_name: String(form.get("organisation") || ""),
          contact_name: String(form.get("name") || ""),
          contact_email: String(form.get("email") || ""),
          sport: selectedSports[0] || "football",
          sports: selectedSports,
          accept_terms: form.get("accept_terms") === "on",
          accept_dpa: form.get("accept_dpa") === "on",
          confirm_admin_age: form.get("confirm_admin_age") === "on",
          terms_version: "2026-08-20",
          dpa_version: "2026-08-20",
          privacy_version: "2026-08-20",
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "FAST Checkout could not be started.");
      if (!data.url) throw new Error("Stripe Checkout did not return a payment URL.");
      window.location.assign(data.url);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "FAST Checkout could not be started.");
      setSubmitting(false);
    }
  }

  return <>
    {checkoutResult === "success" && <div className="checkout-banner success"><strong>Payment received.</strong><span>Stripe is confirming your FAST subscription. Your administrator activation email will follow shortly.</span></div>}
    {checkoutResult === "cancelled" && <div className="checkout-banner"><strong>Checkout cancelled.</strong><span>No payment was taken. You can choose a plan whenever you are ready.</span></div>}

    <div className="pricing-grid">
      {plans.map((plan, index) => {
        const lowerName = plan.name.toLowerCase();
        const featured = lowerName === "professional" || (!plans.some(p => p.name.toLowerCase() === "professional") && index === 1);
        const priced = plan.monthly_price_pence > 0 || plan.annual_price_pence > 0;
        const productNames = plan.products.length ? plan.products.map(value => `FAST ${value.charAt(0).toUpperCase()}${value.slice(1)}`) : ["Configurable FAST products"];
        const selfService = priced && lowerName !== "enterprise" && plan.self_service_upgrades !== false;
        return <article className={featured ? "featured" : ""} key={plan.id}>
          {featured && <small className="recommended">Recommended</small>}
          <p>FAST {plan.name}</p>
          <h2>{plan.name}</h2>
          <span className="price">{priced && plan.monthly_price_pence > 0 ? `${money(plan.monthly_price_pence)}/mo` : lowerName === "enterprise" ? "From £249/mo" : "Coming soon"}</span>
          {priced && plan.annual_price_pence > 0 && <p className="tier-for">{money(plan.annual_price_pence)}/year</p>}
          <p className="tier-for">{plan.description}</p>
          <ul>
            {productNames.map(item => <li key={item}>{item}</li>)}
            <li>{plan.included_seats} included seat{plan.included_seats === 1 ? "" : "s"}</li>
            <li>Up to {plan.max_devices} device{plan.max_devices === 1 ? "" : "s"}</li>
            {plan.cloud_storage_gb > 0 && <li>{plan.cloud_storage_gb} GB cloud storage</li>}
            <li>{lowerName === "starter" ? "1 licensed sport" : lowerName === "professional" ? "Up to 5 licensed sports" : lowerName === "enterprise" ? "All 14 sports" : "Configurable sports access"}</li>
          </ul>
          {lowerName === "enterprise" ? <Link className={`button ${featured ? "button-primary" : "button-quiet"}`} href="/contact">Contact sales</Link>
            : selfService && canCheckout ? <div className="pricing-actions">
              <button className={`button ${featured ? "button-primary" : "button-quiet"}`} type="button" onClick={() => openCheckout(plan, "monthly")}>{payload.billing_mode === "test" ? "Test monthly checkout" : "Choose monthly"}</button>
              {plan.annual_price_pence > 0 && <button className="pricing-annual-link" type="button" onClick={() => openCheckout(plan, "annual")}>{payload.billing_mode === "test" ? "Test annual checkout" : `Choose annual · ${money(plan.annual_price_pence)}`}</button>}
            </div>
            : <Link className={`button ${featured ? "button-primary" : "button-quiet"}`} href="/trial">Register interest</Link>}
        </article>;
      })}
    </div>

    <p className="pricing-note">
      {loaded && payload.billing_mode === "live"
        ? "FAST Billing is live. Starter is £39/month or £390/year; Professional is £99/month or £990/year. Enterprise starts from £249/month and is tailored to each organisation. FAST Sports Analytics Ltd is not currently VAT registered, so VAT is not added to these prices."
        : loaded && payload.billing_mode === "test"
        ? sandboxEnabled ? "Stripe sandbox checkout is enabled for this browser session. No real money will move." : "FAST Billing is connected in Stripe test mode. Live purchasing will be enabled after final payment testing."
        : "Final subscription pricing will be published before public launch. FAST Cloud already supports plan, seat, device and billing-state management."}
    </p>

    {checkout && <div className="checkout-modal" role="dialog" aria-modal="true" aria-labelledby="checkout-title" onMouseDown={event => { if (event.target === event.currentTarget && !submitting) setCheckout(null); }}>
      <section className="checkout-card">
        <button className="checkout-close" type="button" aria-label="Close checkout" disabled={submitting} onClick={() => setCheckout(null)}>×</button>
        <p className="eyebrow">Secure subscription</p>
        <h2 id="checkout-title">FAST {checkout.plan.name}</h2>
        <p className="checkout-summary">{checkout.interval === "monthly" ? `${money(checkout.plan.monthly_price_pence)} per month` : `${money(checkout.plan.annual_price_pence)} per year`} · payment handled securely by Stripe.</p>
        <form className="checkout-form" onSubmit={submitCheckout}>
          <label>Your name<input name="name" autoComplete="name" required maxLength={160}/></label>
          <label>Work email<input name="email" type="email" autoComplete="email" required maxLength={320}/></label>
          <label>Club or organisation<input name="organisation" autoComplete="organization" required maxLength={180}/></label>
          <fieldset className="checkout-sports">
            <legend>{checkout.plan.name.toLowerCase() === "starter" ? "Required: choose your licensed sport" : "Required: choose 1–5 licensed sports"}</legend>
            <p>
              Your selection controls which sports FAST Analysis and FAST Viewer can access.
              {" "}{selectedSports.length} selected{checkout.plan.name.toLowerCase() === "professional" ? " · maximum 5" : ""}.
            </p>
            <div className="checkout-sport-grid">
              {supportedSports.map(sport => {
                const maxSports = checkout.plan.name.toLowerCase() === "starter" ? 1 : 5;
                const checked = selectedSports.includes(sport.key);
                const disabled = !checked && selectedSports.length >= maxSports;
                return <label key={sport.key} className={disabled ? "disabled" : ""}>
                  <input type="checkbox" checked={checked} disabled={disabled} onChange={() => toggleSport(sport.key, maxSports)}/>
                  <span>{sport.name}</span>
                </label>;
              })}
            </div>
          </fieldset>
          <label className="auth-check"><input name="confirm_admin_age" type="checkbox" required/><span>I confirm that I am at least 18 years old and authorised to subscribe for this organisation.</span></label>
          <label className="auth-check"><input name="accept_terms" type="checkbox" required/><span>I agree on behalf of my organisation to the <Link href="/terms">FAST Terms of Service</Link>.</span></label>
          <label className="auth-check"><input name="accept_dpa" type="checkbox" required/><span>I agree on behalf of my organisation to the <Link href="/dpa">FAST Data Processing Agreement</Link> where applicable.</span></label>
          <small>See the <Link href="/privacy">Privacy Notice</Link> for how FAST handles personal information.</small>
          {message && <p className="checkout-error">{message}</p>}
          <button className="button button-primary" type="submit" disabled={submitting}>{submitting ? "Opening Stripe…" : `Continue to Stripe · ${checkout.interval === "monthly" ? money(checkout.plan.monthly_price_pence) : money(checkout.plan.annual_price_pence)}`}</button>
          <small>You will create your FAST administrator password from the secure activation email sent after successful checkout.</small>
        </form>
      </section>
    </div>}
  </>;
}
