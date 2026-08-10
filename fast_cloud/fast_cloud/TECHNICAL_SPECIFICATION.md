# FAST Cloud Technical Specification — v0.1

## Service boundary

FAST Cloud owns identity, authentication, licence codes, entitlements and device activations. FAST Hub remains local and owns local matches, clips and media delivery.

## Core entities

### User
Email, password hash, verification status, account status and administrator flag.

### Licence
Hashed code, tier, enabled products, enabled sports, status, expiry, device limit and assigned user.

### Device activation
Licence, stable device identifier, display name, active state, activation timestamp and last validation timestamp.

## Licence-code lifecycle

1. Administrator chooses tier, products, sports, expiry and device limit.
2. FAST Cloud generates a random display code.
3. Only a cryptographic lookup hash and last four characters are persisted.
4. Customer signs in and submits the code from a device.
5. FAST Cloud assigns the licence to the account and records the device.
6. Launcher validates the device and receives authoritative entitlements.
7. Suspended, revoked, expired or over-limit licences are rejected server-side.

## Phase 1 delivery sequence

1. Local authentication/licensing API — included here.
2. Launcher sign-in and activation screen integration.
3. Password-reset and transactional-email provider.
4. Admin licence-management desktop/web interface.
5. PostgreSQL plus Alembic migrations.
6. Deployment, HTTPS, secrets management, rate limiting and audit logs.
