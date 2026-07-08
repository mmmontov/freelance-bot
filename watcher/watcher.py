import asyncio
import logging
import random
from collections import defaultdict

from aiogram import Bot

from bot.notifications import send_order
from exchanges.base import BaseExchange
from storage.repository import ChatRepo, SeenOrdersRepo, SubscriptionRepo

logger = logging.getLogger(__name__)

REQUEST_PAUSE = (3.0, 6.0)   # случайная пауза между запросами к бирже, сек
INTERVAL_JITTER = 0.2        # разброс интервала опроса, доля от POLL_INTERVAL
CLEANUP_EVERY = 200          # циклов между чистками seen_orders


class Watcher:
    def __init__(self, bot: Bot, exchanges: dict[str, BaseExchange],
                 chat_repo: ChatRepo, sub_repo: SubscriptionRepo,
                 seen_repo: SeenOrdersRepo, interval: int) -> None:
        self._bot = bot
        self._exchanges = exchanges
        self._chat_repo = chat_repo
        self._sub_repo = sub_repo
        self._seen_repo = seen_repo
        self._interval = interval

    async def run(self) -> None:
        cycle = 0
        while True:
            try:
                await self._poll_all()
            except Exception:
                logger.exception("Цикл опроса завершился с ошибкой")
            cycle += 1
            if cycle % CLEANUP_EVERY == 0:
                await self._seen_repo.cleanup()
            jitter = self._interval * INTERVAL_JITTER
            await asyncio.sleep(self._interval + random.uniform(-jitter, jitter))

    async def _poll_all(self) -> None:
        # опрашиваем биржи для ВСЕХ чатов, даже тех, где уведомления сейчас
        # выключены — иначе seen_orders не обновляется, и при включении
        # уведомлений обратно на чат разом валится накопившаяся пачка заказов
        chat_ids = await self._chat_repo.all_chat_ids()
        if not chat_ids:
            return
        active_ids = set(await self._chat_repo.active_chat_ids())
        for exchange in self._exchanges.values():
            await self._poll_exchange(exchange, chat_ids, active_ids)

    async def _poll_exchange(self, exchange: BaseExchange,
                             chat_ids: list[int], active_ids: set[int]) -> None:
        # уникальные комбинации (рубрика, включённые подрубрики) → чаты
        combos: dict[tuple[str, frozenset[str]], list[int]] = defaultdict(list)
        for chat_id in chat_ids:
            enabled = await self._sub_repo.enabled_rubrics(chat_id, exchange.name)
            for rubric_id, attrs in enabled.items():
                combos[(rubric_id, frozenset(attrs))].append(chat_id)
        if not combos:
            return

        # при первом запуске только помечаем текущие заказы, без рассылки
        bootstrap = not await self._seen_repo.has_any(exchange.name)
        if bootstrap:
            logger.info("Первый запуск для %s: помечаю текущие заказы без рассылки",
                        exchange.name)

        new_ids: set[str] = set()
        delivered: set[tuple[int, str]] = set()

        for (rubric_id, attrs), combo_chats in combos.items():
            try:
                orders = await exchange.fetch_orders(rubric_id, set(attrs))
            except Exception:
                logger.exception("Ошибка запроса %s рубрика %s",
                                 exchange.name, rubric_id)
                continue

            fresh = await self._seen_repo.filter_new(
                exchange.name, [o.order_id for o in orders]
            )
            new_ids.update(fresh)

            if not bootstrap:
                # старые снизу, новые сверху — шлём в хронологическом порядке
                for order in reversed(orders):
                    if order.order_id not in fresh:
                        continue
                    for chat_id in combo_chats:
                        if chat_id not in active_ids:
                            continue
                        key = (chat_id, order.order_id)
                        if key in delivered:
                            continue
                        delivered.add(key)
                        await send_order(self._bot, chat_id, order, exchange.title)

            await asyncio.sleep(random.uniform(*REQUEST_PAUSE))

        if new_ids:
            await self._seen_repo.mark_seen(exchange.name, new_ids)
            if not bootstrap:
                logger.info("%s: %d новых заказов", exchange.name, len(new_ids))
