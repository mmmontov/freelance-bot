"""Цикл опроса.

Здесь живёт главный инвариант проекта: биржи опрашиваются и seen_orders
обновляется для ВСЕХ чатов, независимо от тумблера уведомлений — гейтится
только сама отправка. Один раз это уже сломали, и при включении уведомлений
на чат разом свалилась вся накопившаяся пачка заказов. Тесты
TestNotifyToggleDoesNotAffectPolling — защита от повторения.
"""
import pytest

from watcher import watcher as watcher_module
from watcher.watcher import Watcher


@pytest.fixture(autouse=True)
def _no_throttling(monkeypatch):
    """Watcher намеренно спит 3-6 секунд между запросами к бирже, чтобы не
    попасть под антибот kwork. В тестах это лишние минуты — убираем сон,
    сохраняя саму логику."""

    async def instant_sleep(_seconds):
        return None

    monkeypatch.setattr(watcher_module.asyncio, "sleep", instant_sleep)


@pytest.fixture
def sent(monkeypatch):
    """Перехватывает send_order: нас интересует решение watcher'а «отправлять
    или нет», а не форматирование (оно покрыто в test_notifications)."""
    calls: list[dict] = []

    async def fake_send_order(bot, chat_id, order, exchange_title, silent=False):
        calls.append({"chat_id": chat_id, "order_id": order.order_id,
                      "exchange_title": exchange_title, "silent": silent})

    monkeypatch.setattr(watcher_module, "send_order", fake_send_order)
    return calls


@pytest.fixture
def make_watcher(bot, chat_repo, sub_repo, seen_repo, order_cache):
    def _make(exchange, interval=1):
        return Watcher(bot, {exchange.name: exchange}, chat_repo, sub_repo,
                       seen_repo, order_cache, interval)

    return _make


class TestBootstrap:
    async def test_first_run_sends_nothing(self, make_watcher, exchange, chat_repo,
                                           make_order, sent):
        """Иначе при первом старте в чат улетели бы все заказы, что сейчас на бирже."""
        await chat_repo.register(1, [exchange])
        exchange.orders["r1"] = [make_order("100"), make_order("101")]

        await make_watcher(exchange)._poll_all()

        assert sent == []

    async def test_first_run_marks_orders_seen(self, make_watcher, exchange, chat_repo,
                                              make_order, seen_repo, sent):
        await chat_repo.register(1, [exchange])
        exchange.orders["r1"] = [make_order("100"), make_order("101")]

        await make_watcher(exchange)._poll_all()

        assert await seen_repo.filter_new(exchange.name, ["100", "101"]) == set()

    async def test_second_run_sends_only_new(self, make_watcher, exchange, chat_repo,
                                             make_order, sent):
        await chat_repo.register(1, [exchange])
        watcher = make_watcher(exchange)

        exchange.orders["r1"] = [make_order("100")]
        await watcher._poll_all()                       # bootstrap

        exchange.orders["r1"] = [make_order("101"), make_order("100")]
        await watcher._poll_all()

        assert [c["order_id"] for c in sent] == ["101"]

    async def test_nothing_happens_without_chats(self, make_watcher, exchange,
                                                 make_order, sent):
        exchange.orders["r1"] = [make_order("100")]

        await make_watcher(exchange)._poll_all()

        assert exchange.calls == []      # ни одного запроса к бирже
        assert sent == []


class TestNotifyToggleDoesNotAffectPolling:
    """Регрессия на баг «включил уведомления — прилетела пачка старых заказов»."""

    async def test_polls_exchange_even_when_notifications_off(self, make_watcher,
                                                             exchange, chat_repo,
                                                             make_order, sent):
        await chat_repo.register(1, [exchange])
        await chat_repo.toggle(1)                       # уведомления выключены
        exchange.orders["r1"] = [make_order("100")]

        await make_watcher(exchange)._poll_all()

        assert exchange.calls, "биржу обязаны опрашивать и с выключенными уведомлениями"

    async def test_marks_seen_while_notifications_off(self, make_watcher, exchange,
                                                      chat_repo, make_order, seen_repo,
                                                      sent):
        await chat_repo.register(1, [exchange])
        watcher = make_watcher(exchange)

        exchange.orders["r1"] = [make_order("100")]
        await watcher._poll_all()                       # bootstrap

        await chat_repo.toggle(1)                       # выключили уведомления
        exchange.orders["r1"] = [make_order("101"), make_order("100")]
        await watcher._poll_all()

        assert sent == []                               # молчим, как и просили
        assert await seen_repo.filter_new(exchange.name, ["101"]) == set()

    async def test_no_backlog_dump_after_re_enabling(self, make_watcher, exchange,
                                                     chat_repo, make_order, sent):
        """Суть бага: после обратного включения не должно прилететь ничего из
        того, что появилось на бирже во время «тишины»."""
        await chat_repo.register(1, [exchange])
        watcher = make_watcher(exchange)

        exchange.orders["r1"] = [make_order("100")]
        await watcher._poll_all()                       # bootstrap

        await chat_repo.toggle(1)                       # выключили
        exchange.orders["r1"] = [make_order(str(i)) for i in range(200, 210)]
        await watcher._poll_all()                       # 10 заказов «пропущены»

        await chat_repo.toggle(1)                       # включили обратно
        await watcher._poll_all()

        assert sent == [], "накопленный бэклог не должен вываливаться пачкой"

    async def test_only_new_orders_arrive_after_re_enabling(self, make_watcher, exchange,
                                                            chat_repo, make_order, sent):
        await chat_repo.register(1, [exchange])
        watcher = make_watcher(exchange)

        exchange.orders["r1"] = [make_order("100")]
        await watcher._poll_all()

        await chat_repo.toggle(1)
        exchange.orders["r1"] = [make_order("200"), make_order("100")]
        await watcher._poll_all()

        await chat_repo.toggle(1)
        exchange.orders["r1"] = [make_order("300"), make_order("200"),
                                 make_order("100")]
        await watcher._poll_all()

        assert [c["order_id"] for c in sent] == ["300"]

    async def test_inactive_chat_does_not_block_active_one(self, make_watcher, exchange,
                                                           chat_repo, make_order, sent):
        await chat_repo.register(1, [exchange])
        await chat_repo.register(2, [exchange])
        await chat_repo.toggle(2)                       # второй чат молчит
        watcher = make_watcher(exchange)

        exchange.orders["r1"] = [make_order("100")]
        await watcher._poll_all()

        exchange.orders["r1"] = [make_order("101"), make_order("100")]
        await watcher._poll_all()

        assert [c["chat_id"] for c in sent] == [1]


