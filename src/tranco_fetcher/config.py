from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip() or default


@dataclass(frozen=True, slots=True)
class Settings:
    project_root: Path
    mongo_connection_string: str
    tranco_csv_path: Path
    mongo_db_name: str = "tranco"
    mongo_collection_name: str = "websites"
    batch_size: int = 10
    max_concurrency: int = 4
    request_timeout_ms: int = 5_000
    request_wait_ms: int = 3_000
    preflight_timeout_seconds: int = 5
    headless: bool = True
    network_idle: bool = True
    disable_resources: bool = False
    solve_cloudflare: bool = True
    browser_locale: str = "en-US"
    browser_timezone_id: str = "UTC"
    accept_language: str = "en-US,en;q=0.9"
    dry_run: bool = False

    @classmethod
    def from_env(cls, project_root: Path | None = None, dotenv_path: Path | None = None) -> "Settings":
        root = (project_root or Path.cwd()).resolve()
        load_dotenv(dotenv_path=dotenv_path or root / ".env")

        mongo_connection_string = os.getenv("MONGO_CONNECTION_STRING")
        if not mongo_connection_string:
            raise RuntimeError("MONGO_CONNECTION_STRING is required.")

        csv_path = Path(os.getenv("TRANCO_CSV_PATH", "tranco_W4XN9.csv"))

        if not csv_path.is_absolute():
            csv_path = root / csv_path

        return cls(
            project_root=root,
            mongo_connection_string=mongo_connection_string,
            tranco_csv_path=csv_path,
            batch_size=_env_int("TRANCO_BATCH_SIZE", 10),
            max_concurrency=max(1, _env_int("TRANCO_MAX_CONCURRENCY", 4)),
            request_timeout_ms=_env_int("TRANCO_REQUEST_TIMEOUT_MS", 5_000),
            request_wait_ms=_env_int("TRANCO_REQUEST_WAIT_MS", 3_000),
            preflight_timeout_seconds=_env_int("TRANCO_PREFLIGHT_TIMEOUT_SECONDS", 5),
            headless=_env_bool("TRANCO_HEADLESS", True),
            network_idle=_env_bool("TRANCO_NETWORK_IDLE", True),
            disable_resources=_env_bool("TRANCO_DISABLE_RESOURCES", False),
            solve_cloudflare=_env_bool("TRANCO_SOLVE_CLOUDFLARE", True),
            browser_locale=_env_str("TRANCO_BROWSER_LOCALE", "en-US"),
            browser_timezone_id=_env_str("TRANCO_BROWSER_TIMEZONE_ID", "UTC"),
            accept_language=_env_str("TRANCO_ACCEPT_LANGUAGE", "en-US,en;q=0.9"),
            dry_run=_env_bool("TRANCO_DRY_RUN", False),
        )
