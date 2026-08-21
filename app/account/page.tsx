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

type SportOption = { key: string; name: string };

type Subscription = {
  status: string;
  display_status: string;
  billing_interval: "monthly" | "annual" | null;
  period_label: string;
  period_value?: string | null;
  billing_ready: boolean;
  can_manage_billing: boolean;
  cancel_at_period_end?: boolean;
  current_period_ends_at?: string | null;
  grace_ends_at?: string | null;
  next_payment_attempt_at?: string | null;
  overdue_amount_pence?: number | null;
  overdue_currency?: string | null;
  seat_limit?: number | null;
  seats_used?: number;
  device_limit?: number | null;
  active_devices?: number;
  plan?: Plan | null;
  scheduled_plan_change?: {
    type: "downgrade" | "billing_interval";
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

type OrganisationManagementUser = {
  id: number;
  full_name?: string;
  email: string;
  role?: string;
  status: string;
  products?: string[];
  sports?: string[];
};

type OrganisationManagementDevice = {
  id: number;
  device_id: string;
  device_name?: string;
  active: boolean;
  last_seen_at?: string | null;
};

type OrganisationManagementOverview = {
  users?: OrganisationManagementUser[];
  devices?: OrganisationManagementDevice[];
};

type PlanChangePreview = {
  change: "upgrade" | "downgrade" | "checkout" | "unchanged";
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
  downgrade_blocked?: boolean;
  downgrade_blockers?: string[];
  current_seats_used?: number;
  target_seat_limit?: number;
  current_devices_used?: number;
  target_device_limit?: number;
};

const FALLBACK_SPORTS: SportOption[] = [
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

type PendingCheckout = { plan: Plan; interval: "monthly" | "annual"; kind: "checkout" | "change" } | null;

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
  const [supportedSports, setSupportedSports] = useState<SportOption[]>(FALLBACK_SPORTS);
  const [pendingCheckout, setPendingCheckout] = useState<PendingCheckout>(null);
  const [selectedSports, setSelectedSports] = useState<string[]>([]);
  const [billingMode, setBillingMode] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [planPreview, setPlanPreview] = useState<PlanChangePreview | null>(null);
  const [cancelScheduledChangeOpen, setCancelScheduledChangeOpen] = useState(false);
  const [cancelSubscriptionOpen, setCancelSubscriptionOpen] = useState(false);
  const [capacityManagerOpen, setCapacityManagerOpen] = useState(false);
  const [capacityOverview, setCapacityOverview] = useState<OrganisationManagementOverview | null>(null);
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([]);
  const [selectedDeviceIds, setSelectedDeviceIds] = useState<number[]>([]);

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
    if (!response.ok) {
      const detail = data.detail;
      const message = typeof detail === "string"
        ? detail
        : detail?.message || (Array.isArray(detail?.downgrade_blockers) ? detail.downgrade_blockers.join(" ") : "");
      throw new Error(message || "FAST Cloud request failed.");
    }
    return data;
  }

  async function load() {
    setLoading(true);
    setError("");
    try {
      const stored = JSON.parse(window.sessionStorage.getItem("fast_user") || "{}");
      setUser(stored);
      const [profile, current, catalogue] = await Promise.all([
        api("/api/v1/auth/me"),
        api("/api/v1/subscriptions/current"),
        fetch(`${apiBase()}/api/v1/subscriptions/public-plans`, { headers: { Accept: "application/json" } }).then(async response => {
          const data = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(data.detail || "Subscription plans are unavailable.");
          return data;
        }),
      ]);
      setUser(profile || stored);
      window.sessionStorage.setItem("fast_user", JSON.stringify(profile || stored));
      setSubscription(current.subscription || null);
      setPlans((catalogue.plans || []).filter((plan: Plan) => plan.self_service_upgrades !== false && ["starter", "professional"].includes(plan.name.toLowerCase())));
      setSupportedSports(Array.isArray(catalogue.supported_sports) && catalogue.supported_sports.length ? catalogue.supported_sports : FALLBACK_SPORTS);
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
    const checkoutResult = new URLSearchParams(window.location.search).get("checkout");
    if (checkoutResult === "success") {
      setMessage("Payment received. Stripe is confirming your FAST subscription; your account will update automatically.");
      window.history.replaceState({}, "", "/account");
    } else if (checkoutResult === "cancelled") {
      setMessage("Checkout cancelled. No payment was taken; you can choose a plan whenever you are ready.");
      window.history.replaceState({}, "", "/account");
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

  const billingIntervalOnlyChange = Boolean(
    planPreview?.current_plan?.id
    && planPreview.current_plan.id === planPreview.target_plan.id
    && planPreview.current_billing_interval
    && planPreview.current_billing_interval !== planPreview.target_billing_interval
  );
  const switchingToAnnualBilling = billingIntervalOnlyChange && planPreview?.target_billing_interval === "annual";
  const switchingToMonthlyBilling = billingIntervalOnlyChange && planPreview?.target_billing_interval === "monthly";
  const scheduledBillingIntervalChange = Boolean(
    subscription?.scheduled_plan_change?.type === "billing_interval"
    || (subscription?.scheduled_plan_change?.plan.id === subscription?.plan?.id
      && subscription?.scheduled_plan_change?.billing_interval !== subscription?.billing_interval)
  );
  const scheduledTargetPrice = subscription?.scheduled_plan_change
    ? subscription.scheduled_plan_change.billing_interval === "annual"
      ? `${money(subscription.scheduled_plan_change.plan.annual_price_pence)}/year`
      : `${money(subscription.scheduled_plan_change.plan.monthly_price_pence)}/month`
    : "";

  async function changePlan(plan: Plan, interval: "monthly" | "annual") {
    // Organisations without a subscription use Stripe Checkout for their first
    // purchase. Existing subscribers continue through the plan-change preview
    // flow so upgrades/downgrades retain their current proration behaviour.
    if (!subscription?.plan) {
      setSelectedSports([]);
      setMessage("");
      setError("");
      setPendingCheckout({ plan, interval, kind: "checkout" });
      return;
    }
    const samePlan = currentPlanId === plan.id;
    const sameInterval = subscription.billing_interval === interval;
    if (samePlan && sameInterval) return;
    if (!samePlan) {
      setSelectedSports([]);
      setMessage("");
      setError("");
      setPendingCheckout({ plan, interval, kind: "change" });
      return;
    }

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

  function toggleCheckoutSport(key: string) {
    if (!pendingCheckout) return;
    const maxSports = pendingCheckout.plan.name.toLowerCase() === "starter" ? 1 : 5;
    setSelectedSports(current => {
      if (current.includes(key)) return current.filter(value => value !== key);
      if (current.length >= maxSports) return current;
      return [...current, key];
    });
  }

  async function continueCheckoutWithSports() {
    if (!pendingCheckout) return;
    const maxSports = pendingCheckout.plan.name.toLowerCase() === "starter" ? 1 : 5;
    if (selectedSports.length < 1 || selectedSports.length > maxSports) {
      setError(pendingCheckout.plan.name.toLowerCase() === "starter"
        ? "Choose exactly one licensed sport before continuing to Stripe."
        : "Choose between one and five licensed sports before continuing to Stripe.");
      return;
    }
    setWorking(true);
    setMessage("");
    setError("");
    try {
      if (pendingCheckout.kind === "change") {
        const preview = await api("/api/v1/subscriptions/change-plan/preview", {
          method: "POST",
          body: JSON.stringify({
            plan_id: pendingCheckout.plan.id,
            billing_interval: pendingCheckout.interval,
            sports: selectedSports,
          }),
        });
        setPendingCheckout(null);
        setPlanPreview(preview as PlanChangePreview);
      } else {
        const preview = await api("/api/v1/subscriptions/checkout/preview", {
          method: "POST",
          body: JSON.stringify({
            plan_id: pendingCheckout.plan.id,
            billing_interval: pendingCheckout.interval,
            sports: selectedSports,
          }),
        });
        setPendingCheckout(null);
        if (preview.downgrade_blocked) {
          setPlanPreview(preview as PlanChangePreview);
        } else {
          const data = await api("/api/v1/subscriptions/checkout", {
            method: "POST",
            body: JSON.stringify({
              plan_id: pendingCheckout.plan.id,
              billing_interval: pendingCheckout.interval,
              sports: selectedSports,
            }),
          });
          if (!data.url) throw new Error("Stripe Checkout did not return a payment URL.");
          window.location.assign(data.url);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "FAST Cloud could not start checkout.");
    } finally {
      setWorking(false);
    }
  }

  async function openCapacityManager() {
    if (!planPreview) return;
    setWorking(true);
    setError("");
    try {
      const overview = await api("/api/v1/organisation-management");
      setCapacityOverview(overview as OrganisationManagementOverview);
      setSelectedUserIds([]);
      setSelectedDeviceIds([]);
      setCapacityManagerOpen(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "FAST Cloud could not load your licensed users and devices.");
    } finally {
      setWorking(false);
    }
  }

  async function applyCapacityChanges() {
    if (!planPreview || !capacityOverview) return;
    const usersToRelease = Math.max(0, (planPreview.current_seats_used || 0) - (planPreview.target_seat_limit || 0));
    const devicesToRelease = Math.max(0, (planPreview.current_devices_used || 0) - (planPreview.target_device_limit || 0));
    if (selectedUserIds.length !== usersToRelease || selectedDeviceIds.length !== devicesToRelease) return;
    setWorking(true);
    setError("");
    try {
      await api("/api/v1/subscriptions/change-plan/stage-access", {
        method: "POST",
        body: JSON.stringify({ plan_id: planPreview.target_plan.id, user_ids: selectedUserIds, device_ids: selectedDeviceIds }),
      });
      const previewEndpoint = planPreview.change === "checkout"
        ? "/api/v1/subscriptions/checkout/preview"
        : "/api/v1/subscriptions/change-plan/preview";
      const preview = await api(previewEndpoint, {
        method: "POST",
        body: JSON.stringify({ plan_id: planPreview.target_plan.id, billing_interval: planPreview.target_billing_interval, sports: selectedSports }),
      });
      setPlanPreview(preview as PlanChangePreview);
      setCapacityManagerOpen(false);
      setCapacityOverview(null);
      setSelectedUserIds([]);
      setSelectedDeviceIds([]);
      setMessage(planPreview.change === "checkout"
        ? `Access choices saved. They will take effect only when the new FAST ${planPreview.target_plan.name} subscription activates.`
        : `Access changes selected. They will not take effect until the FAST ${planPreview.target_plan.name} downgrade starts.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "FAST Cloud could not schedule your licence changes.");
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
      if (planPreview.change === "checkout") {
        const data = await api("/api/v1/subscriptions/checkout", {
          method: "POST",
          body: JSON.stringify({
            plan_id: planPreview.target_plan.id,
            billing_interval: planPreview.target_billing_interval,
            sports: selectedSports,
          }),
        });
        if (!data.url) throw new Error("Stripe Checkout did not return a payment URL.");
        window.location.assign(data.url);
        return;
      }
      const data = await api("/api/v1/subscriptions/change-plan", {
        method: "POST",
        body: JSON.stringify({
          plan_id: planPreview.target_plan.id,
          billing_interval: planPreview.target_billing_interval,
          proration_date: planPreview.proration_date || undefined,
          sports: selectedSports,
        }),
      });
      if (data.effective === "period_end") {
        if (billingIntervalOnlyChange) {
          setMessage(`Billing change scheduled. FAST ${planPreview.target_plan.name} will switch to ${planPreview.target_billing_interval} billing on ${dateLabel(data.effective_at)}. Your current ${planPreview.current_billing_interval} plan remains active until then.`);
        } else {
          setMessage(`Downgrade scheduled. FAST ${planPreview.target_plan.name} will take effect on ${dateLabel(data.effective_at)}. Your current access remains active until then.`);
        }
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

  async function cancelScheduledChange() {
    setWorking(true);
    setMessage("");
    setError("");
    try {
      const data = await api("/api/v1/subscriptions/change-plan/cancel-scheduled", { method: "POST" });
      setMessage(data.message || "Scheduled subscription change cancelled. Your current FAST subscription will continue unchanged.");
      setCancelScheduledChangeOpen(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "FAST Cloud could not cancel the scheduled subscription change.");
    } finally {
      setWorking(false);
    }
  }

  async function cancelSubscription() {
    setWorking(true);
    setMessage("");
    setError("");
    try {
      const data = await api("/api/v1/subscriptions/cancel", { method: "POST" });
      setMessage(data.message || "Cancellation scheduled. Your FAST access remains active until the end of the paid period.");
      setCancelSubscriptionOpen(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "FAST Cloud could not schedule the subscription cancellation.");
    } finally {
      setWorking(false);
    }
  }

  async function undoCancellation() {
    setWorking(true);
    setMessage("");
    setError("");
    try {
      const data = await api("/api/v1/subscriptions/cancel/undo", { method: "POST" });
      setMessage(data.message || "Cancellation removed. Your FAST subscription will continue.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "FAST Cloud could not remove the scheduled cancellation.");
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
      {(subscription?.status === "grace_period" || subscription?.status === "past_due") && <div className="account-scheduled-change account-cancellation-notice">
        <div>
          <strong>Payment overdue</strong>
          <span>
            {subscription.overdue_amount_pence != null
              ? `We couldn't collect your ${money(subscription.overdue_amount_pence)} subscription payment. `
              : "We couldn't collect your subscription payment. "}
            {subscription.next_payment_attempt_at
              ? `We'll retry payment on ${dateLabel(subscription.next_payment_attempt_at)}. `
              : "Stripe will retry payment according to your billing retry schedule. "}
            Your grace period ends on {dateLabel(subscription.grace_ends_at)}. FAST will remain available during the grace period. If payment is not recovered before it ends, your subscription will be cancelled and licensed access will stop.
          </span>
        </div>
        <button className="button button-primary button-small" type="button" disabled={working || !subscription.can_manage_billing} onClick={manageBilling}>Fix payment</button>
      </div>}
      {subscription?.cancel_at_period_end && <div className="account-scheduled-change account-cancellation-notice">
        <div>
          <strong>Subscription cancellation scheduled</strong>
          <span>Your FAST {subscription.plan?.name || "subscription"} access remains active until {dateLabel(subscription.current_period_ends_at || subscription.period_value)}. You will not be charged again unless you keep the subscription.</span>
        </div>
        <button className="button button-primary button-small" type="button" disabled={working} onClick={undoCancellation}>{working ? "Processing…" : "Keep subscription"}</button>
      </div>}

      {subscription?.scheduled_plan_change && <div className="account-scheduled-change">
        <div>
          <strong>{scheduledBillingIntervalChange ? "Billing change scheduled" : "Downgrade scheduled"}</strong>
          <span>{scheduledBillingIntervalChange
            ? `Your FAST ${subscription.plan?.name || "subscription"} subscription will switch from ${subscription.billing_interval} billing to ${subscription.scheduled_plan_change.billing_interval} billing on ${dateLabel(subscription.scheduled_plan_change.effective_at)}. Your current ${subscription.billing_interval} plan remains active until then.`
            : `FAST ${subscription.scheduled_plan_change.plan.name} will take effect on ${dateLabel(subscription.scheduled_plan_change.effective_at)}. Your FAST ${subscription.plan?.name || "current"} access remains active until then.`}</span>
        </div>
        <button className="button button-quiet button-small" type="button" disabled={working} onClick={() => setCancelScheduledChangeOpen(true)}>{scheduledBillingIntervalChange ? "Cancel scheduled billing change" : "Cancel scheduled downgrade"}</button>
      </div>}

      {!user.organisation_admin ? <section className="account-panel">
        <div className="account-panel-heading"><div><p className="eyebrow">Your FAST access</p><h2>Downloads</h2></div></div>
        <p>Install FAST Launcher on this device. Launcher will sign you in and install only the FAST products your organisation has assigned to your account.</p>
        <div className="account-actions">
          <Link className="button button-primary" href="/downloads">Downloads</Link>
        </div>
        <p>Subscription, billing and organisation management are available only to your organisation administrator.</p>
      </section> : <>
        <section className="account-panel">
          <div className="account-panel-heading"><div><p className="eyebrow">{subscription?.plan ? "Current subscription" : "Subscription"}</p><h2>{subscription?.plan ? `FAST ${subscription.plan.name}` : "No active FAST subscription"}</h2></div>{subscription?.plan && <strong className="account-price">{currentPrice}</strong>}</div>
          {subscription?.plan ? <>
            <div className="account-metrics">
              <article><small>Licensed users</small><strong>{subscription?.seats_used ?? 0} / {subscription?.seat_limit ?? "—"}</strong></article>
              <article><small>Active devices</small><strong>{subscription?.active_devices ?? 0} / {subscription?.device_limit ?? "—"}</strong></article>
              <article><small>{subscription?.period_label || "Renewal"}</small><strong>{dateLabel(subscription?.period_value)}</strong></article>
              <article><small>Billing</small><strong>{subscription?.billing_interval ? subscription.billing_interval[0].toUpperCase() + subscription.billing_interval.slice(1) : "—"}</strong></article>
            </div>
            <div className="account-entitlements"><span>{subscription.plan.products.map(value => `FAST ${value[0].toUpperCase()}${value.slice(1)}`).join(" + ")}</span><span>{subscription.plan.cloud_storage_gb} GB cloud storage</span></div>
          </> : <p>{subscription?.status === "unconfigured"
            ? "Your FAST account is ready. Choose a plan below to activate your licensed applications and organisation entitlements."
            : "Your paid FAST access has ended. Choose a plan below to restore licensed applications and organisation entitlements."}</p>}
          <div className="account-actions">
            <Link className="button button-primary" href="/downloads">Downloads</Link>
            <Link className="button button-quiet" href="/organisation">Organisation Management</Link>
            <button className="button button-quiet" type="button" disabled={working || !subscription?.can_manage_billing} onClick={manageBilling}>Manage payment & invoices</button>
            {subscription?.plan && !subscription?.cancel_at_period_end && <button className="button button-danger" type="button" disabled={working || !subscription?.can_manage_billing || Boolean(subscription?.scheduled_plan_change)} onClick={() => setCancelSubscriptionOpen(true)}>Cancel subscription</button>}
            {subscription?.plan && subscription?.cancel_at_period_end && <button className="button button-primary" type="button" disabled={working} onClick={undoCancellation}>{working ? "Processing…" : "Keep subscription"}</button>}
          </div>
        </section>

        <section className="account-panel">
          <div className="account-panel-heading"><div><p className="eyebrow">{subscription?.plan ? "Plans & billing" : "Choose a plan"}</p><h2>{subscription?.plan ? "Change your FAST subscription" : "Start your FAST subscription"}</h2></div><small>{billingMode === "test" ? "Test billing environment" : "Payments secured by Stripe"}</small></div>
          <div className="account-plan-grid">
            {plans.map(plan => {
              const current = currentPlanId === plan.id;
              return <article className={current ? "current" : ""} key={plan.id}>
                <div className="account-plan-top"><h3>FAST {plan.name}</h3>{current && <span>Current plan</span>}</div>
                <p>{plan.description}</p>
                <strong>{money(plan.monthly_price_pence)}/month</strong>
                <small>{money(plan.annual_price_pence)}/year</small>
                <ul>
                  <li>{plan.included_seats} licensed users</li>
                  <li>{plan.max_devices} devices</li>
                  <li>{plan.products.map(value => `FAST ${value[0].toUpperCase()}${value.slice(1)}`).join(" + ")}</li>
                  <li>{plan.cloud_storage_gb} GB cloud storage</li>
                </ul>
                <div className="account-plan-actions">
                  <button className="button button-primary" type="button" disabled={working || Boolean(subscription?.scheduled_plan_change) || (current && subscription?.billing_interval === "monthly")} onClick={() => changePlan(plan, "monthly")}>{subscription?.scheduled_plan_change?.plan.id === plan.id && subscription?.scheduled_plan_change?.billing_interval === "monthly" ? (scheduledBillingIntervalChange ? "Billing change scheduled" : "Downgrade scheduled") : current && subscription?.billing_interval === "monthly" ? "Current monthly plan" : "Choose monthly"}</button>
                  <button className="button button-quiet" type="button" disabled={working || Boolean(subscription?.scheduled_plan_change) || (current && subscription?.billing_interval === "annual")} onClick={() => changePlan(plan, "annual")}>{subscription?.scheduled_plan_change?.plan.id === plan.id && subscription?.scheduled_plan_change?.billing_interval === "annual" ? (scheduledBillingIntervalChange ? "Billing change scheduled" : "Downgrade scheduled") : current && subscription?.billing_interval === "annual" ? "Current annual plan" : "Choose annual"}</button>
                </div>
              </article>;
            })}
          </div>
          <p className="account-note">{subscription?.plan ? "Upgrades apply immediately and Stripe calculates any billing adjustment. Downgrades take effect at the end of your current paid period, so you keep the access you have already paid for." : "Your subscription starts after successful payment. Existing organisation accounts are retained, and FAST will ask you to reconcile users or devices first if the selected plan has lower limits."}</p>
        </section>
      </>}
    </div>

    {pendingCheckout && <div className="account-modal-backdrop" role="presentation" onMouseDown={() => !working && setPendingCheckout(null)}>
      <section className="account-modal account-sport-modal" role="dialog" aria-modal="true" aria-labelledby="checkout-sports-title" onMouseDown={event => event.stopPropagation()}>
        <button className="account-modal-close" type="button" aria-label="Close" disabled={working} onClick={() => setPendingCheckout(null)}>×</button>
        <div className="account-sport-heading">
          <p className="eyebrow">Licensed sports</p>
          <h2 id="checkout-sports-title">Choose your FAST {pendingCheckout.plan.name} sport{pendingCheckout.plan.name.toLowerCase() === "starter" ? "" : "s"}</h2>
          <p className="account-confirm-copy">{pendingCheckout.plan.name.toLowerCase() === "starter"
            ? "Select the one sport your organisation will use with FAST Starter."
            : "Select up to five sports your organisation will use with FAST Professional."}</p>
        </div>
        <div className="account-sport-selection-bar">
          <span>{pendingCheckout.plan.name}</span>
          <strong>{selectedSports.length} / {pendingCheckout.plan.name.toLowerCase() === "starter" ? 1 : 5} selected</strong>
        </div>
        <div className="checkout-sport-grid">
          {supportedSports.map(sport => {
            const maxSports = pendingCheckout.plan.name.toLowerCase() === "starter" ? 1 : 5;
            const checked = selectedSports.includes(sport.key);
            const disabled = !checked && selectedSports.length >= maxSports;
            return <label key={sport.key} className={disabled ? "disabled" : ""}>
              <input type="checkbox" checked={checked} disabled={working || disabled} onChange={() => toggleCheckoutSport(sport.key)} />
              <span>{sport.name}</span>
            </label>;
          })}
        </div>
        <div className="account-sport-footer">
          <p>{selectedSports.length < 1
            ? (pendingCheckout.plan.name.toLowerCase() === "starter" ? "Choose one sport to continue." : "Choose at least one sport to continue.")
            : (pendingCheckout.plan.name.toLowerCase() === "starter" ? "Sport selected. You can continue to secure checkout." : `You can select ${5 - selectedSports.length} more sport${5 - selectedSports.length === 1 ? "" : "s"}.`)}</p>
          <div className="account-modal-actions">
            <button className="button button-quiet" type="button" disabled={working} onClick={() => setPendingCheckout(null)}>Cancel</button>
            <button className="button button-primary" type="button" disabled={working || selectedSports.length < 1} onClick={continueCheckoutWithSports}>{working ? "Processing…" : pendingCheckout.kind === "change" ? "Continue to review" : `Continue to Stripe · ${pendingCheckout.interval === "monthly" ? money(pendingCheckout.plan.monthly_price_pence) : money(pendingCheckout.plan.annual_price_pence)}`}</button>
          </div>
        </div>
      </section>
    </div>}

    {cancelSubscriptionOpen && subscription?.plan && <div className="account-modal-backdrop" role="presentation" onMouseDown={() => !working && setCancelSubscriptionOpen(false)}>
      <section className="account-modal" role="dialog" aria-modal="true" aria-labelledby="cancel-subscription-title" onMouseDown={event => event.stopPropagation()}>
        <button className="account-modal-close" type="button" aria-label="Close" disabled={working} onClick={() => setCancelSubscriptionOpen(false)}>×</button>
        <p className="eyebrow">Subscription</p>
        <h2 id="cancel-subscription-title">Cancel FAST {subscription.plan.name}?</h2>
        <div className="account-confirm-summary">
          <div><span>Current plan</span><strong>FAST {subscription.plan.name}</strong></div>
          <div><span>Access continues until</span><strong>{dateLabel(subscription.current_period_ends_at || subscription.period_value)}</strong></div>
          <div><span>Further renewal charges</span><strong>Stopped</strong></div>
        </div>
        <p className="account-confirm-copy">Your FAST products, seats, devices and cloud access stay available until the end of the period you have already paid for. After that date the subscription ends and licensed FAST applications will no longer be available to the organisation.</p>
        <p className="account-confirm-copy">You can reverse this cancellation from this page at any time before the subscription ends.</p>
        <div className="account-modal-actions">
          <button className="button button-quiet" type="button" disabled={working} onClick={() => setCancelSubscriptionOpen(false)}>Keep FAST</button>
          <button className="button button-danger" type="button" disabled={working} onClick={cancelSubscription}>{working ? "Processing…" : "Cancel at period end"}</button>
        </div>
        <p className="account-confirm-footnote">Cancellation is sent securely to Stripe. No refund is issued automatically because your existing access remains available through the paid period.</p>
      </section>
    </div>}

    {cancelScheduledChangeOpen && subscription?.scheduled_plan_change && <div className="account-modal-backdrop" role="presentation" onMouseDown={() => !working && setCancelScheduledChangeOpen(false)}>
      <section className="account-modal" role="dialog" aria-modal="true" aria-labelledby="cancel-scheduled-change-title" onMouseDown={event => event.stopPropagation()}>
        <button className="account-modal-close" type="button" aria-label="Close" disabled={working} onClick={() => setCancelScheduledChangeOpen(false)}>×</button>
        <p className="eyebrow">Confirm subscription change</p>
        <h2 id="cancel-scheduled-change-title">{scheduledBillingIntervalChange ? "Cancel scheduled billing change?" : "Cancel your scheduled downgrade?"}</h2>

        <div className="account-confirm-plans">
          <article><small>Keep</small><strong>FAST {subscription.plan?.name || "current plan"}</strong><span>{currentPrice}</span></article>
          <div className="account-confirm-arrow">←</div>
          <article><small>Cancel scheduled change</small><strong>FAST {subscription.scheduled_plan_change.plan.name}</strong><span>{scheduledBillingIntervalChange ? scheduledTargetPrice : `Was due ${dateLabel(subscription.scheduled_plan_change.effective_at)}`}</span></article>
        </div>

        <div className="account-confirm-summary">
          <div className="total"><span>Amount due now</span><strong>{money(0)}</strong></div>
          <div><span>Your current plan</span><strong>Continues normally</strong></div>
          <div><span>{scheduledBillingIntervalChange ? "Scheduled billing change" : "Scheduled downgrade"}</span><strong>Removed</strong></div>
        </div>
        <p className="account-confirm-copy">{scheduledBillingIntervalChange
          ? `Cancelling this scheduled billing change keeps FAST ${subscription.plan?.name || "your current plan"} on ${subscription.billing_interval} billing. Your products, seats, devices and current renewal price remain unchanged.`
          : <>Cancelling the scheduled downgrade keeps FAST {subscription.plan?.name || "your current plan"} active. Your products, seats, devices and current renewal price remain unchanged.</>}</p>

        <div className="account-modal-actions">
          <button className="button button-quiet" type="button" disabled={working} onClick={() => setCancelScheduledChangeOpen(false)}>{scheduledBillingIntervalChange ? "Keep scheduled billing change" : "Keep scheduled downgrade"}</button>
          <button className="button button-primary" type="button" disabled={working} onClick={cancelScheduledChange}>{working ? "Processing…" : scheduledBillingIntervalChange ? "Cancel scheduled billing change" : "Cancel scheduled downgrade"}</button>
        </div>
        <p className="account-confirm-footnote">Billing is handled securely by Stripe. Cancelling this scheduled change does not create an additional charge.</p>
      </section>
    </div>}

    {planPreview && <div className="account-modal-backdrop" role="presentation" onMouseDown={() => !working && setPlanPreview(null)}>
      <section className="account-modal" role="dialog" aria-modal="true" aria-labelledby="plan-change-title" onMouseDown={event => event.stopPropagation()}>
        <button className="account-modal-close" type="button" aria-label="Close" disabled={working} onClick={() => setPlanPreview(null)}>×</button>
        <p className="eyebrow">Confirm plan change</p>
        <h2 id="plan-change-title">{
          billingIntervalOnlyChange
            ? `Switch to ${planPreview.target_billing_interval === "annual" ? "annual" : "monthly"} billing`
            : planPreview.change === "downgrade"
              ? "Schedule your downgrade"
              : planPreview.change === "checkout"
                ? `Start FAST ${planPreview.target_plan.name}`
                : `Upgrade to FAST ${planPreview.target_plan.name}`
        }</h2>

        <div className="account-confirm-plans">
          <article><small>Current</small><strong>{planPreview.change === "checkout" ? "No active FAST subscription" : `FAST ${planPreview.current_plan?.name || subscription?.plan?.name}`}</strong><span>{planPreview.change === "checkout" ? "Access inactive" : planPreview.current_billing_interval === "annual" ? `${money(planPreview.current_plan?.annual_price_pence || 0)}/year` : `${money(planPreview.current_plan?.monthly_price_pence || 0)}/month`}</span></article>
          <div className="account-confirm-arrow">→</div>
          <article><small>New</small><strong>FAST {planPreview.target_plan.name}</strong><span>{planPreview.target_billing_interval === "annual" ? `${money(planPreview.target_plan.annual_price_pence)}/year` : `${money(planPreview.target_plan.monthly_price_pence)}/month`}</span></article>
        </div>

        {planPreview.change === "upgrade" ? <>
          <div className="account-confirm-summary">
            <div><span>{switchingToAnnualBilling ? "Unused monthly-plan credit" : switchingToMonthlyBilling ? "Unused annual-plan credit" : "Unused-plan credit"}</span><strong>{money(planPreview.credit_pence || 0)}</strong></div>
            <div><span>{switchingToAnnualBilling ? "Annual plan charge" : switchingToMonthlyBilling ? "Monthly plan charge" : `${planPreview.target_plan.name} access for the remaining period`}</span><strong>{money(planPreview.upgrade_charge_pence || 0)}</strong></div>
            <div className="total"><span>Estimated amount due now</span><strong>{money(planPreview.amount_due_now_pence || 0)}</strong></div>
            <div><span>Next renewal</span><strong>{money(planPreview.next_renewal_amount_pence || 0)} on {dateLabel(planPreview.next_renewal_at)}</strong></div>
          </div>
          <p className="account-confirm-copy">{
            billingIntervalOnlyChange
              ? `Stripe calculates the exact proration. Your unused ${planPreview.current_billing_interval === "annual" ? "annual" : "monthly"} FAST ${planPreview.target_plan.name} time is credited against the switch to ${planPreview.target_billing_interval === "annual" ? "annual" : "monthly"} billing. Your FAST plan, products, seats and devices stay the same.`
              : <>Stripe calculates the exact proration. Your unused FAST {planPreview.current_plan?.name || "current plan"} time is credited against the upgrade, and the new plan becomes available immediately after the billing change succeeds.</>
          }</p>
        </> : <>
          <div className="account-confirm-summary">
            <div className="total"><span>Amount due now</span><strong>{money(planPreview.change === "checkout" ? (planPreview.amount_due_now_pence || 0) : 0)}</strong></div>
            <div><span>FAST {planPreview.target_plan.name} starts</span><strong>{planPreview.change === "checkout" ? "After successful payment" : dateLabel(planPreview.effective_at)}</strong></div>
            <div><span>New renewal price</span><strong>{money(planPreview.next_renewal_amount_pence || 0)}/{planPreview.target_billing_interval === "annual" ? "year" : "month"}</strong></div>
          </div>
          {!billingIntervalOnlyChange && planPreview.downgrade_blocked && <div className="account-message error" role="alert">
            <strong>{planPreview.change === "checkout" ? "Choose access for the new subscription" : "Reduce usage before downgrading"}</strong>
            {(planPreview.downgrade_blockers || []).map((blocker, index) => <p key={index}>{blocker}</p>)}
          </div>}
          <p className="account-confirm-copy">{billingIntervalOnlyChange
            ? `You keep your current FAST ${planPreview.current_plan?.name || "plan"} access until the end of the paid ${planPreview.current_billing_interval} period. On ${dateLabel(planPreview.effective_at)}, your subscription switches to ${planPreview.target_billing_interval} billing at ${money(planPreview.next_renewal_amount_pence || 0)}/${planPreview.target_billing_interval === "annual" ? "year" : "month"}. Your products, seats, devices, installed applications and local data remain unchanged.`
            : planPreview.change === "checkout"
              ? planPreview.downgrade_blocked
                ? <>Your previous organisation users and devices are retained, but FAST {planPreview.target_plan.name} has lower limits. Choose which access to release before continuing to Stripe.</>
                : <>FAST {planPreview.target_plan.name} will activate after successful Stripe payment. Any access choices made for the new plan are applied when that new subscription activates.</>
              : planPreview.downgrade_blocked
                ? <>Your current FAST {planPreview.current_plan?.name || "plan"} remains unchanged. Reduce your licensed users/devices to the FAST {planPreview.target_plan.name} limits, then choose this downgrade again.</>
                : <>You keep your current FAST {planPreview.current_plan?.name || "plan"} access until the end of the paid period. After that, your limits and product access change to FAST {planPreview.target_plan.name}; installed applications and local data are not deleted.</>}</p>
        </>}

        <div className="account-modal-actions">
          <button className="button button-quiet" type="button" disabled={working} onClick={() => setPlanPreview(null)}>Cancel</button>
          <button className="button button-primary" type="button" disabled={working} onClick={(planPreview.change === "downgrade" || planPreview.change === "checkout") && planPreview.downgrade_blocked ? openCapacityManager : confirmPlanChange}>{
            working
              ? "Processing…"
              : (planPreview.change === "downgrade" || planPreview.change === "checkout") && planPreview.downgrade_blocked
                ? "Choose licences to remove"
                : billingIntervalOnlyChange
                  ? `Confirm switch to ${planPreview.target_billing_interval === "annual" ? "annual" : "monthly"} billing`
                  : planPreview.change === "downgrade"
                    ? `Confirm downgrade to FAST ${planPreview.target_plan.name}`
                    : planPreview.change === "checkout"
                      ? `Continue to Stripe for FAST ${planPreview.target_plan.name}`
                      : `Confirm upgrade to FAST ${planPreview.target_plan.name}`
          }</button>
        </div>
        <p className="account-confirm-footnote">Billing is handled securely by Stripe. The final amount can vary slightly if taxes, discounts or exchange-rate adjustments apply.</p>
      </section>
    </div>}

    {capacityManagerOpen && planPreview && capacityOverview && <div className="account-modal-backdrop" role="presentation">
      <section className="account-modal" role="dialog" aria-modal="true" aria-labelledby="capacity-manager-title">
        <button className="account-modal-close" type="button" disabled={working} onClick={() => setCapacityManagerOpen(false)} aria-label="Close">×</button>
        <p className="eyebrow">MANAGE DOWNGRADE LIMITS</p>
        <h2 id="capacity-manager-title">Choose access to remove</h2>
        <p className="account-confirm-copy">FAST {planPreview.target_plan.name} includes {planPreview.target_seat_limit} licensed users and {planPreview.target_device_limit} active devices. Choose which access should be released {planPreview.change === "checkout" ? "when the new subscription activates" : "when the downgrade takes effect"}. Accounts, roles, memberships and local data are not deleted.</p>

        {(planPreview.current_seats_used || 0) > (planPreview.target_seat_limit || 0) && <div className="account-capacity-section">
          <h3>Licensed users</h3>
          <p>Select exactly {(planPreview.current_seats_used || 0) - (planPreview.target_seat_limit || 0)} user(s) whose licensed access will be released {planPreview.change === "checkout" ? "when the new subscription activates" : "on the downgrade date"}. Your own administrator access cannot be selected.</p>
          <div className="account-capacity-list">
            {(capacityOverview.users || []).filter(item => ["active", "invited"].includes(String(item.status || "").toLowerCase())).map(item => {
              const isSelf = item.email.toLowerCase() === String(user.email || "").toLowerCase();
              const checked = selectedUserIds.includes(item.id);
              const required = (planPreview.current_seats_used || 0) - (planPreview.target_seat_limit || 0);
              const atLimit = selectedUserIds.length >= required && !checked;
              return <label key={item.id} className={`account-capacity-row${isSelf ? " protected" : ""}`}>
                <input type="checkbox" checked={checked} disabled={working || isSelf || atLimit} onChange={() => setSelectedUserIds(ids => checked ? ids.filter(id => id !== item.id) : [...ids, item.id])} />
                <span><strong>{item.full_name || item.email}</strong><small>{item.email} · {(item.role || "user").replace(/^./, c => c.toUpperCase())}{isSelf ? " · Your administrator account" : ""}</small></span>
              </label>;
            })}
          </div>
        </div>}

        {(planPreview.current_devices_used || 0) > (planPreview.target_device_limit || 0) && <div className="account-capacity-section">
          <h3>Active devices</h3>
          <p>Select exactly {(planPreview.current_devices_used || 0) - (planPreview.target_device_limit || 0)} device(s) to deactivate {planPreview.change === "checkout" ? "when the new subscription activates" : "on the downgrade date"}.</p>
          <div className="account-capacity-list">
            {(capacityOverview.devices || []).filter(item => item.active).map(item => {
              const checked = selectedDeviceIds.includes(item.id);
              const required = (planPreview.current_devices_used || 0) - (planPreview.target_device_limit || 0);
              const atLimit = selectedDeviceIds.length >= required && !checked;
              return <label key={item.id} className="account-capacity-row">
                <input type="checkbox" checked={checked} disabled={working || atLimit} onChange={() => setSelectedDeviceIds(ids => checked ? ids.filter(id => id !== item.id) : [...ids, item.id])} />
                <span><strong>{item.device_name || item.device_id}</strong><small>{item.last_seen_at ? `Last seen ${dateLabel(item.last_seen_at)}` : item.device_id}</small></span>
              </label>;
            })}
          </div>
        </div>}

        <div className="account-modal-actions">
          <button className="button button-quiet" type="button" disabled={working} onClick={() => setCapacityManagerOpen(false)}>Back</button>
          <button className="button button-primary" type="button" disabled={working || selectedUserIds.length < Math.max(0, (planPreview.current_seats_used || 0) - (planPreview.target_seat_limit || 0)) || selectedDeviceIds.length < Math.max(0, (planPreview.current_devices_used || 0) - (planPreview.target_device_limit || 0))} onClick={applyCapacityChanges}>{working ? "Saving…" : planPreview.change === "checkout" ? "Save access choices" : "Schedule access changes"}</button>
        </div>
      </section>
    </div>}
  </main>;
}