class TestDelivery:
    async def test_chronological_order(self, make_watcher, exchange, chat_repo,
                                       make_order, sent):
        """Биржа отдаёт новые сверху, а в чат заказы должны идти снизу вверх —
        чтобы читались в том порядке, в котором появились."""
        await chat_repo.register(1, [exchange])
        watcher = make_watcher(exchange)

        exchange.orders["r1"] = [make_order("1")]
        await watcher._poll_all()

        exchange.orders["r1"] = [make_order("4"), make_order("3"), make_order("2"),
                                 make_order("1")]
        await watcher._poll_all()

        assert [c["order_id"] for c in sent] == ["2", "3", "4"]

    async def test_delivered_to_every_active_chat(self, make_watcher, exchange,
                                                  chat_repo, make_order, sent):
        for chat_id in (1, 2, 3):
            await chat_repo.register(chat_id, [exchange])
        watcher = make_watcher(exchange)

        exchange.orders["r1"] = [make_order("1")]
        await watcher._poll_all()

        exchange.orders["r1"] = [make_order("2"), make_order("1")]
        await watcher._poll_all()

        assert sorted(c["chat_id"] for c in sent) == [1, 2, 3]

    async def test_no_duplicate_when_order_in_two_rubrics(self, make_watcher, exchange,
                                                          chat_repo, make_order, sent):
        """Чат подписан и на r1, и на r2; один и тот же заказ может попасть в обе
        выдачи — доставить его нужно один раз."""
        await chat_repo.register(1, [exchange])
        watcher = make_watcher(exchange)

        exchange.orders["r1"] = [make_order("1")]
        await watcher._poll_all()

        duplicate = make_order("99")
        exchange.orders["r1"] = [duplicate, make_order("1")]
        exchange.orders["r2"] = [duplicate]
        await watcher._poll_all()

        assert [c["order_id"] for c in sent] == ["99"]

    async def test_silent_chats_get_silent_flag(self, make_watcher, exchange, chat_repo,
                                               make_order, sent):
        await chat_repo.register(1, [exchange])
        await chat_repo.register(2, [exchange])
        await chat_repo.toggle_silent(2)
        watcher = make_watcher(exchange)

        exchange.orders["r1"] = [make_order("1")]
        await watcher._poll_all()

        exchange.orders["r1"] = [make_order("2"), make_order("1")]
        await watcher._poll_all()

        flags = {c["chat_id"]: c["silent"] for c in sent}
        assert flags == {1: False, 2: True}

    async def test_exchange_title_passed_through(self, make_watcher, exchange,
                                                 chat_repo, make_order, sent):
        await chat_repo.register(1, [exchange])
        watcher = make_watcher(exchange)

        exchange.orders["r1"] = [make_order("1")]
        await watcher._poll_all()
        exchange.orders["r1"] = [make_order("2"), make_order("1")]
        await watcher._poll_all()

        assert sent[0]["exchange_title"] == exchange.title


