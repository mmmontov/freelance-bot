"""Парсер kwork.

У kwork нет JSON API — данные вынимаются из window.stateData, встроенного в HTML.
Это самая хрупкая часть проекта: вёрстка меняется на их стороне без предупреждения.
Тесты гоняются на сохранённом слепке страницы (tests/fixtures/kwork_projects.html),
живая сеть не используется — иначе CI зависел бы от доступности kwork и его
антибот-защиты.
"""
from pathlib import Path

import pytest

from exchanges.kwork.categories import RUBRICS
from exchanges.kwork.provider import KworkExchange, _to_float

FIXTURE = Path(__file__).parent / "fixtures" / "kwork_projects.html"


@pytest.fixture
def page() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture
def kwork(monkeypatch, page):
    """Биржа с подменённым HTTP-слоем: возвращает слепок и пишет параметры запроса."""
    exchange = KworkExchange()
    captured: dict = {}

    async def fake_get(self, params):
        captured["params"] = dict(params)
        return captured.get("html", page)

    monkeypatch.setattr(KworkExchange, "_get", fake_get)
    exchange.captured = captured
    return exchange


class TestExtractState:
    def test_finds_state_in_page(self, page):
        state = KworkExchange._extract_state(page)
        assert "pagination" in state

    def test_stops_at_end_of_object(self, page):
        """raw_decode должен взять только первый объект и не подавиться тем,
        что идёт после него в <script>."""
        state = KworkExchange._extract_state(page)
        assert "ignored" not in state

    def test_raises_when_state_missing(self):
        with pytest.raises(ValueError, match="stateData"):
            KworkExchange._extract_state("<html><body>ничего нет</body></html>")

    @pytest.mark.parametrize(
        "prefix",
        [
            'window.stateData = ',
            'window.stateData=',
            'window.stateData   =   ',
            'window.stateData\t=\t',
        ],
    )
    def test_tolerates_whitespace_variants(self, prefix):
        state = KworkExchange._extract_state(f"<script>{prefix}{{\"a\": 1}};</script>")
        assert state == {"a": 1}


class TestFetchOrders:
    async def test_parses_all_orders(self, kwork):
        orders = await kwork.fetch_orders("41", set())
        assert len(orders) == 3

    async def test_preserves_order_from_page(self, kwork):
        """Биржа отдаёт новые сверху; watcher рассчитывает на этот порядок."""
        orders = await kwork.fetch_orders("41", set())
        assert [o.order_id for o in orders] == ["1122334", "1122335", "1122336"]

    async def test_parses_fields(self, kwork):
        order = (await kwork.fetch_orders("41", set()))[0]

        assert order.exchange == "kwork"
        assert order.order_id == "1122334"
        assert order.title == "Написать Telegram-бота для записи на приём"
        assert order.price == 5000.0
        assert order.price_max == 15000.0
        assert order.time_left == "2 дня 4 часа"
        assert order.offers_count == 7

    async def test_price_comes_as_string_from_kwork(self, kwork):
        """priceLimit в stateData — строка, а не число; молча привести к float."""
        order = (await kwork.fetch_orders("41", set()))[0]
        assert isinstance(order.price, float)

    async def test_offers_count_as_string(self, kwork):
        order = (await kwork.fetch_orders("41", set()))[2]
        assert order.offers_count == 12

    async def test_url_built_from_id(self, kwork):
        order = (await kwork.fetch_orders("41", set()))[0]
        assert order.url == "https://kwork.ru/projects/1122334"

    async def test_rubric_meta_attached(self, kwork):
        """rubric_id/rubric_title в ответе биржи нет — их подставляет провайдер."""
        order = (await kwork.fetch_orders("41", set()))[0]
        assert order.rubric_id == "41"
        assert order.rubric_title == "Скрипты, боты и mini apps"

    async def test_missing_and_null_fields_get_defaults(self, kwork):
        order = (await kwork.fetch_orders("41", set()))[2]

        assert order.description == ""
        assert order.price is None          # priceLimit: null
        assert order.price_max is None      # ключа вообще нет
        assert order.time_left == ""

    async def test_description_kept_raw(self, kwork):
        """Провайдер не чистит текст — это делает слой уведомлений."""
        order = (await kwork.fetch_orders("41", set()))[0]
        assert "&nbsp;" in order.description

    async def test_empty_pagination_gives_empty_list(self, kwork, monkeypatch):
        async def empty_get(self, params):
            return '<script>window.stateData = {"pagination":{"data":[]}};</script>'

        monkeypatch.setattr(KworkExchange, "_get", empty_get)
        assert await kwork.fetch_orders("41", set()) == []

    async def test_null_data_gives_empty_list(self, kwork, monkeypatch):
        async def null_get(self, params):
            return '<script>window.stateData = {"pagination":{"data":null}};</script>'

        monkeypatch.setattr(KworkExchange, "_get", null_get)
        assert await kwork.fetch_orders("41", set()) == []

    async def test_missing_pagination_gives_empty_list(self, kwork, monkeypatch):
        async def bare_get(self, params):
            return '<script>window.stateData = {"userData":{}};</script>'

        monkeypatch.setattr(KworkExchange, "_get", bare_get)
        assert await kwork.fetch_orders("41", set()) == []

    async def test_unknown_rubric_raises(self, kwork):
        with pytest.raises(KeyError):
            await kwork.fetch_orders("нет-такой-рубрики", set())


