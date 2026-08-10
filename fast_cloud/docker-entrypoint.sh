#!/bin/sh
set -eu

python -m scripts.production_preflight

if [ "${FAST_CLOUD_BOOTSTRAP_ADMIN:-false}" = "true" ]; then
  echo "[FAST Cloud] Bootstrapping platform administrator..."
  python -m scripts.create_admin
fi

exec python -m uvicorn app.main:app   --host 0.0.0.0   --port "${PORT:-8766}"   --proxy-headers   --forwarded-allow-ips="*"
