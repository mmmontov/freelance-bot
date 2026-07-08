from collections.abc import Iterable

import aiosqlite

from exchanges.base import BaseExchange


class ChatRepo:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def exists(self, chat_id: int) -> bool:
        cur = await self._conn.execute(
            "SELECT 1 FROM chats WHERE chat_id = ?", (chat_id,)
        )
        return await cur.fetchone() is not None

    async def register(self, chat_id: int, exchanges: Iterable[BaseExchange]) -> None:
        """Создаёт чат с дефолтными подписками. Повторный вызов ничего не меняет."""
        if await self.exists(chat_id):
            return
        await self._conn.execute("INSERT INTO chats (chat_id) VALUES (?)", (chat_id,))
        for exchange in exchanges:
            for rubric in exchange.rubrics():
                await self._conn.execute(
                    "INSERT OR IGNORE INTO subscriptions VALUES (?, ?, ?, '', 1)",
                    (chat_id, exchange.name, rubric.id),
                )
                for sub in rubric.subrubrics:
                    await self._conn.execute(
                        "INSERT OR IGNORE INTO subscriptions VALUES (?, ?, ?, ?, ?)",
                        (chat_id, exchange.name, rubric.id, sub.id,
                         int(sub.default_enabled)),
                    )
        await self._conn.commit()

    async def is_enabled(self, chat_id: int) -> bool:
        cur = await self._conn.execute(
            "SELECT enabled FROM chats WHERE chat_id = ?", (chat_id,)
        )
        row = await cur.fetchone()
        return bool(row and row["enabled"])

    async def toggle(self, chat_id: int) -> bool:
        """Переключает уведомления чата, возвращает новое состояние."""
        await self._conn.execute(
            "UPDATE chats SET enabled = 1 - enabled WHERE chat_id = ?", (chat_id,)
        )
        await self._conn.commit()
        return await self.is_enabled(chat_id)

    async def active_chat_ids(self) -> list[int]:
        cur = await self._conn.execute("SELECT chat_id FROM chats WHERE enabled = 1")
        return [row["chat_id"] for row in await cur.fetchall()]

    async def all_chat_ids(self) -> list[int]:
        cur = await self._conn.execute("SELECT chat_id FROM chats")
        return [row["chat_id"] for row in await cur.fetchall()]


class SubscriptionRepo:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def get_states(self, chat_id: int, exchange: str) -> dict[tuple[str, str], bool]:
        """{(rubric_id, attr_id): enabled}; attr_id='' — сама рубрика."""
        cur = await self._conn.execute(
            "SELECT rubric_id, attr_id, enabled FROM subscriptions "
            "WHERE chat_id = ? AND exchange = ?",
            (chat_id, exchange),
        )
        return {
            (row["rubric_id"], row["attr_id"]): bool(row["enabled"])
            for row in await cur.fetchall()
        }

    async def toggle(self, chat_id: int, exchange: str, rubric_id: str,
                     attr_id: str = "") -> None:
        await self._conn.execute(
            "UPDATE subscriptions SET enabled = 1 - enabled "
            "WHERE chat_id = ? AND exchange = ? AND rubric_id = ? AND attr_id = ?",
            (chat_id, exchange, rubric_id, attr_id),
        )
        await self._conn.commit()

    async def enabled_rubrics(self, chat_id: int, exchange: str) -> dict[str, set[str]]:
        """Включённые рубрики чата: {rubric_id: множество включённых attr_id}."""
        states = await self.get_states(chat_id, exchange)
        result: dict[str, set[str]] = {}
        for (rubric_id, attr_id), enabled in states.items():
            if attr_id == "" and enabled:
                result.setdefault(rubric_id, set())
        for (rubric_id, attr_id), enabled in states.items():
            if attr_id and enabled and rubric_id in result:
                result[rubric_id].add(attr_id)
        # рубрика без единой включённой подрубрики не опрашивается
        return {r: attrs for r, attrs in result.items() if attrs}


class SeenOrdersRepo:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def has_any(self, exchange: str) -> bool:
        cur = await self._conn.execute(
            "SELECT 1 FROM seen_orders WHERE exchange = ? LIMIT 1", (exchange,)
        )
        return await cur.fetchone() is not None

    async def filter_new(self, exchange: str, order_ids: Iterable[str]) -> set[str]:
        ids = list(order_ids)
        if not ids:
            return set()
        placeholders = ",".join("?" * len(ids))
        cur = await self._conn.execute(
            f"SELECT order_id FROM seen_orders WHERE exchange = ? "
            f"AND order_id IN ({placeholders})",
            (exchange, *ids),
        )
        seen = {row["order_id"] for row in await cur.fetchall()}
        return set(ids) - seen

    async def mark_seen(self, exchange: str, order_ids: Iterable[str]) -> None:
        await self._conn.executemany(
            "INSERT OR IGNORE INTO seen_orders (exchange, order_id) VALUES (?, ?)",
            [(exchange, oid) for oid in order_ids],
        )
        await self._conn.commit()

    async def cleanup(self, days: int = 30) -> None:
        await self._conn.execute(
            "DELETE FROM seen_orders WHERE seen_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        await self._conn.commit()
