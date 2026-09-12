import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _parse_int_list(value: str) -> list[int]:
    if not value:
        return []
    return [int(x.strip()) for x in value.split(",") if x.strip().isdigit()]


class Settings:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS: list[int] = _parse_int_list(os.getenv("ADMIN_IDS", ""))
    CHANNEL_ID: int = int(os.getenv("CHANNEL_ID", "0")) if os.getenv("CHANNEL_ID") else 0
    DB_PATH: Path = BASE_DIR / os.getenv("DB_PATH", "database/bot.db")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    REF_LINK_COST: int = int(os.getenv("REF_LINK_COST", "111"))
    REF_BONUS: int = int(os.getenv("REF_BONUS", "40"))
    RENEWAL_BONUS: int = int(os.getenv("RENEWAL_BONUS", "20"))
    RESTORE_LEVEL_COST: int = int(os.getenv("RESTORE_LEVEL_COST", "100"))
    SUBSCRIPTION_DAYS: int = int(os.getenv("SUBSCRIPTION_DAYS", "30"))
    SUBSCRIPTION_GRACE_DAYS: int = int(os.getenv("SUBSCRIPTION_GRACE_DAYS", "2"))
    LEGACY_POSTGRES_DUMP: Path = BASE_DIR / os.getenv("LEGACY_POSTGRES_DUMP", "referral_export.dump")
    PG_RESTORE_COMMAND: str = os.getenv("PG_RESTORE_COMMAND", "pg_restore")


settings = Settings()
