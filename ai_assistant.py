"""AI-assisted task drafting with a deterministic offline fallback."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from utils import SKILLS, evaluate


CARD_KEYS = ("title", "problem", "goal", "result", "requirements", "deadline", "skills", "extra")


class AssistantServiceError(RuntimeError):
    """A safe, user-facing error for a failed remote AI request."""


def configured_api_key(secret_value: str | None = None) -> str | None:
    """Return a configured key without ever persisting or displaying it."""
    return (secret_value or os.getenv("OPENAI_API_KEY") or "").strip() or None


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Модель не вернула карточку в ожидаемом формате.")
    return json.loads(cleaned[start : end + 1])


def _normalize_card(card: dict[str, Any], brief: str) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key in CARD_KEYS:
        value = card.get(key, [] if key == "skills" else "")
        if key == "skills":
            if not isinstance(value, list):
                value = [str(value)] if value else []
            value = [skill for skill in value if skill in SKILLS][:4]
        else:
            value = str(value).strip()
        normalized[key] = value
    normalized["problem"] = normalized["problem"] or brief.strip()
    return normalized


def _infer_skills(text: str) -> list[str]:
    lowered = text.casefold()
    rules = {
        "Python": ("python", "анализ", "данн"),
        "AI / ML": ("ai", "ии", "модел", "чат-бот", "прогноз"),
        "Web": ("сайт", "веб", "платформ", "кабинет"),
        "Frontend": ("интерфейс", "экран", "дизайн"),
        "Backend": ("api", "база данных", "интеграц"),
        "Data Analysis": ("анализ", "отчёт", "дашборд", "метрик"),
        "Design": ("дизайн", "ux", "ui", "прототип"),
        "Mobile": ("мобил", "android", "ios", "приложение"),
    }
    detected = [skill for skill, words in rules.items() if any(word in lowered for word in words)]
    return detected[:4] or ["Web", "Design"]


def _offline_card(brief: str) -> dict[str, Any]:
    compact = " ".join(brief.strip().split())
    first_sentence = re.split(r"[.!?]", compact, maxsplit=1)[0].strip()
    title_words = first_sentence.split()[:8]
    title = " ".join(title_words).strip().capitalize()
    if len(title) < 12:
        title = "Цифровое решение для бизнес-задачи"
    return {
        "title": title[:100],
        "problem": compact,
        "goal": "Сократить время на текущий процесс и сделать результат прозрачным и измеримым для бизнеса.",
        "result": "Работающий MVP, краткая инструкция запуска и демонстрация основного сценария на тестовых данных.",
        "requirements": "Решение должно запускаться локально, использовать обезличенные данные и иметь понятную инструкцию для бизнеса.",
        "deadline": "4 недели",
        "skills": _infer_skills(compact),
        "extra": "Перед стартом команда уточняет доступные данные, метрику успеха и формат итоговой демонстрации.",
    }


def generate_task_card(
    brief: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[dict[str, Any], str]:
    """Create a structured card and return it with the active assistant mode."""
    if len(brief.strip()) < 30:
        raise ValueError("Опишите задачу чуть подробнее — минимум 30 символов.")
    key = configured_api_key(api_key)
    if not key:
        return _offline_card(brief), "demo"

    from openai import OpenAI

    client = OpenAI(api_key=key, timeout=30.0, max_retries=1)
    prompt = f"""
Черновик бизнес-задачи:
{brief.strip()}

Верни только JSON-объект с ключами title, problem, goal, result, requirements,
deadline, skills, extra. В skills используй только значения из списка: {", ".join(SKILLS)}.
Не выдумывай факты: если деталей нет, формулируй их как предложение для уточнения.
"""
    try:
        response = client.responses.create(
            model=model or os.getenv("OPENAI_MODEL", "gpt-6-astra"),
            instructions=(
                "Ты AI-редактор практических бизнес-задач для студенческих команд. "
                "Пиши по-русски, ясно, конкретно и без маркетинговых штампов."
            ),
            input=prompt,
            store=False,
        )
        return _normalize_card(_extract_json(response.output_text), brief), "openai"
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        raise AssistantServiceError(
            "OpenAI сейчас недоступен. Проверьте API-ключ, доступ к модели и подключение, затем повторите попытку."
        ) from exc


def review_task_card(
    draft: dict[str, Any],
    *,
    api_key: str | None = None,
    model: str | None = None,
) -> tuple[str, str]:
    """Return a concise editorial review for a draft card."""
    assessment = evaluate(draft)
    key = configured_api_key(api_key)
    if not key:
        weak = assessment["improvements"][:3]
        if not weak:
            return (
                "Карточка уже готова к публикации. Перед стартом уточните с командой одну измеримую метрику успеха.",
                "demo",
            )
        return "\n".join(f"• {item}" for item in weak), "demo"

    from openai import OpenAI

    client = OpenAI(api_key=key, timeout=30.0, max_retries=1)
    try:
        response = client.responses.create(
            model=model or os.getenv("OPENAI_MODEL", "gpt-6-astra"),
            instructions=(
                "Ты редактор бизнес-задач. Дай ровно 3 кратких и конкретных совета по-русски. "
                "Не пересказывай всю карточку и не выдумывай данные."
            ),
            input=json.dumps(draft, ensure_ascii=False),
            store=False,
        )
        text = response.output_text.strip()
        if not text:
            raise ValueError("empty response")
        return text, "openai"
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        raise AssistantServiceError(
            "OpenAI сейчас недоступен. Проверьте API-ключ, доступ к модели и подключение, затем повторите попытку."
        ) from exc
