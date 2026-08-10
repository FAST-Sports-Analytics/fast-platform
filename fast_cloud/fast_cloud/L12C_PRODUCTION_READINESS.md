# L12C Production Infrastructure Readiness

## Profiles
- `run_server.bat` remains the local-development entry point and may use SQLite.
- `run_production.bat` sets `FAST_CLOUD_ENV=production`.
- Production refuses to start with SQLite, a weak JWT secret, or no transactional email provider.

## PostgreSQL
Set `FAST_CLOUD_DATABASE_URL` in the production secret store to a
`postgresql+psycopg://...` URL. Credentials must not be committed.

## Health
- `/health` reports service/dependency diagnostics.
- `/ready` is a deployment readiness probe and returns HTTP 503 when the database is unavailable.

## Backup / restore
Run `python -m scripts.backup_database`.
Restore only while Cloud is stopped:
`python -m scripts.restore_database <backup-file> --yes`.
PostgreSQL backup/restore requires `pg_dump` / `pg_restore`.

## Deployment rule
Do not copy the local `.env`, `.venv`, SQLite database, backups, or credentials into a production release.
