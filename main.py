import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.handlers import commands, menu
from config import load_config
from exchanges.registry import EXCHANGES
from storage.database import Database
from storage.repository import ChatRepo, SeenOrdersRepo, SubscriptionRepo
from watcher.watcher import Watcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def main() -> None:
    config = load_config()

    db = Database(config.db_path)
    conn = await db.connect()
    chat_repo = ChatRepo(conn)
    sub_repo = SubscriptionRepo(conn)
    seen_repo = SeenOrdersRepo(conn)

    if config.seed_chat_id is not None:
        await chat_repo.register(config.seed_chat_id, EXCHANGES.values())

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(chat_repo=chat_repo, sub_repo=sub_repo, seen_repo=seen_repo)
    dp.include_routers(commands.router, menu.router)

    watcher = Watcher(bot, EXCHANGES, chat_repo, sub_repo, seen_repo,
                      config.poll_interval)
    watcher_task = asyncio.create_task(watcher.run())

    logger.info("Бот запущен, интервал опроса %d c", config.poll_interval)
    try:
        await dp.start_polling(bot)
    finally:
        watcher_task.cancel()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
