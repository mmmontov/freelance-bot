"""Форматирование уведомлений о заказах.

Тексты заказов приходят из kwork в «грязном» виде: HTML-сущности, \\r\\n из
редактора, неразрывные пробелы. Из-за этого уже был баг с &nbsp; в сообщениях,
поэтому чистка описания покрыта подробно.
"""
import pytest

from bot.notifications import (
    DESCRIPTION_LIMIT,
    _clean_description,
    _fmt_price,
    format_order,
    send_order,
)


class TestCleanDescription:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # то, из-за чего всё началось: &nbsp; → обычный пробел
            ("Привет&nbsp;мир", "Привет мир"),
            ("Ставка&nbsp;&nbsp;5000", "Ставка 5000"),
            # прочие HTML-сущности
            ("Цена &lt; 1000 &amp; больше", "Цена < 1000 & больше"),
            ("&quot;кавычки&quot;", '"кавычки"'),
            # переводы строк из виндового редактора
            ("первая\r\nвторая", "первая\nвторая"),
            ("первая\rвторая", "первая\nвторая"),
            # табы и повторяющиеся пробелы внутри строки схлопываются
            ("много\t\t   пробелов", "много пробелов"),
            # несколько пустых строк подряд → максимум одна
            ("абзац\n\n\n\nвторой", "абзац\n\nвторой"),
            # пробелы по краям строк и всего текста срезаются
            ("   \n\n  Привет  \n\n  ", "Привет"),
            ("", ""),
            ("   ", ""),
        ],
    )
    def test_cleanup(self, raw, expected):
        assert _clean_description(raw) == expected

    def test_nbsp_never_survives(self):
        """Регрессия: в готовом тексте не должно остаться \\xa0 ни в каком виде."""
        cleaned = _clean_description("a&nbsp;b\xa0c")
        assert "\xa0" not in cleaned
        assert cleaned == "a b c"

    def test_single_newline_between_paragraphs_kept(self):
        assert _clean_description("один\nдва\nтри") == "один\nдва\nтри"


class TestFmtPrice:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, "не указана"),
            (0.0, "0 ₽"),
            (500.0, "500 ₽"),
            (1500.0, "1 500 ₽"),
            (1500.7, "1 501 ₽"),        # округление до целых
            (1234567.0, "1 234 567 ₽"),
        ],
    )
    def test_format(self, value, expected):
        assert _fmt_price(value) == expected

    def test_thousands_separator_is_space_not_comma(self):
        assert "," not in _fmt_price(1500.0)


class TestFormatOrder:
    def test_contains_key_fields(self, make_order):
        order = make_order("42", title="Бот для записи", rubric_title="Скрипты и боты",
                           price=5000.0, time_left="2 дня", offers_count=7)
        text = format_order(order, "Kwork")

        assert "Kwork" in text
        assert "Скрипты и боты" in text
        assert "Бот для записи" in text
        assert "5 000 ₽" in text
        assert "2 дня" in text
        assert "Предложений: 7" in text
        assert order.url in text

    def test_escapes_html_in_title_and_description(self, make_order):
        """Parse mode у бота — HTML, так что скрейпленный текст обязан escape-иться,
        иначе <b> из описания заказа поедет как разметка и сломает сообщение."""
        order = make_order("1", title="<b>жирный</b> & <i>косой</i>",
                           description="<script>alert(1)</script> & сравнение a < b")
        text = format_order(order, "Kwork")

        assert "<b>жирный</b>" not in text
        assert "&lt;b&gt;жирный&lt;/b&gt;" in text
        assert "<script>" not in text
        assert "&lt;script&gt;" in text

    def test_escapes_html_in_exchange_title(self, make_order):
        text = format_order(make_order("1"), "<Kwork>")
        assert "&lt;Kwork&gt;" in text

    def test_price_max_shown_when_different(self, make_order):
        text = format_order(make_order("1", price=1000.0, price_max=5000.0), "Kwork")
        assert "1 000 ₽" in text
        assert "макс. 5 000 ₽" in text

    def test_price_max_hidden_when_equal(self, make_order):
        text = format_order(make_order("1", price=1000.0, price_max=1000.0), "Kwork")
        assert "макс." not in text

    def test_price_max_hidden_when_absent(self, make_order):
        text = format_order(make_order("1", price=1000.0, price_max=None), "Kwork")
        assert "макс." not in text

    def test_missing_price(self, make_order):
        text = format_order(make_order("1", price=None), "Kwork")
        assert "не указана" in text

    def test_empty_description_has_no_blockquote(self, make_order):
        text = format_order(make_order("1", description=""), "Kwork")
        assert "<blockquote>" not in text

    def test_description_in_blockquote(self, make_order):
        text = format_order(make_order("1", description="Нужен бот"), "Kwork")
        assert "<blockquote>Нужен бот</blockquote>" in text

    def test_empty_time_left_line_omitted(self, make_order):
        text = format_order(make_order("1", time_left=""), "Kwork")
        assert "Осталось" not in text

    def test_long_description_truncated_with_ellipsis(self, make_order):
        long = " ".join(["слово"] * 200)          # заведомо больше лимита
        text = format_order(make_order("1", description=long), "Kwork")

        body = text.split("<blockquote>")[1].split("</blockquote>")[0]
        assert body.endswith("…")
        assert len(body) <= DESCRIPTION_LIMIT + 1

    def test_truncation_keeps_whole_words(self, make_order):
        long = " ".join(["слово"] * 200)
        text = format_order(make_order("1", description=long), "Kwork")

        body = text.split("<blockquote>")[1].split("</blockquote>")[0]
        # обрезали по границе слова → последнее слово не рублёное
        assert body.rstrip("…").split()[-1] == "слово"

    def test_short_description_not_truncated(self, make_order):
        text = format_order(make_order("1", description="Коротко"), "Kwork")
        assert "…" not in text

    def test_description_without_spaces_still_truncated(self, make_order):
        """Нет пробелов → резать по границе слова некуда, но лимит держим."""
        text = format_order(make_order("1", description="я" * 500), "Kwork")

        body = text.split("<blockquote>")[1].split("</blockquote>")[0]
        assert body.endswith("…")
        assert len(body) <= DESCRIPTION_LIMIT + 1


class TestSendOrder:
    async def test_sends_with_keyboard_and_sound(self, bot, make_order):
        order = make_order("777", exchange="kwork")
        await send_order(bot, 555, order, "Kwork")

        assert len(bot.sent) == 1
        msg = bot.sent[0]
        assert msg["chat_id"] == 555
        assert msg["disable_notification"] is False
        assert msg["disable_web_page_preview"] is True
        # под уведомлением должна быть кнопка черновика с id этого заказа
        assert msg["reply_markup"] is not None
        payload = msg["reply_markup"].inline_keyboard[0][0].callback_data
        assert "777" in payload
        assert "kwork" in payload

    async def test_silent_flag_forwarded(self, bot, make_order):
        await send_order(bot, 555, make_order("1"), "Kwork", silent=True)
        assert bot.sent[0]["disable_notification"] is True

    async def test_telegram_error_is_swallowed(self, broken_bot, make_order):
        """Падение отправки в один чат не должно ронять весь цикл рассылки."""
        await send_order(broken_bot, 555, make_order("1"), "Kwork")   # не бросает
        assert broken_bot.sent == []
