from pathlib import Path

from app.core.config import get_settings


def release_packages_dir() -> Path:
    path = Path(get_settings().release_storage_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def backup_dir() -> Path:
    path = Path(get_settings().backup_storage_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path
