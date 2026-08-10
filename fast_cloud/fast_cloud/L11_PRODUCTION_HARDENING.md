# L11 Production Hardening

This pass hardens the existing L9/L10 account and recovery flows without changing their public contracts.

## Added
- Process-local rate limiting for password-reset requests, reset-token submissions, invitation acceptance and invitation resends.
- `Retry-After` responses on HTTP 429; Launcher surfaces a human-readable wait time.
- Security response headers and `Cache-Control: no-store` for authentication endpoints.
- Production CORS no longer permits localhost development origins.
- Local Private Network Access headers are development-only.
- `/health` now validates database reachability and reports whether transactional email is configured (without exposing secrets).
- Production startup refuses the default/short JWT secret or missing transactional-email configuration.
- Development verification tokens are no longer returned by `/register` in production.
- Existing invitation/password reset tokens remain one-time and are cleared after successful use.

## Deployment note
The included limiter is intentionally process-local because the current supported FAST Cloud deployment is a single Uvicorn process. Before scaling Cloud to multiple workers/instances, replace it with a shared store such as Redis while preserving the same route-level calls.
