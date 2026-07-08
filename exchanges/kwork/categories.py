"""Рубрики kwork.ru/projects. ID проверены по window.stateData (июль 2026).

default_enabled соответствует выбору пользователя: рубрики 37/39/79 целиком,
в 41 — только ИИ-агенты, в 46 — только Telegram, в 113 — только Сбор данных.
"""
from exchanges.base import Rubric, SubRubric

RUBRICS: tuple[Rubric, ...] = (
    Rubric("37", "Создание сайта", (
        SubRubric("5016", "Новый сайт"),
        SubRubric("5017", "Копия сайта"),
    )),
    Rubric("39", "Мобильные приложения", (
        SubRubric("1405", "iOS"),
        SubRubric("1406", "Android"),
    )),
    Rubric("41", "Скрипты, боты и mini apps", (
        SubRubric("5548694", "ИИ-агенты"),
        SubRubric("211", "Парсеры", default_enabled=False),
        SubRubric("3587", "Чат-боты", default_enabled=False),
        SubRubric("7352", "Скрипты", default_enabled=False),
        SubRubric("3934090", "Telegram Mini Apps", default_enabled=False),
        SubRubric("4158112", "ИИ-боты", default_enabled=False),
        SubRubric("4158119", "Машинное обучение", default_enabled=False),
        SubRubric("5503256", "Интернет вещей (IoT)", default_enabled=False),
    )),
    Rubric("46", "Соцсети и SMM", (
        SubRubric("281", "Telegram"),
        SubRubric("242", "ВКонтакте", default_enabled=False),
        SubRubric("265", "Youtube", default_enabled=False),
        SubRubric("5273900", "MAX", default_enabled=False),
        SubRubric("273", "Одноклассники", default_enabled=False),
        SubRubric("7912", "Дзен", default_enabled=False),
        SubRubric("411064", "TikTok", default_enabled=False),
        SubRubric("3118203", "Rutube", default_enabled=False),
        SubRubric("5293031", "VC.ru", default_enabled=False),
        SubRubric("5293041", "Reddit", default_enabled=False),
        SubRubric("302", "Другие", default_enabled=False),
    )),
    Rubric("79", "Верстка", (
        SubRubric("224", "Верстка по макету"),
        SubRubric("226", "Доработка и адаптация верстки"),
    )),
    Rubric("113", "Базы данных и клиентов", (
        SubRubric("1116", "Сбор данных"),
        SubRubric("1117", "Готовые базы", default_enabled=False),
        SubRubric("1118", "Проверка, чистка базы", default_enabled=False),
    )),
)
