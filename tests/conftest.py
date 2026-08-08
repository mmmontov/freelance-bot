"""Общие фикстуры для всех тестов.

Главное правило набора: ни один тест не ходит в сеть. kwork и Groq — внешние
сервисы с лимитами и антибот-защитой; если бы тесты их дёргали, CI краснел бы
из-за чужой недоступности, а не из-за нашего кода. Фикстура _forbid_network
делает это правило принудительным, а не устным договором.
"""
from pathlib import Path

import pytest

from exchanges.base import BaseExchange, Order, Rubric, SubRubric
from storage.database import Database
from storage.repository import (
    ChatRepo,
    OrderCacheRepo,
    SeenOrdersRepo,
    SubscriptionRepo,
)


@pytest.fixture(autouse=True)
def _forbid_network(monkeypatch):
    """Падаем с внятным сообщением, если тест полез в сеть."""

    def _boom(*args, **kwargs):
        raise AssertionError(
            "Тест попытался обратиться к внешнему сервису. Замокай "
            "KworkExchange._get или Groq-клиент вместо реального запроса."
        )

    monkeypatch.setattr("aiohttp.ClientSession", _boom)
    monkeypatch.setattr("groq.AsyncGroq", _boom)


# --------------------------------------------------------------------------- БД


@pytest.fixture
async def conn():
    """Свежая пустая база в памяти на каждый тест (со всей схемой и миграциями)."""
    db = Database(Path(":memory:"))
    connection = await db.connect()
    try:
        yield connection
    finally:
        await db.close()


@pytest.fixture
def chat_repo(conn):
    return ChatRepo(conn)


@pytest.fixture
def sub_repo(conn):
    return SubscriptionRepo(conn)


@pytest.fixture
def seen_repo(conn):
    return SeenOrdersRepo(conn)


@pytest.fixture
def order_cache(conn):
    return OrderCacheRepo(conn)


# ---------------------------------------------------------------- фейковая биржа

FAKE_RUBRICS: tuple[Rubric, ...] = (
    Rubric("r1", "Рубрика 1", (
        SubRubric("a1", "Подрубрика A1"),
        SubRubric("a2", "Подрубрика A2"),
    )),
    Rubric("r2", "Рубрика 2", (
        SubRubric("b1", "Подрубрика B1"),
    )),
    # все подрубрики выключены по умолчанию → рубрика не должна опрашиваться
    Rubric("r3", "Рубрика 3", (
        SubRubric("c1", "Подрубрика C1", default_enabled=False),
    )),
)


class FakeExchange(BaseExchange):
    """Биржа-заглушка: отдаёт заранее подложенные заказы и пишет, о чём спросили."""

    name = "fake"
    title = "Fake Exchange"

    def __init__(self, rubrics: tuple[Rubric, ...] = FAKE_RUBRICS) -> None:
        self._rubrics = rubrics
        self.orders: dict[str, list[Order]] = {}
        self.calls: list[tuple[str, frozenset[str]]] = []
        self.fail_on: set[str] = set()

    def rubrics(self) -> tuple[Rubric, ...]:
        return self._rubrics

    async def fetch_orders(self, rubric_id: str, attr_ids: set[str]) -> list[Order]:
        self.calls.append((rubric_id, frozenset(attr_ids)))
        if rubric_id in self.fail_on:
            raise RuntimeError("биржа недоступна")
        return list(self.orders.get(rubric_id, []))


@pytest.fixture
def exchange():
    return FakeExchange()


@pytest.fixture
def make_exchange():
    """Фейковая биржа с произвольным деревом рубрик."""

    def _make(rubrics: tuple[Rubric, ...], name: str = "fake") -> FakeExchange:
        instance = FakeExchange(rubrics)
        instance.name = name
        return instance

    return _make


# ------------------------------------------------------------------- фабрики


@pytest.fixture
def make_order():
    """Фабрика Order с разумными дефолтами — в тестах задаём только то, что важно."""

    def _make(
        order_id: str,
        *,
        exchange: str = "fake",
        title: str | None = None,
        description: str = "Описание заказа",
        price: float | None = 1000.0,
        price_max: float | None = None,
        url: str | None = None,
        rubric_id: str = "r1",
        rubric_title: str = "Рубрика 1",
        time_left: str = "2 дня",
        offers_count: int = 3,
    ) -> Order:
        return Order(
            exchange=exchange,
            order_id=order_id,
            title=title if title is not None else f"Заказ {order_id}",
            description=description,
            price=price,
            price_max=price_max,
            url=url if url is not None else f"https://example.test/{order_id}",
            rubric_id=rubric_id,
            rubric_title=rubric_title,
            time_left=time_left,
            offers_count=offers_count,
        )

    return _make


class FakeBot:
    """Заглушка aiogram.Bot: копит отправленные сообщения вместо реальной отправки."""

    def __init__(self, fail: bool = False) -> None:
        self.sent: list[dict] = []
        self.fail = fail

    async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
        if self.fail:
            raise RuntimeError("telegram недоступен")
        self.sent.append({"chat_id": chat_id, "text": text, **kwargs})


@pytest.fixture
def bot():
    return FakeBot()


@pytest.fixture
def broken_bot():
    """Бот, у которого любая отправка падает — для проверки, что цикл выживает."""
    return FakeBot(fail=True)
