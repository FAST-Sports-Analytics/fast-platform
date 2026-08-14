"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

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
  features?: { remote_management?: boolean; priority_support?: boolean };
  cloud_storage_gb: number;
  self_service_upgrades?: boolean;
};

type Subscription = {
  status: string;
  display_status: string;
  billing_interval: "monthly" | "annual" | null;
  period_label: string;
  period_value?: string | null;
  billing_ready: boolean;
  can_manage_billing: boolean;
  seat_limit?: number | null;
  seats_used?: number;
  device_limit?: number | null;
  plan?: Plan | null;
  scheduled_plan_change?: {
    type: "downgrade";
    plan: Plan;
    billing_interval: "monthly" | "annual";
    effective_at?: string | null;
  } | null;
};

type UserInfo = {
  full_name?: string;
  email?: string;
  role?: string;
  organisation?: { id: number; name: string } | null;
  organisation_admin?: boolean;
};

type PlanChangePreview = {
  change: "upgrade" | "downgrade" | "unchanged";
  effective: "now" | "period_end";
  effective_at?: string | null;
  current_plan?: Plan | null;
  target_plan: Plan;
  current_billing_interval?: "monthly" | "annual";
  target_billing_interval: "monthly" | "annual";
  amount_due_now_pence?: number;
  credit_pence?: number;
  upgrade_charge_pence?: number;
  next_renewal_amount_pence?: number;
  next_renewal_at?: string | null;
  currency?: string;
  proration_date?: number | null;
};

function apiBase() {
  return (process.env.NEXT_PUBLIC_FAST_CLOUD_URL || "http://127.0.0.1:8766").replace(/\/+$/, "");
}

function money(pence: number) {
  return new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP", maximumFractionDigits: pence % 100 === 0 ? 0 : 2 }).format(pence / 100);
}

function dateLabel(value?: string | null) {
  if (!value) return "Not set";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? value : new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" }).format(date);
}

