"""Readiness rules shared by the UI and SQLite writes; no AI decisions."""

import json
import re
import unicodedata

CARD_FIELDS = (
    "title", "context", "need", "users", "data", "constraints", "outcome",
    "success", "contact", "interaction",
)
LABELS = {
    "title": "Название",
    "context": "Контекст",
    "need": "Потребность",
    "users": "Пользователи",
    "data": "Доступные данные",
    "constraints": "Ограничения",
    "outcome": "Ожидаемый результат",
    "success": "Критерии успеха",
    "contact": "Контакт",
    "interaction": "Формат взаимодействия",
}
SCORE_GROUPS = (
    (("context", "need"), 20, "Контекст и потребность"),
    (("data",), 20, "Доступные данные"),
    (("outcome",), 15, "Ожидаемый результат"),
    (("success",), 15, "Критерии успеха"),
    (("constraints",), 10, "Ограничения"),
    (("users",), 10, "Пользователи"),
    (("contact", "interaction"), 10, "Контакт и взаимодействие"),
)
_PLACEHOLDERS = {
    "tbd", "todo", "to do", "to be determined", "n a", "na", "none", "null",
    "unknown", "not specified", "not available", "placeholder", "test", "xxx",
    "нет", "нет данных", "данных нет", "не знаю", "неизвестно", "не известно",
    "не указано", "не указан", "не указаны", "не определено", "не определены",
    "не заполнено", "не заполнен", "не заполнены", "уточнить", "нужно уточнить",
    "требует уточнения", "требуется уточнение", "пока неизвестно", "пока нет",
    "будет позже", "позже", "заглушка", "тест", "пример", "ваш ответ",
}


def is_meaningful(value):
    """Reject empty/punctuation-only values and explicit placeholders.

    This deliberately has no minimum word count: e.g. "Агрономы" is useful.
    It cannot establish truth; only a person can confirm the supplied facts.
    """
    if not isinstance(value, str):
        return False
    normalized = unicodedata.normalize("NFKC", value).casefold().replace("ё", "е")
    normalized = " ".join(re.findall(r"[^\W_]+", normalized, flags=re.UNICODE))
    return bool(normalized) and normalized not in _PLACEHOLDERS


def confirmed_fields(card):
    """Read old JSON records and in-memory card previews in the same way."""
    raw = dict(card).get("confirmed_fields", [])
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return set()
    if not isinstance(raw, (list, tuple, set)):
        return set()
    return {field for field in raw if isinstance(field, str) and field in CARD_FIELDS}


def readiness_level(score):
    if score < 40:
        return "черновик"
    if score < 70:
        return "рабочая постановка"
    if score < 90:
        return "готова"
    return "приоритетная"


def evaluate_card(card):
    card = dict(card)
    confirmed = confirmed_fields(card)
    score, breakdown, missing = 0, [], []
    for fields, maximum, criterion in SCORE_GROUPS:
        reasons = []
        for field in fields:
            value = card.get(field, "")
            if not isinstance(value, str) or not value.strip():
                reasons.append(f"{LABELS[field]}: не заполнено")
            elif not is_meaningful(value):
                reasons.append(f"{LABELS[field]}: замените заглушку содержательным ответом")
            elif field not in confirmed:
                reasons.append(f"{LABELS[field]}: подтвердите сведения вручную")
        earned = 0 if reasons else maximum
        score += earned
        reason = "; ".join(reasons) if reasons else "Все части заполнены и подтверждены человеком"
        breakdown.append({"criterion": criterion, "earned": earned, "maximum": maximum, "reason": reason})
        if reasons:
            missing.append(f"{criterion} (+{maximum}): {reason}")
    return {"score": score, "level": readiness_level(score), "breakdown": breakdown, "missing": missing}


def score_card(card):
    result = evaluate_card(card)
    return result["score"], result["missing"]
