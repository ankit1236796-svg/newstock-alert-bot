from pathlib import Path

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    sqlite_prefix = "sqlite+aiosqlite:///"
    if settings.database_url.startswith(sqlite_prefix):
        db_path = settings.database_url.removeprefix(sqlite_prefix)
        if db_path not in ("", ":memory:"):
            parent = Path(db_path).parent
            if not parent.exists() or not parent.is_dir():
                raise SystemExit(f"database directory does not exist: {parent}")
            probe = parent / ".healthcheck"
            probe.touch(exist_ok=True)
            probe.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
