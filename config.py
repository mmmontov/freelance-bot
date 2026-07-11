from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Config:
    bot_token: str
    poll_interval: int
    db_path: Path
    seed_chat_id: int | None
    groq_api_key: str


def load_config() -> Config:
    load_dotenv(BASE_DIR / ".env")

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN не задан в .env")

    seed_chat = os.getenv("SEED_CHAT_ID", "").strip()

    return Config(
        bot_token=token,
        poll_interval=int(os.getenv("POLL_INTERVAL", "180")),
        db_path=BASE_DIR / os.getenv("DB_PATH", "bot.db"),
        seed_chat_id=int(seed_chat) if seed_chat else None,
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
    )
