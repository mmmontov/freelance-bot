"""Репозитории поверх SQLite. Каждый тест получает пустую базу в памяти."""
import pytest

from exchanges.base import Rubric, SubRubric


class TestChatRepo:
    async def test_register_creates_chat(self, chat_repo, exchange):
        assert await chat_repo.exists(1) is False
        await chat_repo.register(1, [exchange])
        assert await chat_repo.exists(1) is True

    async def test_notifications_on_by_default(self, chat_repo, exchange):
        await chat_repo.register(1, [exchange])
        assert await chat_repo.is_enabled(1) is True

    async def test_sound_on_by_default(self, chat_repo, exchange):
        await chat_repo.register(1, [exchange])
        assert await chat_repo.is_silent(1) is False

    async def test_register_is_idempotent(self, chat_repo, exchange, sub_repo):
        """Повторный /start не должен сбрасывать настройки чата."""
        await chat_repo.register(1, [exchange])
        await chat_repo.toggle(1)                    # выключили уведомления
        await sub_repo.toggle(1, exchange.name, "r1")  # и одну рубрику

        await chat_repo.register(1, [exchange])

        assert await chat_repo.is_enabled(1) is False
        states = await sub_repo.get_states(1, exchange.name)
        assert states[("r1", "")] is False

    async def test_register_applies_default_subscriptions(self, chat_repo, sub_repo,
                                                          exchange):
        await chat_repo.register(1, [exchange])
        states = await sub_repo.get_states(1, exchange.name)

        assert states[("r1", "")] is True        # сама рубрика включена
        assert states[("r1", "a1")] is True      # default_enabled=True
        assert states[("r3", "c1")] is False     # default_enabled=False

    async def test_toggle_returns_new_state(self, chat_repo, exchange):
        await chat_repo.register(1, [exchange])
        assert await chat_repo.toggle(1) is False
        assert await chat_repo.toggle(1) is True

    async def test_toggle_silent_returns_new_state(self, chat_repo, exchange):
        await chat_repo.register(1, [exchange])
        assert await chat_repo.toggle_silent(1) is True
        assert await chat_repo.toggle_silent(1) is False

    async def test_toggles_are_independent(self, chat_repo, exchange):
        await chat_repo.register(1, [exchange])
        await chat_repo.toggle_silent(1)
        assert await chat_repo.is_enabled(1) is True   # звук не влияет на уведомления

    async def test_unknown_chat_is_not_enabled(self, chat_repo):
        assert await chat_repo.is_enabled(999) is False
        assert await chat_repo.is_silent(999) is False

    async def test_chat_id_lists(self, chat_repo, exchange):
        for chat_id in (1, 2, 3):
            await chat_repo.register(chat_id, [exchange])
        await chat_repo.toggle(2)          # 2 — уведомления выключены
        await chat_repo.toggle_silent(3)   # 3 — без звука

        assert sorted(await chat_repo.all_chat_ids()) == [1, 2, 3]
        assert sorted(await chat_repo.active_chat_ids()) == [1, 3]
        assert await chat_repo.silent_chat_ids() == {3}

    async def test_lists_empty_on_fresh_db(self, chat_repo):
        assert await chat_repo.all_chat_ids() == []
        assert await chat_repo.active_chat_ids() == []
        assert await chat_repo.silent_chat_ids() == set()


