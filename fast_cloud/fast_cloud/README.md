# FAST Cloud v0.2.1

Clean local development build for FAST Sports Analytics authentication and licensing.

## Install

1. Delete or rename the previous `E:\FAST\fast_cloud` folder.
2. Extract this ZIP.
3. Rename the extracted folder to `fast_cloud` and place it at `E:\FAST\fast_cloud`.
4. Open PowerShell in that folder.
5. Run:

```powershell
.\run_server.bat
```

The script creates its own `.venv`, installs dependencies, creates `.env`, seeds the administrator, and starts the server.

## Addresses

- Admin Portal: `http://127.0.0.1:8766/admin`
- API documentation: `http://127.0.0.1:8766/docs`
- Health check: `http://127.0.0.1:8766/health`

## Development administrator

- Email: `admin@fastsportsanalytics.com`
- Password: `ChangeMe123!`

Change these values in `.env` before any deployment.

## Included in this milestone

- Registration, email verification and login APIs
- Access and refresh tokens
- Administrator portal login
- Dashboard for users and licences
- Licence-code generation
- Product and sport entitlements
- Licence expiry and device limits
- Licence activation, validation and device deactivation APIs
- Licence and user status controls

FAST Hub remains a separate local match and clip service.
