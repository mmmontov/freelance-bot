"""Инлайн-клавиатуры и схема callback-данных.

Вся навигация бота ездит через один MenuCb, поэтому тут два типа проверок:
структура кнопок и — важнее — что упакованные callback_data влезают в лимит
Telegram (64 байта). Превышение лимита Telegram не прощает: кнопка просто
перестаёт работать, причём молча.
"""
import pytest

from bot.keyboards import MenuCb, draft_kb, exchange_menu, main_menu, order_kb, rubric_menu

CALLBACK_DATA_LIMIT = 64      # жёсткий лимит Telegram Bot API


class TestMenuCb:
    def test_round_trip(self):
        packed = MenuCb(action="draft", exchange="kwork", rubric="41", attr="211",
                        order_id="1122334").pack()
        restored = MenuCb.unpack(packed)

        assert restored.action == "draft"
        assert restored.exchange == "kwork"
        assert restored.rubric == "41"
        assert restored.attr == "211"
        assert restored.order_id == "1122334"

    def test_optional_fields_default_to_empty(self):
        restored = MenuCb.unpack(MenuCb(action="main").pack())

        assert restored.action == "main"
        assert restored.exchange == ""
        assert restored.order_id == ""

    @pytest.mark.parametrize(
        "action",
        ["main", "exch", "rubric", "t_notify", "t_silent", "t_rubric", "t_attr",
         "draft", "redraft", "del_order", "close"],
    )
    def test_every_action_fits_telegram_limit(self, action):
        """Считаем по максимуму: самый длинный из реальных id рубрик/подрубрик
        и 10-значный id заказа с запасом на рост."""
        packed = MenuCb(action=action, exchange="kwork", rubric="5503256",
                        attr="5548694", order_id="1234567890").pack()

        assert len(packed.encode("utf-8")) <= CALLBACK_DATA_LIMIT, packed

    def test_real_kwork_ids_fit(self):
        from exchanges.kwork.categories import RUBRICS

        for rubric in RUBRICS:
            for sub in rubric.subrubrics:
                packed = MenuCb(action="t_attr", exchange="kwork", rubric=rubric.id,
                                attr=sub.id, order_id="9999999").pack()
                assert len(packed.encode("utf-8")) <= CALLBACK_DATA_LIMIT, packed


class TestOrderKeyboard:
    def test_has_draft_and_delete(self):
        kb = order_kb("kwork", "42")
        row = kb.inline_keyboard[0]

        assert len(row) == 2
        assert "Черновик" in row[0].text
        assert "Удалить" in row[1].text

    def test_draft_button_carries_order_reference(self):
        """Без exchange+order_id хендлер не найдёт заказ в кэше."""
        cb = MenuCb.unpack(order_kb("kwork", "42").inline_keyboard[0][0].callback_data)

        assert cb.action == "draft"
        assert cb.exchange == "kwork"
        assert cb.order_id == "42"

    def test_delete_button_needs_no_order(self):
        cb = MenuCb.unpack(order_kb("kwork", "42").inline_keyboard[0][1].callback_data)
        assert cb.action == "del_order"

    def test_single_row(self):
        assert len(order_kb("kwork", "42").inline_keyboard) == 1


class TestDraftKeyboard:
    def test_has_regenerate_and_delete(self):
        row = draft_kb("kwork", "42").inline_keyboard[0]

        assert len(row) == 2
        assert "Перегенерировать" in row[0].text
        assert "Удалить" in row[1].text

    def test_regenerate_keeps_order_reference(self):
        """Перегенерация должна знать тот же заказ, иначе черновик будет не о том."""
        cb = MenuCb.unpack(draft_kb("kwork", "42").inline_keyboard[0][0].callback_data)

        assert cb.action == "redraft"
        assert cb.exchange == "kwork"
        assert cb.order_id == "42"

    def test_delete_action_shared_with_order_keyboard(self):
        draft_del = MenuCb.unpack(
            draft_kb("kwork", "42").inline_keyboard[0][1].callback_data
        )
        order_del = MenuCb.unpack(
            order_kb("kwork", "42").inline_keyboard[0][1].callback_data
        )
        assert draft_del.action == order_del.action