class TestSubscriptionRepo:
    async def test_toggle_rubric(self, chat_repo, sub_repo, exchange):
        await chat_repo.register(1, [exchange])
        await sub_repo.toggle(1, exchange.name, "r1")

        states = await sub_repo.get_states(1, exchange.name)
        assert states[("r1", "")] is False
        assert states[("r1", "a1")] is True    # подрубрики не затронуты

    async def test_toggle_subrubric(self, chat_repo, sub_repo, exchange):
        await chat_repo.register(1, [exchange])
        await sub_repo.toggle(1, exchange.name, "r1", "a1")

        states = await sub_repo.get_states(1, exchange.name)
        assert states[("r1", "a1")] is False
        assert states[("r1", "a2")] is True
        assert states[("r1", "")] is True

    async def test_states_isolated_between_chats(self, chat_repo, sub_repo, exchange):
        await chat_repo.register(1, [exchange])
        await chat_repo.register(2, [exchange])
        await sub_repo.toggle(1, exchange.name, "r1")

        assert (await sub_repo.get_states(2, exchange.name))[("r1", "")] is True

    async def test_states_isolated_between_exchanges(self, chat_repo, sub_repo, exchange):
        await chat_repo.register(1, [exchange])
        assert await sub_repo.get_states(1, "other") == {}

    async def test_enabled_rubrics_returns_enabled_attrs(self, chat_repo, sub_repo,
                                                         exchange):
        await chat_repo.register(1, [exchange])
        enabled = await sub_repo.enabled_rubrics(1, exchange.name)

        assert enabled == {"r1": {"a1", "a2"}, "r2": {"b1"}}

    async def test_rubric_with_all_attrs_off_is_excluded(self, chat_repo, sub_repo,
                                                         exchange):
        """r3 — все подрубрики выключены по умолчанию, опрашивать её незачем."""
        await chat_repo.register(1, [exchange])
        assert "r3" not in await sub_repo.enabled_rubrics(1, exchange.name)

    async def test_disabling_last_attr_drops_rubric(self, chat_repo, sub_repo, exchange):
        await chat_repo.register(1, [exchange])
        await sub_repo.toggle(1, exchange.name, "r2", "b1")

        assert "r2" not in await sub_repo.enabled_rubrics(1, exchange.name)

    async def test_attrs_ignored_when_rubric_off(self, chat_repo, sub_repo, exchange):
        """Выключенная рубрика не опрашивается, даже если подрубрики включены."""
        await chat_repo.register(1, [exchange])
        await sub_repo.toggle(1, exchange.name, "r1")

        enabled = await sub_repo.enabled_rubrics(1, exchange.name)
        assert "r1" not in enabled

    async def test_enabled_rubrics_empty_for_unknown_chat(self, sub_repo, exchange):
        assert await sub_repo.enabled_rubrics(999, exchange.name) == {}

    async def test_rubric_without_subrubrics_never_polled(self, chat_repo, sub_repo,
                                                          make_exchange):
        """Известное свойство enabled_rubrics: рубрика без подрубрик отсеивается,
        т.к. множество включённых attr_id пустое. Если появится биржа с плоским
        деревом рубрик — этот тест покраснеет и напомнит поправить логику."""
        flat = make_exchange((Rubric("flat", "Без подрубрик", ()),))
        await chat_repo.register(1, [flat])

        assert await sub_repo.enabled_rubrics(1, flat.name) == {}


class TestSeenOrdersRepo:
    async def test_has_any_false_on_empty(self, seen_repo):
        assert await seen_repo.has_any("kwork") is False

    async def test_has_any_after_mark(self, seen_repo):
        await seen_repo.mark_seen("kwork", {"1"})
        assert await seen_repo.has_any("kwork") is True

    async def test_has_any_is_per_exchange(self, seen_repo):
        await seen_repo.mark_seen("kwork", {"1"})
        assert await seen_repo.has_any("habr") is False

    async def test_filter_new_returns_unseen_only(self, seen_repo):
        await seen_repo.mark_seen("kwork", {"1", "2"})
        assert await seen_repo.filter_new("kwork", ["1", "2", "3"]) == {"3"}

    async def test_filter_new_with_empty_input(self, seen_repo):
        assert await seen_repo.filter_new("kwork", []) == set()

    async def test_filter_new_all_unseen(self, seen_repo):
        assert await seen_repo.filter_new("kwork", ["1", "2"]) == {"1", "2"}

    async def test_filter_new_is_per_exchange(self, seen_repo):
        """Дедуп идёт по (биржа, id) — одинаковые id на разных биржах не конфликтуют."""
        await seen_repo.mark_seen("kwork", {"1"})
        assert await seen_repo.filter_new("habr", ["1"]) == {"1"}

    async def test_mark_seen_is_idempotent(self, seen_repo):
        await seen_repo.mark_seen("kwork", {"1"})
        await seen_repo.mark_seen("kwork", {"1"})    # не должно упасть на PK
        assert await seen_repo.filter_new("kwork", ["1"]) == set()

    async def test_cleanup_removes_old_only(self, seen_repo, conn):
        await seen_repo.mark_seen("kwork", {"old", "fresh"})
        await conn.execute(
            "UPDATE seen_orders SET seen_at = datetime('now', '-40 days') "
            "WHERE order_id = 'old'"
        )
        await conn.commit()

        await seen_repo.cleanup(days=30)

        assert await seen_repo.filter_new("kwork", ["old"]) == {"old"}   # забыт
        assert await seen_repo.filter_new("kwork", ["fresh"]) == set()   # помнит


