from __future__ import annotations
import argparse, shutil, subprocess
from pathlib import Path
from app.core.config import get_settings

def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a FAST Cloud database backup.")
    parser.add_argument("backup")
    parser.add_argument("--yes", action="store_true", help="Confirm destructive restore.")
    args = parser.parse_args()
    if not args.yes:
        raise SystemExit("Restore is destructive. Re-run with --yes after stopping FAST Cloud.")
    backup = Path(args.backup).resolve()
    if not backup.exists():
        raise SystemExit(f"Backup not found: {backup}")
    url = get_settings().database_url
    if url.startswith("sqlite:///"):
        target = Path(url.removeprefix("sqlite:///"))
        if not target.is_absolute():
            target = Path.cwd() / target
        shutil.copy2(backup, target)
    elif url.startswith(("postgresql://", "postgresql+psycopg://")):
        pg_url = url.replace("postgresql+psycopg://", "postgresql://", 1)
        try:
            subprocess.run(["pg_restore", "--clean", "--if-exists", "--no-owner", "--dbname", pg_url, str(backup)], check=True)
        except FileNotFoundError as exc:
            raise SystemExit("pg_restore is required for PostgreSQL restores.") from exc
    else:
        raise SystemExit("Unsupported FAST_CLOUD_DATABASE_URL.")
    print("Restore completed.")

if __name__ == "__main__":
    main()
