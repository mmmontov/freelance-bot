"""Реестр бирж. Чтобы добавить новую биржу: реализовать BaseExchange
и добавить экземпляр сюда."""
from exchanges.base import BaseExchange
from exchanges.kwork.provider import KworkExchange

EXCHANGES: dict[str, BaseExchange] = {
    e.name: e for e in (KworkExchange(),)
}