class TestOrderCaching:
    async def test_delivered_orders_are_cached(self, make_watcher, exchange, chat_repo,
                                               make_order, order_cache, sent):
        """Без кэша кнопка «Черновик отклика» не найдёт данные заказа после
        перезапуска бота."""
        await chat_repo.register(1, [exchange])
        watcher = make_watcher(exchange)

        exchange.orders["r1"] = [make_order("1")]
        await watcher._poll_all()

        exchange.orders["r1"] = [make_order("2", title="Новый заказ"), make_order("1")]
        await watcher._poll_all()

        cached = await order_cache.get(exchange.name, "2")
        assert cached is not None
        assert cached.title == "Новый заказ"

    async def test_bootstrap_orders_are_not_cached(self, make_watcher, exchange,
                                                   chat_repo, make_order, order_cache,
                                                   sent):
        await chat_repo.register(1, [exchange])
        exchange.orders["r1"] = [make_order("1")]

        await make_watcher(exchange)._poll_all()

        assert await order_cache.get(exchange.name, "1") is None

    async def test_cached_even_when_all_chats_muted(self, make_watcher, exchange,
                                                    chat_repo, make_order, order_cache,
                                                    sent):
        """Кэширование идёт до проверки активности чата — заказ попадает в кэш
        даже если отправлять его сейчас некому."""
        await chat_repo.register(1, [exchange])
        watcher = make_watcher(exchange)

        exchange.orders["r1"] = [make_order("1")]
        await watcher._poll_all()

        await chat_repo.toggle(1)
        exchange.orders["r1"] = [make_order("2"), make_order("1")]
        await watcher._poll_all()

        assert await order_cache.get(exchange.name, "2") is not None


class TestSubscriptionFiltering:
    async def test_rubric_with_all_subrubrics_off_not_polled(self, make_watcher,
                                                             exchange, chat_repo,
                                                             make_order, sent):
        await chat_repo.register(1, [exchange])

        await make_watcher(exchange)._poll_all()

        polled = {rubric_id for rubric_id, _ in exchange.calls}
        assert polled == {"r1", "r2"}       # r3 выключена по умолчанию

    async def test_enabled_attrs_passed_to_exchange(self, make_watcher, exchange,
                                                    chat_repo, sub_repo, make_order,
                                                    sent):
        await chat_repo.register(1, [exchange])
        await sub_repo.toggle(1, exchange.name, "r1", "a2")   # оставили только a1

        await make_watcher(exchange)._poll_all()

        assert ("r1", frozenset({"a1"})) in exchange.calls

    async def test_identical_subscriptions_polled_once(self, make_watcher, exchange,
                                                       chat_repo, make_order, sent):
        """Три чата с одинаковыми подписками — один запрос к бирже на рубрику,
        иначе антибот-лимиты kwork улетят в трубу."""
        for chat_id in (1, 2, 3):
            await chat_repo.register(chat_id, [exchange])

        await make_watcher(exchange)._poll_all()

        assert len([c for c in exchange.calls if c[0] == "r1"]) == 1

    async def test_different_subscriptions_polled_separately(self, make_watcher,
                                                             exchange, chat_repo,
                                                             sub_repo, make_order, sent):
        await chat_repo.register(1, [exchange])
        await chat_repo.register(2, [exchange])
        await sub_repo.toggle(2, exchange.name, "r1", "a2")

        await make_watcher(exchange)._poll_all()

        r1_calls = {attrs for rubric_id, attrs in exchange.calls if rubric_id == "r1"}
        assert r1_calls == {frozenset({"a1", "a2"}), frozenset({"a1"})}


class TestErrorHandling:
    async def test_failing_rubric_does_not_block_others(self, make_watcher, exchange,
                                                        chat_repo, make_order, sent):
        await chat_repo.register(1, [exchange])
        watcher = make_watcher(exchange)

        exchange.orders["r1"] = [make_order("1")]
        exchange.orders["r2"] = [make_order("2")]
        await watcher._poll_all()                       # bootstrap

        exchange.fail_on = {"r1"}
        exchange.orders["r2"] = [make_order("3"), make_order("2")]
        await watcher._poll_all()

        assert [c["order_id"] for c in sent] == ["3"]

    async def test_failing_rubric_orders_stay_unseen(self, make_watcher, exchange,
                                                     chat_repo, make_order, seen_repo,
                                                     sent):
        """Упавший запрос не должен помечать заказы просмотренными — иначе они
        потеряются навсегда."""
        await chat_repo.register(1, [exchange])
        watcher = make_watcher(exchange)

        exchange.orders["r1"] = [make_order("1")]
        await watcher._poll_all()

        exchange.fail_on = {"r1"}
        exchange.orders["r1"] = [make_order("2"), make_order("1")]
        await watcher._poll_all()

        assert await seen_repo.filter_new(exchange.name, ["2"]) == {"2"}

    async def test_send_failure_does_not_break_cycle(self, exchange, chat_repo,
                                                     sub_repo, seen_repo, order_cache,
                                                     broken_bot, make_order):
        """send_order глотает ошибки Telegram — цикл обязан дойти до конца и
        пометить заказы просмотренными."""
        await chat_repo.register(1, [exchange])
        watcher = Watcher(broken_bot, {exchange.name: exchange}, chat_repo, sub_repo,
                          seen_repo, order_cache, 1)

        exchange.orders["r1"] = [make_order("1")]
        await watcher._poll_all()

        exchange.orders["r1"] = [make_order("2"), make_order("1")]
        await watcher._poll_all()

        assert await seen_repo.filter_new(exchange.name, ["2"]) == set()
