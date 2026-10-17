"""Settings read from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Config:
    discord_token: str
    anthropic_api_key: str | None
    model: str
    db_path: str
    retention_days: int
    owner_only: bool
    dev_guild_id: int | None
    render_workers: int
    render_timeout: float
    usetex: bool

    @classmethod
    def from_env(cls) -> "Config":
        _load_dotenv(Path.cwd() / ".env")
        token = os.environ.get("DISCORD_TOKEN", "")
        guild = os.environ.get("DEV_GUILD_ID", "").strip()
        return cls(
            discord_token=token,
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
            model=os.environ.get("PLOTBOT_MODEL", "claude-opus-5-5"),
            db_path=os.environ.get("PLOTBOT_DB", "plotbot.sqlite3"),
            retention_days=int(os.environ.get("PLOTBOT_RETENTION_DAYS", "30")),
            owner_only=os.environ.get("PLOTBOT_OWNER_ONLY", "0") == "1",
            dev_guild_id=int(guild) if guild else None,
            render_workers=int(os.environ.get("PLOTBOT_RENDER_WORKERS", "2")),
            render_timeout=float(os.environ.get("PLOTBOT_RENDER_TIMEOUT", "30")),
            usetex=os.environ.get("PLOTBOT_USETEX", "0") == "1",
        )
