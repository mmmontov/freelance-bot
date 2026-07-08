import html
import logging
import re

from aiogram import Bot

from bot.keyboards import order_kb
from exchanges.base import Order

logger = logging.getLogger(__name__)

DESCRIPTION_LIMIT = 300


def format_order(order: Order, exchange_title: str) -> str:
    description = _clean_description(order.description)
    if len(description) > DESCRIPTION_LIMIT:
        cut = description[:DESCRIPTION_LIMIT]
        space = cut.rfind(" ")
        if space > DESCRIPTION_LIMIT * 0.6:
            cut = cut[:space]
        description = cut.rstrip() + "…"

    price = _fmt_price(order.price)
    if order.price_max and order.price_max != order.price:
        price += f" (макс. {_fmt_price(order.price_max)})"

    lines = [
        f"🆕 <b>{html.escape(exchange_title)}</b> · {html.escape(order.rubric_title)}",
        "",
        f"<b>{html.escape(order.title)}</b>",
    ]
    if description:
        lines += ["", f"<blockquote>{html.escape(description)}</blockquote>"]
    lines += ["", f"💰 До {price}"]
    if order.time_left:
        lines.append(f"⏳ Осталось: {order.time_left}")
    lines.append(f"📋 Предложений: {order.offers_count}")
    lines += ["", f'🔗 <a href="{order.url}">Открыть заказ</a>']
    return "\n".join(lines)


def _clean_description(text: str) -> str:
    """Заказы приходят с HTML-сущностями и \\r\\n из редактора kwork."""
    text = html.unescape(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    cleaned: list[str] = []
    for ln in lines:
        if ln or (cleaned and cleaned[-1]):
            cleaned.append(ln)
    return "\n".join(cleaned).strip()


def _fmt_price(value: float | None) -> str:
    if value is None:
        return "не указана"
    return f"{value:,.0f} ₽".replace(",", " ")


async def send_order(bot: Bot, chat_id: int, order: Order,
                     exchange_title: str) -> None:
    try:
        await bot.send_message(
            chat_id,
            format_order(order, exchange_title),
            disable_web_page_preview=True,
            reply_markup=order_kb(),
        )
    except Exception:
        logger.exception("Не удалось отправить заказ %s в чат %s",
                         order.order_id, chat_id)