class TestMainMenu:
    @pytest.mark.parametrize(
        ("notify", "expected"),
        [(True, "ВКЛ"), (False, "ВЫКЛ")],
    )
    def test_notify_state_visible(self, notify, expected, exchange):
        kb = main_menu(notify, False, [exchange])
        assert expected in kb.inline_keyboard[0][0].text

    @pytest.mark.parametrize(
        ("silent", "expected"),
        [(True, "Без звука"), (False, "Со звуком")],
    )
    def test_silent_state_visible(self, silent, expected, exchange):
        kb = main_menu(True, silent, [exchange])
        assert expected in kb.inline_keyboard[1][0].text

    def test_exchange_row_per_exchange(self, exchange):
        kb = main_menu(True, False, [exchange])
        texts = [row[0].text for row in kb.inline_keyboard]

        assert any(exchange.title in text for text in texts)

    def test_has_close_button(self, exchange):
        kb = main_menu(True, False, [exchange])
        cb = MenuCb.unpack(kb.inline_keyboard[-1][0].callback_data)

        assert cb.action == "close"

    def test_toggles_are_separate_buttons(self, exchange):
        """Уведомления и звук — независимые тумблеры, каждый со своим action."""
        kb = main_menu(True, False, [exchange])

        assert MenuCb.unpack(kb.inline_keyboard[0][0].callback_data).action == "t_notify"
        assert MenuCb.unpack(kb.inline_keyboard[1][0].callback_data).action == "t_silent"


class TestExchangeMenu:
    def test_row_per_rubric_with_settings_button(self, exchange):
        kb = exchange_menu(exchange, {})
        rubric_rows = kb.inline_keyboard[:-1]      # последняя строка — «Назад»

        assert len(rubric_rows) == len(exchange.rubrics())
        assert all(len(row) == 2 for row in rubric_rows)

    def test_enabled_and_disabled_marks(self, exchange):
        kb = exchange_menu(exchange, {("r1", ""): True, ("r2", ""): False})

        assert kb.inline_keyboard[0][0].text.startswith("✅")
        assert kb.inline_keyboard[1][0].text.startswith("🔕")

    def test_missing_state_treated_as_off(self, exchange):
        kb = exchange_menu(exchange, {})
        assert kb.inline_keyboard[0][0].text.startswith("🔕")

    def test_gear_opens_rubric(self, exchange):
        cb = MenuCb.unpack(exchange_menu(exchange, {}).inline_keyboard[0][1].callback_data)

        assert cb.action == "rubric"
        assert cb.rubric == "r1"

    def test_back_goes_to_main(self, exchange):
        kb = exchange_menu(exchange, {})
        cb = MenuCb.unpack(kb.inline_keyboard[-1][0].callback_data)

        assert cb.action == "main"


class TestRubricMenu:
    def test_row_per_subrubric(self, exchange):
        kb = rubric_menu(exchange, "r1", {})
        assert len(kb.inline_keyboard) == 2 + 1        # две подрубрики + «Назад»

    def test_subrubric_marks(self, exchange):
        kb = rubric_menu(exchange, "r1", {("r1", "a1"): True, ("r1", "a2"): False})

        assert kb.inline_keyboard[0][0].text.startswith("✅")
        assert kb.inline_keyboard[1][0].text.startswith("🔕")

    def test_toggle_carries_rubric_and_attr(self, exchange):
        cb = MenuCb.unpack(rubric_menu(exchange, "r1", {}).inline_keyboard[0][0].callback_data)

        assert cb.action == "t_attr"
        assert cb.rubric == "r1"
        assert cb.attr == "a1"

    def test_back_returns_to_exchange(self, exchange):
        kb = rubric_menu(exchange, "r1", {})
        cb = MenuCb.unpack(kb.inline_keyboard[-1][0].callback_data)

        assert cb.action == "exch"
        assert cb.exchange == exchange.name

    def test_unknown_rubric_raises(self, exchange):
        with pytest.raises(StopIteration):
            rubric_menu(exchange, "нет-такой", {})