class TestRequestParams:
    async def test_rubric_passed_as_c(self, kwork):
        await kwork.fetch_orders("37", set())
        assert kwork.captured["params"]["c"] == "37"

    async def test_no_attr_filter_when_all_subrubrics_enabled(self, kwork):
        """Если включены все подрубрики — фильтр не нужен, запрос короче."""
        rubric = next(r for r in RUBRICS if r.id == "37")
        await kwork.fetch_orders("37", {s.id for s in rubric.subrubrics})

        assert "attr" not in kwork.captured["params"]

    async def test_no_attr_filter_when_set_empty(self, kwork):
        await kwork.fetch_orders("37", set())
        assert "attr" not in kwork.captured["params"]

    async def test_attr_filter_for_subset(self, kwork):
        await kwork.fetch_orders("37", {"5016"})
        assert kwork.captured["params"]["attr"] == "5016"

    async def test_attr_filter_is_sorted(self, kwork):
        """Порядок фиксируем, чтобы запросы были детерминированными."""
        await kwork.fetch_orders("41", {"7352", "211", "3587"})
        assert kwork.captured["params"]["attr"] == "211,3587,7352"


class TestToFloat:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("5000", 5000.0),
            (5000, 5000.0),
            (5000.5, 5000.5),
            ("5000.5", 5000.5),
            (None, None),
            ("", None),
            ("бесплатно", None),
            ([], None),
        ],
    )
    def test_conversion(self, raw, expected):
        assert _to_float(raw) == expected


class TestCategoriesTree:
    """ID рубрик захардкожены (скопированы из stateData). Эти проверки ловят
    опечатки и копипасту при правке categories.py."""

    def test_rubrics_not_empty(self):
        assert RUBRICS

    def test_rubric_ids_unique(self):
        ids = [r.id for r in RUBRICS]
        assert len(ids) == len(set(ids))

    def test_subrubric_ids_unique_within_rubric(self):
        for rubric in RUBRICS:
            ids = [s.id for s in rubric.subrubrics]
            assert len(ids) == len(set(ids)), f"дубли подрубрик в рубрике {rubric.id}"

    def test_subrubric_ids_unique_globally(self):
        """kwork передаёт attr без указания рубрики, так что id должны не пересекаться."""
        ids = [s.id for rubric in RUBRICS for s in rubric.subrubrics]
        assert len(ids) == len(set(ids))

    def test_all_ids_are_numeric_strings(self):
        for rubric in RUBRICS:
            assert rubric.id.isdigit(), rubric.id
            for sub in rubric.subrubrics:
                assert sub.id.isdigit(), sub.id

    def test_every_rubric_has_title(self):
        for rubric in RUBRICS:
            assert rubric.title.strip()
            for sub in rubric.subrubrics:
                assert sub.title.strip()

    def test_every_rubric_has_at_least_one_default_subrubric(self):
        """Рубрика, где все подрубрики выключены, никогда не опрашивается
        (см. SubscriptionRepo.enabled_rubrics) — значит она бесполезна в меню
        по умолчанию. Если это осознанно, тест надо править вместе с деревом."""
        dead = [r.id for r in RUBRICS
                if r.subrubrics and not any(s.default_enabled for s in r.subrubrics)]
        assert dead == [], f"рубрики без включённых подрубрик: {dead}"

    def test_exchange_exposes_tree(self):
        assert KworkExchange().rubrics() is RUBRICS

    def test_registered_in_registry(self):
        from exchanges.registry import EXCHANGES

        assert "kwork" in EXCHANGES
        assert isinstance(EXCHANGES["kwork"], KworkExchange)