class TestOrderCacheRepo:
    async def test_round_trip(self, order_cache, make_order):
        order = make_order("42", exchange="kwork", title="Бот",
                           description="Описание", rubric_title="Скрипты",
                           url="https://kwork.ru/projects/42")
        await order_cache.cache(order)

        got = await order_cache.get("kwork", "42")
        assert got is not None
        assert got.order_id == "42"
        assert got.title == "Бот"
        assert got.description == "Описание"
        assert got.rubric_title == "Скрипты"
        assert got.url == "https://kwork.ru/projects/42"

    async def test_get_missing_returns_none(self, order_cache):
        assert await order_cache.get("kwork", "нет-такого") is None

    async def test_get_is_per_exchange(self, order_cache, make_order):
        await order_cache.cache(make_order("42", exchange="kwork"))
        assert await order_cache.get("habr", "42") is None

    async def test_cache_keeps_first_version(self, order_cache, make_order):
        """INSERT OR IGNORE: повторный вызов не перезаписывает уже сохранённое."""
        await order_cache.cache(make_order("42", exchange="kwork", title="Первый"))
        await order_cache.cache(make_order("42", exchange="kwork", title="Второй"))

        got = await order_cache.get("kwork", "42")
        assert got.title == "Первый"

    async def test_cache_twice_does_not_raise(self, order_cache, make_order):
        order = make_order("42", exchange="kwork")
        await order_cache.cache(order)
        await order_cache.cache(order)

    @pytest.mark.parametrize("field", ["price", "price_max", "rubric_id", "offers_count"])
    async def test_fields_not_stored_come_back_as_stubs(self, order_cache, make_order,
                                                        field):
        """Кэш хранит только то, что нужно генератору черновика (title/description);
        цена, срок и счётчик предложений возвращаются заглушками — это осознанно,
        и черновик на них не опирается."""
        await order_cache.cache(make_order("42", exchange="kwork", price=1000.0,
                                           price_max=5000.0, offers_count=7))
        got = await order_cache.get("kwork", "42")

        assert getattr(got, field) in (None, "", 0)

    async def test_cleanup_removes_old_only(self, order_cache, conn, make_order):
        await order_cache.cache(make_order("old", exchange="kwork"))
        await order_cache.cache(make_order("fresh", exchange="kwork"))
        await conn.execute(
            "UPDATE order_cache SET cached_at = datetime('now', '-40 days') "
            "WHERE order_id = 'old'"
        )
        await conn.commit()

        await order_cache.cleanup(days=30)

        assert await order_cache.get("kwork", "old") is None
        assert await order_cache.get("kwork", "fresh") is not None


class TestDefaultSubscriptionsMatchCategories:
    async def test_subrubric_default_flags_are_honoured(self, chat_repo, sub_repo,
                                                        make_exchange):
        """Дефолты подписок берутся из default_enabled в дереве рубрик биржи."""
        custom = make_exchange((
            Rubric("x", "Рубрика X", (
                SubRubric("on", "Включена", default_enabled=True),
                SubRubric("off", "Выключена", default_enabled=False),
            )),
        ))
        await chat_repo.register(1, [custom])

        states = await sub_repo.get_states(1, custom.name)
        assert states[("x", "on")] is True
        assert states[("x", "off")] is False
