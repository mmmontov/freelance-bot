"""Схема и миграции.

В проекте принято, что новые колонки досыпаются через ALTER TABLE в _migrate(),
т.к. CREATE TABLE IF NOT EXISTS не меняет уже существующую таблицу. Эти тесты
охраняют именно этот путь — на живом сервере база создана давно и проходит
только через миграции, а не через SCHEMA.
"""
import aiosqlite
import pytest

from storage.database import Database
from storage.repository import ChatRepo


async def test_connect_creates_all_tables(conn):
    cur = await conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    tables = {row["name"] for row in await cur.fetchall()}

    assert {"chats", "subscriptions", "seen_orders", "order_cache"} <= tables


async def test_row_factory_allows_named_access(conn):
    await conn.execute("INSERT INTO chats (chat_id) VALUES (1)")
    cur = await conn.execute("SELECT chat_id FROM chats")
    row = await cur.fetchone()

    assert row["chat_id"] == 1     # репозитории всюду обращаются по имени колонки


async def test_migrate_adds_silent_column_to_old_db(tmp_path):
    """База, созданная до появления беззвучного режима, должна дожить до новой
    колонки без потери данных."""
    path = tmp_path / "legacy.db"
    async with aiosqlite.connect(path) as legacy:
        await legacy.execute(
            "CREATE TABLE chats (chat_id INTEGER PRIMARY KEY, "
            "enabled INTEGER NOT NULL DEFAULT 1)"
        )
        await legacy.execute("INSERT INTO chats (chat_id, enabled) VALUES (42, 0)")
        await legacy.commit()

    db = Database(path)
    conn = await db.connect()
    try:
        cur = await conn.execute("SELECT enabled, silent FROM chats WHERE chat_id = 42")
        row = await cur.fetchone()
        assert row["enabled"] == 0     # старые настройки на месте
        assert row["silent"] == 0      # новая колонка с дефолтом
    finally:
        await db.close()


async def test_connect_twice_is_safe(tmp_path):
    """Миграции гоняются на каждом старте контейнера — повторный запуск не падает."""
    path = tmp_path / "bot.db"

    db = Database(path)
    conn = await db.connect()
    await ChatRepo(conn).register(1, [])
    await db.close()

    db = Database(path)
    conn = await db.connect()
    try:
        assert await ChatRepo(conn).exists(1) is True
    finally:
        await db.close()


async def test_close_is_idempotent(tmp_path):
    db = Database(tmp_path / "bot.db")
    await db.connect()
    await db.close()
    await db.close()
    assert db.conn is None


@pytest.mark.parametrize(
    ("table", "columns"),
    [
        ("chats", {"chat_id", "enabled", "silent"}),
        ("subscriptions", {"chat_id", "exchange", "rubric_id", "attr_id", "enabled"}),
        ("seen_orders", {"exchange", "order_id", "seen_at"}),
        ("order_cache", {"exchange", "order_id", "title", "description",
                         "rubric_title", "url", "cached_at"}),
    ],
)
async def test_table_columns(conn, table, columns):
    cur = await conn.execute(f"PRAGMA table_info({table})")
    actual = {row["name"] for row in await cur.fetchall()}

    assert actual == columns
