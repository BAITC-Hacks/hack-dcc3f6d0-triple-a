"""SQLite persistence and repeatable demo fixtures."""

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib.parse import urlsplit

from rating import CARD_FIELDS, SCORE_GROUPS, confirmed_fields, is_meaningful, score_card

DB_PATH = Path(os.getenv("SANA_DB_PATH", Path(__file__).with_name("sana_hub.sqlite3")))


def connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    """Add missing schema only; never replace or reseed an existing database."""
    with closing(connect()) as db, db:
        existing = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('tasks','cards','teams','proposals')"
        ).fetchall()
        db.executescript("""
        CREATE TABLE IF NOT EXISTS business_profiles (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY, description TEXT NOT NULL,
            questions TEXT NOT NULL DEFAULT '{}', answers TEXT NOT NULL DEFAULT '{}',
            question_mode TEXT NOT NULL DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            business_id INTEGER REFERENCES business_profiles(id),
            suggestions TEXT NOT NULL DEFAULT '{}', suggestion_mode TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS cards (
            id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL UNIQUE REFERENCES tasks(id),
            title TEXT NOT NULL DEFAULT '', context TEXT NOT NULL DEFAULT '',
            need TEXT NOT NULL DEFAULT '', users TEXT NOT NULL DEFAULT '',
            data TEXT NOT NULL DEFAULT '', constraints TEXT NOT NULL DEFAULT '',
            outcome TEXT NOT NULL DEFAULT '', success TEXT NOT NULL DEFAULT '',
            contact TEXT NOT NULL DEFAULT '', interaction TEXT NOT NULL DEFAULT '',
            confirmed_fields TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, contact TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL REFERENCES cards(id),
            team_id INTEGER NOT NULL REFERENCES teams(id),
            idea TEXT NOT NULL, plan TEXT NOT NULL, link TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','accepted','declined')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(tasks)")}
        additions = {
            "business_id": "INTEGER REFERENCES business_profiles(id)",
            "suggestions": "TEXT NOT NULL DEFAULT '{}'",
            "suggestion_mode": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in additions.items():
            if name not in columns:
                db.execute(f"ALTER TABLE tasks ADD COLUMN {name} {definition}")
        business_id = _default_business_id(db)
        db.execute("UPDATE tasks SET business_id=? WHERE business_id IS NULL", (business_id,))
        if not existing:
            seed(db, business_id)


def _default_business_id(db):
    profile = db.execute("SELECT id FROM business_profiles WHERE name=?", ("Демо-бизнес",)).fetchone()
    if profile:
        return profile["id"]
    return db.execute("INSERT INTO business_profiles(name) VALUES (?)", ("Демо-бизнес",)).lastrowid


def seed(db, business_id=None):
    samples = [
        ("Демо: помощник агронома", "Синтетическое агрохозяйство собирает наблюдения о состоянии посевов.", "По культуре, погоде и симптомам нужен план осмотра на неделю.", "Агрономы хозяйства", "Синтетическая таблица культур, погодных наблюдений и симптомов для демонстрации.", "Работать только с демонстрационными данными; план проверяет агроном.", "Прототип помощника, формирующего недельный план по введённым сведениям.", "На 10 синтетических примерах план содержит действия на неделю и вопросы о недостающих сведениях.", "agro-demo@example.org", "Одна онлайн-встреча в неделю"),
        ("Помочь посетителям ориентироваться в библиотеке", "Посетители ищут книги в каталоге библиотеки.", "Нужна удобная навигация по разделам.", "Посетители библиотеки", "Публичный каталог книг.", "Прототип должен работать в браузере.", "Интерактивный поиск по разделам.", "Пользователь находит раздел за несколько шагов.", "demo2@example.org", "Общение в чате"),
        ("Собрать обратную связь о городских мероприятиях", "Организаторы собирают отзывы вручную.", "Нужно видеть частые темы отзывов.", "Организаторы мероприятий", "Пробный набор обезличенных отзывов.", "Только демонстрационные данные.", "Панель тем и отзывов.", "Видны основные темы на пробной выборке.", "demo3@example.org", "Созвон по запросу"),
        ("Улучшить запись на консультации", "", "Нужен удобный способ записи.", "Посетители учебного центра", "", "Для демонстрации использовать только синтетические контакты.", "Веб-форма записи на доступное время консультации.", "", "", ""),
        ("Сделать помощника для волонтёров", "", "", "", "", "", "", "", "", ""),
    ]
    business_id = business_id or _default_business_id(db)
    card_ids = []
    for index, values in enumerate(samples):
        title, *other = values
        description = f"Демонстрационная задача: {title}."
        task_id = db.execute("INSERT INTO tasks(description,business_id) VALUES (?,?)", (description, business_id)).lastrowid
        confirmed = (
            list(CARD_FIELDS),
            ["context", "need", "data", "outcome", "constraints", "users"],
            ["context", "need", "data", "outcome"],
            ["outcome", "users", "constraints"],
            [],
        )[index]
        card_ids.append(db.execute(
            "INSERT INTO cards(task_id,title,context,need,users,data,constraints,outcome,success,contact,interaction,confirmed_fields,status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (task_id, title, *other, json.dumps(confirmed), "published" if index < 4 else "draft"),
        ).lastrowid)
    for index in range(1, 6):
        team_id = db.execute("INSERT INTO teams(name,contact) VALUES (?,?)", (f"Демо-команда {index}", f"team{index}@example.org")).lastrowid
        db.execute(
            "INSERT INTO proposals(card_id,team_id,idea,plan,link) VALUES (?,?,?,?,?)",
            (card_ids[(index - 1) % 4], team_id, f"Демонстрационная идея команды {index}", "Уточнить требования, собрать прототип, показать результат.", f"https://example.org/demo-{index}"),
        )


def rows(query, parameters=()):
    with closing(connect()) as db, db:
        return [dict(row) for row in db.execute(query, parameters).fetchall()]


def one(query, parameters=()):
    result = rows(query, parameters)
    return result[0] if result else None


def _required_text(value, label):
    if not is_meaningful(value):
        raise ValueError(f"{label}: заполните содержательно, без заглушек.")
    return value.strip()


def _get_card(db, card_id):
    card = db.execute("SELECT * FROM cards WHERE id=?", (card_id,)).fetchone()
    if card is None:
        raise ValueError("Карточка не найдена.")
    return dict(card)


def create_task(description, questions, mode, business_id=None):
    description = _required_text(description, "Черновик")
    if not isinstance(questions, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in questions.items()):
        raise ValueError("Вопросы должны быть словарём текстовых полей.")
    with closing(connect()) as db, db:
        business_id = business_id if business_id is not None else _default_business_id(db)
        if not db.execute("SELECT id FROM business_profiles WHERE id=?", (business_id,)).fetchone():
            raise ValueError("Профиль бизнеса не найден.")
        task_id = db.execute(
            "INSERT INTO tasks(description,questions,question_mode,business_id) VALUES (?,?,?,?)",
            (description, json.dumps(questions, ensure_ascii=False), mode, business_id),
        ).lastrowid
        db.execute("INSERT INTO cards(task_id) VALUES (?)", (task_id,))
        return task_id


def save_answers(task_id, answers):
    if not isinstance(answers, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in answers.items()):
        raise ValueError("Ответы должны содержать текст.")
    with closing(connect()) as db, db:
        if not db.execute("UPDATE tasks SET answers=? WHERE id=?", (json.dumps(answers, ensure_ascii=False), task_id)).rowcount:
            raise ValueError("Черновик не найден.")


def save_card(card_id, values, confirmed, status):
    """Save manual edits; changing a previously confirmed value revokes consent."""
    if status not in ("draft", "published"):
        raise ValueError("Неизвестный статус публикации.")
    if not isinstance(values, dict) or any(field not in CARD_FIELDS or not isinstance(value, str) for field, value in values.items()):
        raise ValueError("Карточка содержит неизвестное поле или нетекстовое значение.")
    if not isinstance(confirmed, (list, tuple, set)) or any(field not in CARD_FIELDS for field in confirmed):
        raise ValueError("Неизвестное поле подтверждения.")
    columns = ",".join(f"{field}=?" for field in CARD_FIELDS)
    with closing(connect()) as db, db:
        previous = _get_card(db, card_id)
        cleaned = {field: values.get(field, previous[field]).strip() for field in CARD_FIELDS}
        if status == "published":
            _required_text(cleaned["title"], "Название для публикации")
        old_confirmed = confirmed_fields(previous)
        reset = [field for field in CARD_FIELDS if field in old_confirmed and cleaned[field] != previous[field]]
        valid_confirmed = [field for field in CARD_FIELDS if field in confirmed and field not in reset and is_meaningful(cleaned[field])]
        db.execute(
            f"UPDATE cards SET {columns},confirmed_fields=?,status=? WHERE id=?",
            (*[cleaned[field] for field in CARD_FIELDS], json.dumps(valid_confirmed), status, card_id),
        )
        return reset


def save_suggestions(task_id, fields, mode, sources):
    if not isinstance(fields, dict) or any(field not in CARD_FIELDS or not isinstance(value, str) for field, value in fields.items()):
        raise ValueError("Предложение полей имеет неверный формат.")
    payload = json.dumps({"fields": fields, "sources": sources}, ensure_ascii=False)
    with closing(connect()) as db, db:
        if not db.execute("UPDATE tasks SET suggestions=?,suggestion_mode=? WHERE id=?", (payload, mode, task_id)).rowcount:
            raise ValueError("Черновик не найден.")


def apply_suggestions(card_id, fields):
    """Copy useful suggestions into empty fields, never overwrite human input."""
    if not isinstance(fields, dict) or any(field not in CARD_FIELDS or not isinstance(value, str) for field, value in fields.items()):
        raise ValueError("Предложение полей имеет неверный формат.")
    with closing(connect()) as db, db:
        card = _get_card(db, card_id)
        applied = [field for field in CARD_FIELDS if not card[field].strip() and is_meaningful(fields.get(field, ""))]
        if applied:
            kept_confirmed = [field for field in CARD_FIELDS if field in confirmed_fields(card) and field not in applied and is_meaningful(card[field])]
            assignments = ",".join(f"{field}=?" for field in applied)
            db.execute(
                f"UPDATE cards SET {assignments},confirmed_fields=? WHERE id=?",
                (*[fields[field].strip() for field in applied], json.dumps(kept_confirmed), card_id),
            )
        return applied


def set_publication(card_id, published):
    if not isinstance(published, bool):
        raise ValueError("Выберите состояние публикации.")
    with closing(connect()) as db, db:
        card = _get_card(db, card_id)
        if published:
            _required_text(card["title"], "Название для публикации")
        db.execute("UPDATE cards SET status=? WHERE id=?", ("published" if published else "draft", card_id))


def create_team(name, contact):
    name = _required_text(name, "Название команды")
    contact = _required_text(contact, "Контакт команды")
    with closing(connect()) as db, db:
        return db.execute("INSERT INTO teams(name,contact) VALUES (?,?)", (name, contact)).lastrowid


def _validated_link(link):
    link = _required_text(link, "Ссылка")
    try:
        parsed = urlsplit(link)
        valid = parsed.scheme in ("http", "https") and parsed.hostname and not parsed.username and not parsed.password
        _ = parsed.port  # Reject malformed ports before displaying the link.
    except ValueError:
        valid = False
    if not valid or any(character.isspace() for character in link):
        raise ValueError("Укажите корректную ссылку, начинающуюся с http:// или https://.")
    return link


def submit_proposal(card_id, team_id, idea, plan, link):
    idea = _required_text(idea, "Идея")
    plan = _required_text(plan, "План")
    link = _validated_link(link)
    with closing(connect()) as db, db:
        card = _get_card(db, card_id)
        if card["status"] != "published":
            raise ValueError("Отклик можно отправить только на опубликованную карточку.")
        if not db.execute("SELECT id FROM teams WHERE id=?", (team_id,)).fetchone():
            raise ValueError("Команда не найдена.")
        return db.execute(
            "INSERT INTO proposals(card_id,team_id,idea,plan,link) VALUES (?,?,?,?,?)",
            (card_id, team_id, idea, plan, link),
        ).lastrowid


def decide_proposal(proposal_id, status, business_id=None):
    if status not in ("pending", "accepted", "declined"):
        raise ValueError("Неизвестное решение по отклику.")
    with closing(connect()) as db, db:
        proposal = db.execute(
            "SELECT p.id,t.business_id FROM proposals p "
            "JOIN cards c ON c.id=p.card_id JOIN tasks t ON t.id=c.task_id WHERE p.id=?",
            (proposal_id,),
        ).fetchone()
        if proposal is None:
            raise ValueError("Отклик не найден.")
        if business_id is not None and proposal["business_id"] != business_id:
            raise ValueError("Решение доступно только владельцу задачи.")
        db.execute("UPDATE proposals SET status=? WHERE id=?", (status, proposal_id))
