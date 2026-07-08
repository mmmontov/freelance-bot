from pathlib import Path

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS subscriptions (
    chat_id  INTEGER NOT NULL,
    exchange TEXT    NOT NULL,
    rubric_id TEXT   NOT NULL,
    attr_id  TEXT    NOT NULL DEFAULT '',  -- '' = сама рубрика
    enabled  INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (chat_id, exchange, rubric_id, attr_id)
);

CREATE TABLE IF NOT EXISTS seen_orders (
    exchange TEXT NOT NULL,
    order_id TEXT NOT NULL,
    seen_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (exchange, order_id)
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self._path = path
        self.conn: aiosqlite.Connection | None = None

    async def connect(self) -> aiosqlite.Connection:
        self.conn = await aiosqlite.connect(self._path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()
        return self.conn

    async def close(self) -> None:
        if self.conn is not None:
            await self.conn.close()
            self.conn = None
