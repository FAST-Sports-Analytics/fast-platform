# L12A Invitation & Onboarding

- Organisation administrators can invite users without assigning a temporary password.
- FAST Cloud sends a single-use invitation link through the configured transactional email provider.
- Invitation links target `/accept-invite?token=...` on the public FAST website.
- Delivered production invitations do not expose the raw invitation token back to Launcher.
- Invitation expiry is controlled by `FAST_CLOUD_INVITE_EXPIRY_HOURS` (default 72 hours).
- Organisation Management reports invitation state as pending, expired, accepted, or not applicable.
- Resending an invitation rotates the token, invalidating the previous link.
- Acceptance activates the account, verifies the email, clears the one-time token, and writes an audit event.