export default function AccountPage() {
  const router = useRouter();
  const [user, setUser] = useState<UserInfo>({});
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [billingMode, setBillingMode] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [planPreview, setPlanPreview] = useState<PlanChangePreview | null>(null);
  const [cancelDowngradeOpen, setCancelDowngradeOpen] = useState(false);

  function token() {
    return typeof window === "undefined" ? "" : window.sessionStorage.getItem("fast_access_token") || "";
  }

  async function api(path: string, init: RequestInit = {}) {
    const auth = token();
    if (!auth) throw new Error("Your FAST Cloud session has ended. Please log in again.");
    const response = await fetch(`${apiBase()}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        Authorization: `Bearer ${auth}`,
        ...(init.headers || {}),
      },
    });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) {
      window.sessionStorage.removeItem("fast_access_token");
      router.replace("/login");
      throw new Error("Your FAST Cloud session has ended. Please log in again.");
    }
    if (!response.ok) throw new Error(data.detail || "FAST Cloud request failed.");
    return data;
  }

  async function load() {
    setLoading(true);
    setError("");
    try {
      const stored = JSON.parse(window.sessionStorage.getItem("fast_user") || "{}");
      setUser(stored);
      const [current, catalogue] = await Promise.all([
        api("/api/v1/subscriptions/current"),
        fetch(`${apiBase()}/api/v1/subscriptions/public-plans`, { headers: { Accept: "application/json" } }).then(async response => {
          const data = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(data.detail || "Subscription plans are unavailable.");
          return data;
        }),
      ]);
      setSubscription(current.subscription || null);
      setPlans((catalogue.plans || []).filter((plan: Plan) => plan.self_service_upgrades !== false && ["starter", "professional"].includes(plan.name.toLowerCase())));
      setBillingMode(catalogue.billing_mode || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "FAST Cloud could not load your account.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!window.sessionStorage.getItem("fast_access_token")) {
      router.replace("/login");
      return;
    }
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const currentPlanId = subscription?.plan?.id;
  const currentPrice = useMemo(() => {
    if (!subscription?.plan || !subscription.billing_interval) return "";
    return subscription.billing_interval === "annual"
      ? `${money(subscription.plan.annual_price_pence)}/year`
      : `${money(subscription.plan.monthly_price_pence)}/month`;
  }, [subscription]);

  async function changePlan(plan: Plan, interval: "monthly" | "annual") {
    if (!subscription?.plan) return;
    const samePlan = currentPlanId === plan.id;
    const sameInterval = subscription.billing_interval === interval;
    if (samePlan && sameInterval) return;

    setWorking(true);
    setMessage("");
    setError("");
    try {
      const preview = await api("/api/v1/subscriptions/change-plan/preview", {
        method: "POST",
        body: JSON.stringify({ plan_id: plan.id, billing_interval: interval }),
      });
      if (preview.change === "unchanged") {
        setMessage("Your subscription is already on that plan and billing interval.");
      } else {
        setPlanPreview(preview as PlanChangePreview);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "FAST Cloud could not preview your plan change.");
    } finally {
      setWorking(false);
    }
  }

  async function confirmPlanChange() {
    if (!planPreview) return;
    setWorking(true);
    setMessage("");
    setError("");
    try {
      const data = await api("/api/v1/subscriptions/change-plan", {
        method: "POST",
        body: JSON.stringify({
          plan_id: planPreview.target_plan.id,
          billing_interval: planPreview.target_billing_interval,
          proration_date: planPreview.proration_date || undefined,
        }),
      });
      if (data.effective === "period_end") {
        setMessage(`Downgrade scheduled. FAST ${planPreview.target_plan.name} will take effect on ${dateLabel(data.effective_at)}. Your current access remains active until then.`);
        await load();
      } else if (data.change === "unchanged") {
        setMessage("Your subscription is already on that plan and billing interval.");
      } else {
        setMessage(`Your organisation is now on FAST ${planPreview.target_plan.name}. Launcher entitlements will refresh automatically.`);
        await load();
      }
      setPlanPreview(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "FAST Cloud could not change your plan.");
    } finally {
      setWorking(false);
    }
  }

  async function cancelScheduledDowngrade() {
    setWorking(true);
    setMessage("");
    setError("");
    try {
      const data = await api("/api/v1/subscriptions/change-plan/cancel-scheduled", { method: "POST" });
      setMessage(data.message || "Scheduled downgrade cancelled. Your current FAST plan will continue.");
      setCancelDowngradeOpen(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "FAST Cloud could not cancel the scheduled downgrade.");
    } finally {
      setWorking(false);
    }
  }

  async function manageBilling() {
    setWorking(true);
    setError("");
    try {
      const data = await api("/api/v1/subscriptions/portal", { method: "POST" });
      if (!data.url) throw new Error("Stripe did not return a billing portal URL.");
      window.location.assign(data.url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "FAST Cloud could not open billing.");
      setWorking(false);
    }
  }

  function logout() {
    window.sessionStorage.removeItem("fast_access_token");
    window.sessionStorage.removeItem("fast_refresh_token");
    window.sessionStorage.removeItem("fast_user");
    router.replace("/login");
  }

  if (loading) return <main className="account-page"><div className="account-shell"><p className="eyebrow">FAST Cloud</p><h1>Loading your account…</h1></div></main>;

  return <main className="account-page">
    <header className="account-header">
      <Link className="account-brand" href="/"><Image src="/branding/fast-logo.png" alt="FAST Sports Analytics" width={500} height={170}/></Link>
      <div className="account-header-actions"><Link href="/" className="text-link">Website</Link><button className="button button-quiet button-small" type="button" onClick={logout}>Log out</button></div>
    </header>

    <div className="account-shell">
      <div className="account-title-row">
        <div><p className="eyebrow">FAST Cloud</p><h1>{user.organisation?.name || "Your FAST account"}</h1><p>{user.full_name || user.email} · {user.role?.replaceAll("_", " ") || "User"}</p></div>
        <span className="account-status">{subscription?.display_status || subscription?.status || "Unconfigured"}</span>
      </div>

      {error && <div className="account-message error">{error}</div>}
      {message && <div className="account-message success">{message}</div>}
      {subscription?.scheduled_plan_change && <div className="account-scheduled-change">
        <div>
          <strong>Downgrade scheduled</strong>
          <span>FAST {subscription.scheduled_plan_change.plan.name} will take effect on {dateLabel(subscription.scheduled_plan_change.effective_at)}. Your FAST {subscription.plan?.name || "current"} access remains active until then.</span>
        </div>
        <button className="button button-quiet button-small" type="button" disabled={working} onClick={() => setCancelDowngradeOpen(true)}>Cancel scheduled downgrade</button>
      </div>}

      {!user.organisation_admin ? <section className="account-panel">
        <h2>Organisation billing</h2>
        <p>Only your organisation administrator can change the FAST subscription or billing details.</p>
      </section> : <>
        <section className="account-panel">
          <div className="account-panel-heading"><div><p className="eyebrow">Current subscription</p><h2>FAST {subscription?.plan?.name || "Plan not configured"}</h2></div><strong className="account-price">{currentPrice}</strong></div>
          <div className="account-metrics">
            <article><small>Users</small><strong>{subscription?.seats_used ?? 0} / {subscription?.seat_limit ?? "—"}</strong></article>
            <article><small>Devices</small><strong>{subscription?.device_limit ?? "—"}</strong></article>
            <article><small>{subscription?.period_label || "Renewal"}</small><strong>{dateLabel(subscription?.period_value)}</strong></article>
            <article><small>Billing</small><strong>{subscription?.billing_interval ? subscription.billing_interval[0].toUpperCase() + subscription.billing_interval.slice(1) : "—"}</strong></article>
          </div>
          {subscription?.plan && <div className="account-entitlements"><span>{subscription.plan.products.map(value => `FAST ${value[0].toUpperCase()}${value.slice(1)}`).join(" + ")}</span><span>{subscription.plan.cloud_storage_gb} GB cloud storage</span></div>}
          <div className="account-actions">
            <button className="button button-quiet" type="button" disabled={working || !subscription?.can_manage_billing} onClick={manageBilling}>Manage payment & invoices</button>
          </div>
        </section>

        <section className="account-panel">
          <div className="account-panel-heading"><div><p className="eyebrow">Change plan</p><h2>Choose the FAST plan that fits your organisation.</h2></div><small>{billingMode === "test" ? "Stripe sandbox" : "Secure Stripe billing"}</small></div>
          <div className="account-plan-grid">
            {plans.map(plan => {
              const current = currentPlanId === plan.id;
              return <article className={current ? "current" : ""} key={plan.id}>
                <div className="account-plan-top"><h3>FAST {plan.name}</h3>{current && <span>Current plan</span>}</div>
                <p>{plan.description}</p>
                <strong>{money(plan.monthly_price_pence)}/month</strong>
                <small>{money(plan.annual_price_pence)}/year</small>
                <ul>
                  <li>{plan.included_seats} included seats</li>
                  <li>{plan.max_devices} devices</li>
                  <li>{plan.products.map(value => `FAST ${value[0].toUpperCase()}${value.slice(1)}`).join(" + ")}</li>
                  <li>{plan.cloud_storage_gb} GB cloud storage</li>
                </ul>
                <div className="account-plan-actions">
                  <button className="button button-primary" type="button" disabled={working || Boolean(subscription?.scheduled_plan_change) || (current && subscription?.billing_interval === "monthly")} onClick={() => changePlan(plan, "monthly")}>{subscription?.scheduled_plan_change?.plan.id === plan.id && subscription?.scheduled_plan_change?.billing_interval === "monthly" ? "Downgrade scheduled" : current && subscription?.billing_interval === "monthly" ? "Current monthly plan" : "Choose monthly"}</button>
                  <button className="button button-quiet" type="button" disabled={working || Boolean(subscription?.scheduled_plan_change) || (current && subscription?.billing_interval === "annual")} onClick={() => changePlan(plan, "annual")}>{subscription?.scheduled_plan_change?.plan.id === plan.id && subscription?.scheduled_plan_change?.billing_interval === "annual" ? "Downgrade scheduled" : current && subscription?.billing_interval === "annual" ? "Current annual plan" : "Choose annual"}</button>
                </div>
              </article>;
            })}
          </div>
          <p className="account-note">Upgrades apply immediately and Stripe handles proration. Downgrades are scheduled for the end of your current paid period so you keep the access you have already paid for.</p>
        </section>
      </>}
    </div>

    {cancelDowngradeOpen && subscription?.scheduled_plan_change && <div className="account-modal-backdrop" role="presentation" onMouseDown={() => !working && setCancelDowngradeOpen(false)}>
      <section className="account-modal" role="dialog" aria-modal="true" aria-labelledby="cancel-downgrade-title" onMouseDown={event => event.stopPropagation()}>
        <button className="account-modal-close" type="button" aria-label="Close" disabled={working} onClick={() => setCancelDowngradeOpen(false)}>×</button>
        <p className="eyebrow">Confirm subscription change</p>
        <h2 id="cancel-downgrade-title">Cancel your scheduled downgrade?</h2>

        <div className="account-confirm-plans">
          <article><small>Keep</small><strong>FAST {subscription.plan?.name || "current plan"}</strong><span>{currentPrice}</span></article>
          <div className="account-confirm-arrow">←</div>
          <article><small>Cancel scheduled change</small><strong>FAST {subscription.scheduled_plan_change.plan.name}</strong><span>Was due {dateLabel(subscription.scheduled_plan_change.effective_at)}</span></article>
        </div>

        <div className="account-confirm-summary">
          <div className="total"><span>Amount due now</span><strong>{money(0)}</strong></div>
          <div><span>Your current plan</span><strong>Continues normally</strong></div>
          <div><span>Scheduled downgrade</span><strong>Removed</strong></div>
        </div>
        <p className="account-confirm-copy">Cancelling the scheduled downgrade keeps FAST {subscription.plan?.name || "your current plan"} active. Your products, seats, devices and current renewal price remain unchanged.</p>

        <div className="account-modal-actions">
          <button className="button button-quiet" type="button" disabled={working} onClick={() => setCancelDowngradeOpen(false)}>Keep scheduled downgrade</button>
          <button className="button button-primary" type="button" disabled={working} onClick={cancelScheduledDowngrade}>{working ? "Processing…" : "Cancel scheduled downgrade"}</button>
        </div>
        <p className="account-confirm-footnote">Billing is handled securely by Stripe. Cancelling this scheduled change does not create an additional charge.</p>
      </section>
    </div>}

    {planPreview && <div className="account-modal-backdrop" role="presentation" onMouseDown={() => !working && setPlanPreview(null)}>
      <section className="account-modal" role="dialog" aria-modal="true" aria-labelledby="plan-change-title" onMouseDown={event => event.stopPropagation()}>
        <button className="account-modal-close" type="button" aria-label="Close" disabled={working} onClick={() => setPlanPreview(null)}>×</button>
        <p className="eyebrow">Confirm plan change</p>
        <h2 id="plan-change-title">{planPreview.change === "downgrade" ? "Schedule your downgrade" : `Upgrade to FAST ${planPreview.target_plan.name}`}</h2>

        <div className="account-confirm-plans">
          <article><small>Current</small><strong>FAST {planPreview.current_plan?.name || subscription?.plan?.name}</strong><span>{planPreview.current_billing_interval === "annual" ? `${money(planPreview.current_plan?.annual_price_pence || 0)}/year` : `${money(planPreview.current_plan?.monthly_price_pence || 0)}/month`}</span></article>
          <div className="account-confirm-arrow">→</div>
          <article><small>New</small><strong>FAST {planPreview.target_plan.name}</strong><span>{planPreview.target_billing_interval === "annual" ? `${money(planPreview.target_plan.annual_price_pence)}/year` : `${money(planPreview.target_plan.monthly_price_pence)}/month`}</span></article>
        </div>

        {planPreview.change === "upgrade" ? <>
          <div className="account-confirm-summary">
            <div><span>Unused-plan credit</span><strong>{money(planPreview.credit_pence || 0)}</strong></div>
            <div><span>Professional access for the remaining period</span><strong>{money(planPreview.upgrade_charge_pence || 0)}</strong></div>
            <div className="total"><span>Estimated amount due now</span><strong>{money(planPreview.amount_due_now_pence || 0)}</strong></div>
            <div><span>Next renewal</span><strong>{money(planPreview.next_renewal_amount_pence || 0)} on {dateLabel(planPreview.next_renewal_at)}</strong></div>
          </div>
          <p className="account-confirm-copy">Stripe calculates the exact proration. Your unused FAST {planPreview.current_plan?.name || "current plan"} time is credited against the upgrade, and the new plan becomes available immediately after the billing change succeeds.</p>
        </> : <>
          <div className="account-confirm-summary">
            <div className="total"><span>Amount due now</span><strong>{money(0)}</strong></div>
            <div><span>FAST {planPreview.target_plan.name} starts</span><strong>{dateLabel(planPreview.effective_at)}</strong></div>
            <div><span>New renewal price</span><strong>{money(planPreview.next_renewal_amount_pence || 0)}/{planPreview.target_billing_interval === "annual" ? "year" : "month"}</strong></div>
          </div>
          <p className="account-confirm-copy">You keep your current FAST {planPreview.current_plan?.name || "plan"} access until the end of the paid period. After that, your limits and product access change to FAST {planPreview.target_plan.name}; installed applications and local data are not deleted.</p>
        </>}

        <div className="account-modal-actions">
          <button className="button button-quiet" type="button" disabled={working} onClick={() => setPlanPreview(null)}>Cancel</button>
          <button className="button button-primary" type="button" disabled={working} onClick={confirmPlanChange}>{working ? "Processing…" : planPreview.change === "downgrade" ? `Confirm downgrade to FAST ${planPreview.target_plan.name}` : `Confirm upgrade to FAST ${planPreview.target_plan.name}`}</button>
        </div>
        <p className="account-confirm-footnote">Billing is handled securely by Stripe. The final amount can vary slightly if taxes, discounts or exchange-rate adjustments apply.</p>
      </section>
    </div>}
  </main>;
}
