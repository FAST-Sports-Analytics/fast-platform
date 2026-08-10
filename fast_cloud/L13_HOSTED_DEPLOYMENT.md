# L13 Hosted FAST Cloud

This release is ready to deploy as a container without embedding production secrets.

## Production architecture
- Public API: `https://api.fastsportsanalytics.com`
- Database: hosted PostgreSQL
- Email: Resend
- Website/account UI: `https://www.fastsportsanalytics.com`
- Release packages: persistent mounted filesystem for the first hosted deployment
  (`FAST_CLOUD_RELEASE_STORAGE_PATH`). This can later be migrated to object storage.

## Required production secrets/settings
Set these in the hosting provider's secret/environment configuration:
- `FAST_CLOUD_ENV=production`
- `FAST_CLOUD_DATABASE_URL=postgresql+psycopg://...`
- `FAST_CLOUD_JWT_SECRET=<strong random secret>`
- `FAST_CLOUD_ADMIN_EMAIL=admin@fastsportsanalytics.com`
- `FAST_CLOUD_ADMIN_PASSWORD=<bootstrap-only strong password>`
- `FAST_CLOUD_PUBLIC_APP_URL=https://www.fastsportsanalytics.com`
- `FAST_CLOUD_EMAIL_PROVIDER=resend`
- `FAST_CLOUD_EMAIL_FROM_NAME=FAST Sports Analytics`
- `FAST_CLOUD_EMAIL_FROM_EMAIL=no-reply@fastsportsanalytics.com`
- `FAST_CLOUD_EMAIL_REPLY_TO=support@fastsportsanalytics.com`
- `FAST_CLOUD_RESEND_API_KEY=<secret>`
- `FAST_CLOUD_RELEASE_STORAGE_PATH=/var/lib/fast-cloud/releases/packages`
- `FAST_CLOUD_BACKUP_STORAGE_PATH=/var/lib/fast-cloud/backups`

## First deployment
1. Provision PostgreSQL.
2. Provision a container/web service from this repository/Dockerfile.
3. Attach persistent storage at `/var/lib/fast-cloud`.
4. Set the production environment variables above.
5. Set `FAST_CLOUD_BOOTSTRAP_ADMIN=true` for the first successful deployment.
6. Verify `/health` and `/ready`.
7. Immediately set `FAST_CLOUD_BOOTSTRAP_ADMIN=false`.
8. Point `api.fastsportsanalytics.com` at the hosted service and enable HTTPS.
9. Configure Launcher production builds with:
   `FAST_CLOUD_API_URL=https://api.fastsportsanalytics.com`

## Important
Do not upload `.env`, `.venv`, `fast_cloud.db`, backups, or the Resend key to the host image or Git repository.
The current local SQLite database is development state; the initial hosted PostgreSQL database should be treated as the clean production environment unless a controlled data migration is explicitly performed.
