FAST Cloud - Stripe quantity / billing interval sync replacement

Replace:
  app/api/routes/subscriptions.py

Changes:
- Stripe subscription item quantity now scales plan user-seat capacity.
- Stripe subscription item quantity now scales licence device capacity.
- Quantity 1 restores the base plan capacity; quantity 2 doubles it, etc.
- Current Stripe recurring interval (month/year) now updates FAST billing_interval, rather than relying on stale checkout metadata.
- Existing webhook lifecycle behaviour (payment failure, grace, recovery, cancellation) is preserved.

Validation performed:
- Python syntax compilation passed.

Expected Professional test result after deployment and a Stripe subscription.updated webhook with quantity 2:
- Licensed users: 1 / 10 (assuming Professional included_seats = 5)
- Device seats: 0 / 10 (assuming Professional max_devices = 5)
- Billing interval: Annual for the current annual Stripe price
