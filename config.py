import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Config:
    token: str
    admin_ids: set[int]
    db_path: str
    timezone: ZoneInfo


def _parse_admin_ids(raw: str | None) -> set[int]:
    if not raw:
        return set()
    items = [item.strip() for item in raw.split(",")]
    admin_ids = set()
    for item in items:
        if not item:
            continue
        admin_ids.add(int(item))
    return admin_ids


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN is required")
    admin_ids = _parse_admin_ids(os.getenv("ADMIN_IDS"))
    db_path = os.getenv("DB_PATH", "events.db")
    timezone = ZoneInfo("Europe/Moscow")
    return Config(token=token, admin_ids=admin_ids, db_path=db_path, timezone=timezone)
