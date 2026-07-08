import asyncio
import json
import logging
import re

import aiohttp

from exchanges.base import BaseExchange, Order, Rubric
from exchanges.kwork.categories import RUBRICS

logger = logging.getLogger(__name__)

PROJECTS_URL = "https://kwork.ru/projects"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
STATE_RE = re.compile(r"window\.stateData\s*=\s*")


class KworkExchange(BaseExchange):
    name = "kwork"
    title = "Kwork"

    def __init__(self) -> None:
        self._rubrics_by_id = {r.id: r for r in RUBRICS}

    def rubrics(self) -> tuple[Rubric, ...]:
        return RUBRICS

    async def fetch_orders(self, rubric_id: str, attr_ids: set[str]) -> list[Order]:
        rubric = self._rubrics_by_id[rubric_id]
        params = {"c": rubric_id}
        # если включены все подрубрики — фильтр не нужен
        if attr_ids and attr_ids != {s.id for s in rubric.subrubrics}:
            params["attr"] = ",".join(sorted(attr_ids))

        html = await self._get(params)
        state = self._extract_state(html)
        wants = state.get("pagination", {}).get("data") or []
        return [self._parse_want(w, rubric) for w in wants]

    async def _get(self, params: dict) -> str:
        timeout = aiohttp.ClientTimeout(total=30)
        headers = {"User-Agent": USER_AGENT, "Accept-Language": "ru-RU,ru;q=0.9"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(PROJECTS_URL, params=params) as resp:
                resp.raise_for_status()
                return await resp.text()

    @staticmethod
    def _extract_state(html: str) -> dict:
        match = STATE_RE.search(html)
        if not match:
            raise ValueError("window.stateData не найден — kwork изменил страницу?")
        data, _ = json.JSONDecoder().raw_decode(html[match.end():])
        return data

    def _parse_want(self, want: dict, rubric: Rubric) -> Order:
        order_id = str(want["id"])
        return Order(
            exchange=self.name,
            order_id=order_id,
            title=want.get("name") or "",
            description=want.get("description") or "",
            price=_to_float(want.get("priceLimit")),
            price_max=_to_float(want.get("possiblePriceLimit")),
            url=f"https://kwork.ru/projects/{order_id}",
            rubric_id=rubric.id,
            rubric_title=rubric.title,
            time_left=want.get("timeLeft") or "",
            offers_count=int(want.get("kwork_count") or 0),
        )


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _demo() -> None:
    """Ручная проверка парсера: python -m exchanges.kwork.provider"""
    exchange = KworkExchange()
    for rubric_id, attrs in [("37", set()), ("41", {"5548694"})]:
        orders = await exchange.fetch_orders(rubric_id, attrs)
        print(f"--- рубрика {rubric_id}: {len(orders)} заказов")
        for o in orders[:3]:
            print(f"[{o.order_id}] {o.title} | {o.price} / {o.price_max} | "
                  f"{o.time_left} | {o.url}")
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(_demo())
