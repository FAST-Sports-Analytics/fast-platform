# L14 — Stripe Billing Foundation

FAST Cloud now contains the production billing integration points while remaining safe when Stripe is not configured.

## Added

- Public subscription-plan catalogue: `GET /api/v1/subscriptions/public-plans`
- Organisation-admin Checkout creation: `POST /api/v1/subscriptions/checkout`
- Organisation-admin Stripe Customer Portal creation: `POST /api/v1/subscriptions/portal`
- Signed Stripe webhook endpoint: `POST /api/v1/subscriptions/webhooks/stripe`
- Subscription state synchronisation for checkout, subscription changes and invoice payment status
- Stripe customer/subscription identifiers stored in the existing organisation subscription model
- Launcher Billing tab opens the Stripe Customer Portal when billing is connected
- Website pricing reads the centrally managed FAST Cloud plan catalogue

## Configuration

Set these only when a Stripe account is ready:

- `FAST_CLOUD_STRIPE_SECRET_KEY`
- `FAST_CLOUD_STRIPE_WEBHOOK_SECRET`
- `FAST_CLOUD_BILLING_CURRENCY=gbp`

Register the webhook URL ending in `/api/v1/subscriptions/webhooks/stripe` and subscribe it to Checkout, customer subscription and invoice payment events.

Until the secret key is supplied, Stripe billing reports as unavailable and existing FAST authentication, licensing and manual subscription administration continue to work normally.

## Commercial launch dependency

Plan prices remain controlled by FAST Cloud's Subscription Plans admin page. A plan must have a non-zero monthly or annual price before self-service Checkout can be created. This deliberately allows pricing to be finalised later without another application code change.
