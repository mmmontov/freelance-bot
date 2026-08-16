"""Генерация черновика отклика.

Groq в тестах не вызывается — вместо клиента подставляется заглушка, которая
записывает переданный промпт. Проверяем именно то, что мы контролируем: сборку
промпта, подмешивание профиля стиля и ограничения длины в инструкции.
"""
from types import SimpleNamespace

import pytest

from bot import draftgen
from bot.draftgen import MODEL, SYSTEM_PROMPT, _load_style_profile, generate_draft


class FakeGroq:
    """Заглушка AsyncGroq: копит kwargs вызова и отдаёт заранее заданный текст."""

    def __init__(self, content: str = "Готов взяться, есть похожий опыт.") -> None:
        self.content = content
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )

    async def _create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )

    @property
    def last(self) -> dict:
        return self.calls[-1]

    def system_prompt(self) -> str:
        return self.last["messages"][0]["content"]

    def user_prompt(self) -> str:
        return self.last["messages"][1]["content"]


@pytest.fixture
def client():
    return FakeGroq()


@pytest.fixture
def no_style_profile(monkeypatch, tmp_path):
    """Профиль стиля отсутствует (как в свежем клоне без data/)."""
    monkeypatch.setattr(draftgen, "STYLE_PROFILE_PATH", tmp_path / "нет.md")


@pytest.fixture
def style_profile(monkeypatch, tmp_path):
    """Фабрика: кладёт профиль стиля на диск и указывает на него модуль."""
    path = tmp_path / "style_profile.md"
    monkeypatch.setattr(draftgen, "STYLE_PROFILE_PATH", path)

    def _write(text: str) -> None:
        path.write_text(text, encoding="utf-8")

    _write.path = path
    return _write


class TestLoadStyleProfile:
    def test_missing_file_returns_empty(self, no_style_profile):
        """Профиль лежит только в gitignore-нутом data/ — в CI и в свежем клоне
        его нет, и это не должно ломать генерацию."""
        assert _load_style_profile() == ""

    def test_reads_file(self, style_profile):
        style_profile("## Стек\nPython, aiogram")
        assert _load_style_profile() == "## Стек\nPython, aiogram"

    def test_strips_surrounding_whitespace(self, style_profile):
        style_profile("\n\n  Профиль  \n\n")
        assert _load_style_profile() == "Профиль"

    def test_empty_file_returns_empty(self, style_profile):
        style_profile("   \n  ")
        assert _load_style_profile() == ""


class TestGenerateDraft:
    async def test_returns_model_text(self, client, make_order, no_style_profile):
        client.content = "  Есть опыт с marzban, уточню детали.  "
        draft = await generate_draft(client, make_order("1"))

        assert draft == "Есть опыт с marzban, уточню детали."

    async def test_uses_configured_model(self, client, make_order, no_style_profile):
        await generate_draft(client, make_order("1"))
        assert client.last["model"] == MODEL

    async def test_caps_output_tokens(self, client, make_order, no_style_profile):
        """Лимит токенов — вторая линия обороны по длине, помимо инструкции,
        и заодно экономия бесплатной квоты Groq."""
        await generate_draft(client, make_order("1"))
        assert client.last["max_completion_tokens"] == 150

    async def test_message_roles(self, client, make_order, no_style_profile):
        await generate_draft(client, make_order("1"))
        roles = [m["role"] for m in client.last["messages"]]

        assert roles == ["system", "user"]

    async def test_order_passed_in_user_message(self, client, make_order,
                                               no_style_profile):
        order = make_order("1", title="Бот для записи",
                           description="Нужен aiogram и Google Sheets")
        await generate_draft(client, order)

        user = client.user_prompt()
        assert "Бот для записи" in user
        assert "Нужен aiogram и Google Sheets" in user

    async def test_system_prompt_used_as_base(self, client, make_order,
                                             no_style_profile):
        await generate_draft(client, make_order("1"))
        assert client.system_prompt() == SYSTEM_PROMPT

    async def test_empty_description_does_not_break(self, client, make_order,
                                                    no_style_profile):
        await generate_draft(client, make_order("1", description=""))
        assert client.calls


class TestStyleProfileInjection:
    async def test_profile_appended_to_system_prompt(self, client, make_order,
                                                     style_profile):
        style_profile("## Стек\nPython, FastAPI, aiogram")
        await generate_draft(client, make_order("1"))

        system = client.system_prompt()
        assert system.startswith(SYSTEM_PROMPT)
        assert "Python, FastAPI, aiogram" in system

    async def test_profile_goes_to_system_not_user(self, client, make_order,
                                                   style_profile):
        style_profile("Секретный профиль")
        await generate_draft(client, make_order("1"))

        assert "Секретный профиль" not in client.user_prompt()

    async def test_profile_reread_on_every_call(self, client, make_order,
                                                style_profile):
        """Задокументированное поведение: data/style_profile.md читается заново
        на каждый вызов, чтобы правки применялись без пересборки контейнера."""
        style_profile("Первая версия профиля")
        await generate_draft(client, make_order("1"))

        style_profile("Вторая версия профиля")
        await generate_draft(client, make_order("2"))

        assert "Первая версия" in client.calls[0]["messages"][0]["content"]
        assert "Вторая версия" in client.calls[1]["messages"][0]["content"]

    async def test_no_profile_leaves_prompt_untouched(self, client, make_order,
                                                     no_style_profile):
        await generate_draft(client, make_order("1"))
        assert client.system_prompt() == SYSTEM_PROMPT


class TestPromptConstraints:
    """Инструкции, за которые пришлось отдельно бороться. Если кто-то сократит
    промпт и потеряет их — черновики поедут в прежние болячки."""

    def test_length_limits_spelled_out(self):
        assert "150" in SYSTEM_PROMPT
        assert "250" in SYSTEM_PROMPT

    def test_forbids_retelling_the_order(self):
        assert "пересказ" in SYSTEM_PROMPT.lower()

    def test_forbids_boilerplate_greeting(self):
        assert "Здравствуйте, меня зовут" in SYSTEM_PROMPT

    def test_asks_for_russian(self):
        assert "русск" in SYSTEM_PROMPT.lower()
