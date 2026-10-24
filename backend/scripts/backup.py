"""Online SQLite backups; schedule daily with Windows Task Scheduler.

Run from backend/: .venv/Scripts/python scripts/backup.py --output ../backups
Each database is transactionally consistent. For a cross-database recovery point,
stop the application before running. Attachments/event blobs are copied as well.
"""

import argparse
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import BACKEND_ROOT, Settings
from app.db.session import normalize_url


def backup_sqlite(source: Path, target: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source.as_uri() + "?mode=ro", uri=True) as original:
        with sqlite3.connect(target) as copy:
            original.backup(copy)
            if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Backup integrity check failed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = Settings()
    if settings.checkpoint_postgres_url:
        parser.error("Use a PostgreSQL backup tool for the configured PostgreSQL checkpointer")
    url = make_url(normalize_url(settings.database_url))
    if url.get_backend_name() != "sqlite" or not url.database:
        parser.error("This script supports local SQLite only")
    folder = args.output.resolve() / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup_sqlite(Path(url.database).resolve(), folder / "aiteams.db")
    checkpoint = Path(settings.checkpoint_db)
    if not checkpoint.is_absolute():
        checkpoint = BACKEND_ROOT / checkpoint
    if checkpoint.is_file():
        backup_sqlite(checkpoint.resolve(), folder / "checkpoints.db")
    if settings.data_dir.is_dir():
        shutil.copytree(settings.data_dir, folder / "data")
    print(f"Backup completed: {folder}")


if __name__ == "__main__":
    main()
