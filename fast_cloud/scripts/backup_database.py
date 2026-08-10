from __future__ import annotations
import shutil, subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from app.core.config import get_settings
from app.core.storage import backup_dir

def main() -> None:
    settings = get_settings()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = backup_dir()
    url = settings.database_url
    if url.startswith("sqlite:///"):
        source = Path(url.removeprefix("sqlite:///"))
        if not source.is_absolute():
            source = Path.cwd() / source
        target = out / f"fast_cloud_{stamp}.db"
        shutil.copy2(source, target)
    elif url.startswith(("postgresql://", "postgresql+psycopg://")):
        target = out / f"fast_cloud_{stamp}.dump"
        pg_url = url.replace("postgresql+psycopg://", "postgresql://", 1)
        try:
            subprocess.run(["pg_dump", "--format=custom", "--file", str(target), pg_url], check=True)
        except FileNotFoundError as exc:
            raise SystemExit("pg_dump is required for PostgreSQL backups.") from exc
    else:
        raise SystemExit("Unsupported FAST_CLOUD_DATABASE_URL.")
    print(f"Backup created: {target.resolve()}")

if __name__ == "__main__":
    main()
