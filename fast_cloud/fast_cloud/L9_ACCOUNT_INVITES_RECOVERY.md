# L9 Account, Invitation and Recovery

L9 adds organisation invitation tokens, invitation resend/expiry, password
recovery tokens, normal password changes, audit logging, and SMTP-backed
transactional email.

For local development with no SMTP configured, FAST Cloud writes invitation and
recovery messages to the server console. The Launcher also surfaces development
tokens so the flows can be tested end-to-end.

Production should configure the FAST_CLOUD_SMTP_* values in `.env` and set
FAST_CLOUD_PUBLIC_APP_URL to the public FAST website.
