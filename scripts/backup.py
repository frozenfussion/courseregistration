"""Back up the SQLite database:  python -m scripts.backup

Uses SQLite's own online backup, so it is safe while the site is running. Keeps the newest 14 copies.
"""
import sqlite3
from datetime import datetime
from pathlib import Path

from app.config import get_settings

KEEP = 14


def backup() -> Path:
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        raise SystemExit("Backups are only implemented for SQLite.")
    source = Path(url.replace("sqlite:///", "", 1))
    target_dir = source.parent / "backups"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"regsite-{datetime.now():%Y%m%d-%H%M%S}.db"

    src = sqlite3.connect(source)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    target.chmod(0o600)

    for old in sorted(target_dir.glob("regsite-*.db"))[:-KEEP]:
        old.unlink()
    return target


if __name__ == "__main__":
    print(f"Backup written to {backup()}")
