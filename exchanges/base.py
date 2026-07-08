from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SubRubric:
    id: str
    title: str
    default_enabled: bool = True


@dataclass(frozen=True)
class Rubric:
    id: str
    title: str
    subrubrics: tuple[SubRubric, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Order:
    exchange: str
    order_id: str
    title: str
    description: str
    price: float | None        # желаемый бюджет
    price_max: float | None    # допустимый максимум
    url: str
    rubric_id: str
    rubric_title: str
    time_left: str
    offers_count: int


class BaseExchange(ABC):
    """Контракт биржи фриланса. Новая биржа = новый класс + запись в registry."""

    name: str   # машинное имя ("kwork")
    title: str  # отображаемое имя ("Kwork")

    @abstractmethod
    def rubrics(self) -> tuple[Rubric, ...]:
        """Дерево рубрик и подрубрик для меню и дефолтных подписок."""

    @abstractmethod
    async def fetch_orders(self, rubric_id: str, attr_ids: set[str]) -> list[Order]:
        """Свежие заказы рубрики, новые первыми.

        attr_ids — включённые подрубрики; если включены все, реализация
        может не передавать фильтр в запросе.
        """
