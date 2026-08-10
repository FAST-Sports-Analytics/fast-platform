# L10 — Production transactional email

FAST Cloud now supports production invitation and password-recovery delivery through Resend or SMTP.

## Recommended production configuration

Set the Cloud environment to `production`, verify a sending domain with Resend, create a sending-only API key, then configure:

- `FAST_CLOUD_EMAIL_PROVIDER=resend`
- `FAST_CLOUD_RESEND_API_KEY=...`
- `FAST_CLOUD_EMAIL_FROM_NAME=FAST Sports Analytics`
- `FAST_CLOUD_EMAIL_FROM_EMAIL=noreply@fastsportsanalytics.com`
- `FAST_CLOUD_EMAIL_REPLY_TO=support@fastsportsanalytics.com`
- `FAST_CLOUD_PUBLIC_APP_URL=https://www.fastsportsanalytics.com`

The API key must remain in server environment configuration and must never be packaged with Launcher or committed to Git.

## Security behaviour

- Invitation and reset tokens are random one-time credentials and only token hashes are stored in the database.
- Successful acceptance/reset clears the stored token hash.
- Expired or reused tokens are rejected.
- Production API responses never return raw invitation or password-reset tokens.
- Production invitation delivery fails closed if the transactional email provider fails.
- Password-reset requests always return a generic response; failed production delivery invalidates the undispatched reset token.
- Development mode retains console delivery and development tokens for local testing.

## Link endpoints

Emails link to:

- `${FAST_CLOUD_PUBLIC_APP_URL}/accept-invite?token=...`
- `${FAST_CLOUD_PUBLIC_APP_URL}/reset-password?token=...`

The public website must route those pages into the account-completion experience before enabling production email for customers.


## Persistent local configuration

Run this once on each FAST Cloud installation after creating a Resend key:

```powershell
cd E:\FAST\fast_cloud
.\setup_resend.ps1
```

The script prompts for the API key using hidden input and stores the provider configuration in the local `.env`. The `.env` file is excluded by `.gitignore` and must not be committed or shared.

After setup, start FAST Cloud with:

```powershell
.\run_server.bat
```

`run_server.bat` validates the current `.venv`. If the project has been moved between computers and the venv points to a missing Python installation, it rebuilds the venv using an available Python 3.10–3.12 interpreter before starting FAST Cloud.
