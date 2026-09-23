"""Core rules and non-destructive migrations; every database is temporary."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import storage
from rating import CARD_FIELDS, evaluate_card, is_meaningful, readiness_level


def full_card():
    card = {field: f"Содержательные сведения: {field}" for field in CARD_FIELDS}
    card["confirmed_fields"] = json.dumps(list(CARD_FIELDS))
    return card


class RatingTests(unittest.TestCase):
    def test_all_groups_sum_to_100_and_unconfirmed_card_scores_zero(self):
        card = full_card()
        result = evaluate_card(card)
        self.assertEqual(result["score"], 100)
        self.assertEqual([row["maximum"] for row in result["breakdown"]], [20, 20, 15, 15, 10, 10, 10])
        self.assertEqual(result["missing"], [])
        card["confirmed_fields"] = "[]"
        self.assertEqual(evaluate_card(card)["score"], 0)

    def test_both_parts_of_group_are_required(self):
        for field, loss in (("context", 20), ("need", 20), ("contact", 10), ("interaction", 10)):
            with self.subTest(field=field):
                card = full_card()
                card[field] = ""
                self.assertEqual(evaluate_card(card)["score"], 100 - loss)
                card = full_card()
                card["confirmed_fields"] = json.dumps([other for other in CARD_FIELDS if other != field])
                self.assertEqual(evaluate_card(card)["score"], 100 - loss)

    def test_placeholders_never_receive_points(self):
        for value in ("", " \n ", "—", "...", "???", "TBD", "N/A", "не знаю", "Не указано!", "уточнить", "нет данных", "нет"):
            with self.subTest(value=value):
                self.assertFalse(is_meaningful(value))
                card = full_card()
                card["data"] = value
                self.assertEqual(evaluate_card(card)["score"], 80)
        for value in ("Агрономы", "AI", "Чат", "Данных пока нет: соберём 10 синтетических примеров до пятницы."):
            self.assertTrue(is_meaningful(value), value)

    def test_boundaries_and_russian_missing_reasons(self):
        for score, level in ((0, "черновик"), (39, "черновик"), (40, "рабочая постановка"), (69, "рабочая постановка"), (70, "готова"), (89, "готова"), (90, "приоритетная"), (100, "приоритетная")):
            self.assertEqual(readiness_level(score), level)
        result = evaluate_card({"context": "нет данных", "need": "Нужен помощник", "confirmed_fields": "[]"})
        reason = result["breakdown"][0]["reason"]
        self.assertIn("Контекст: замените заглушку", reason)
        self.assertIn("Потребность: подтвердите", reason)
        self.assertNotIn("need", reason)
        self.assertEqual(evaluate_card({"confirmed_fields": "broken json"})["score"], 0)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_path = Path(self.temp.name) / "test.sqlite3"
        self.database = patch.object(storage, "DB_PATH", self.db_path)
        self.database.start()
        self.addCleanup(self.database.stop)
        storage.init_db()

    def card(self, card_id):
        return storage.one("SELECT * FROM cards WHERE id=?", (card_id,))

    def new_card(self):
        task_id = storage.create_task("Помощник агронома: культура, погода, симптомы → план на неделю.", {"data": "Какие данные доступны?"}, "Локальный режим")
        return storage.one("SELECT * FROM cards WHERE task_id=?", (task_id,))

    def test_demo_seed_is_idempotent_and_varied(self):
        storage.init_db()
        for table in ("tasks", "cards", "teams", "proposals"):
            self.assertEqual(storage.one(f"SELECT COUNT(*) AS count FROM {table}")["count"], 5)
        self.assertEqual(sorted(storage.score_card(card)[0] for card in storage.rows("SELECT * FROM cards")), [0, 35, 55, 75, 100])
        self.assertEqual(storage.one("SELECT COUNT(*) AS count FROM business_profiles")["count"], 1)

    def test_changed_confirmed_field_loses_points_until_reconfirmed(self):
        card = self.new_card()
        values = {field: full_card()[field] for field in CARD_FIELDS}
        self.assertEqual(storage.save_card(card["id"], values, list(CARD_FIELDS), "draft"), [])
        self.assertEqual(storage.score_card(self.card(card["id"]))[0], 100)
        values["need"] = "Новое требование к помощнику агронома"
        self.assertEqual(storage.save_card(card["id"], values, list(CARD_FIELDS), "draft"), ["need"])
        self.assertEqual(storage.score_card(self.card(card["id"]))[0], 80)
        self.assertNotIn("need", json.loads(self.card(card["id"])["confirmed_fields"]))
        storage.save_card(card["id"], values, list(CARD_FIELDS), "draft")
        self.assertEqual(storage.score_card(self.card(card["id"]))[0], 100)
        values["data"] = "TBD"
        storage.save_card(card["id"], values, list(CARD_FIELDS), "draft")
        self.assertNotIn("data", json.loads(self.card(card["id"])["confirmed_fields"]))

    def test_apply_suggestions_preserves_manual_edits_and_confirmation(self):
        card = self.new_card()
        storage.save_card(card["id"], {"title": "Моё название", "need": "Моя формулировка"}, ["title", "need"], "draft")
        applied = storage.apply_suggestions(card["id"], {"title": "Название от AI", "need": "Другая потребность", "data": "Синтетическая таблица", "constraints": "не знаю"})
        self.assertEqual(applied, ["data"])
        saved = self.card(card["id"])
        self.assertEqual(saved["title"], "Моё название")
        self.assertEqual(saved["need"], "Моя формулировка")
        self.assertEqual(saved["constraints"], "")
        self.assertEqual(set(json.loads(saved["confirmed_fields"])), {"title", "need"})
        storage.apply_suggestions(card["id"], {"data": "Перезапись"})
        self.assertEqual(self.card(card["id"])["data"], "Синтетическая таблица")

    def test_low_score_publication_and_multiple_manual_decisions(self):
        card = self.new_card()
        storage.save_card(card["id"], {"title": "Помощник агронома"}, [], "draft")
        with self.assertRaises(ValueError):
            storage.submit_proposal(card["id"], 1, "Идея команды", "План команды", "https://example.org/proposal")
        storage.set_publication(card["id"], True)
        self.assertEqual(storage.score_card(self.card(card["id"]))[0], 0)
        first = storage.submit_proposal(card["id"], 1, "Идея команды", "План команды", "https://example.org/one")
        second = storage.submit_proposal(card["id"], 2, "Другая идея", "Другой план", "https://example.org/two")
        self.assertEqual(storage.one("SELECT status FROM proposals WHERE id=?", (first,))["status"], "pending")
        owner = storage.one("SELECT business_id FROM tasks WHERE id=?", (card["task_id"],))["business_id"]
        with self.assertRaises(ValueError):
            storage.decide_proposal(first, "accepted", owner + 100)
        for proposal_id in (first, second):
            storage.decide_proposal(proposal_id, "accepted", owner)
        self.assertEqual(storage.one("SELECT COUNT(*) AS count FROM proposals WHERE card_id=? AND status='accepted'", (card["id"],))["count"], 2)
        for proposal_id in (first, second):
            storage.decide_proposal(proposal_id, "declined", owner)
        self.assertEqual(storage.one("SELECT COUNT(*) AS count FROM proposals WHERE card_id=? AND status='accepted'", (card["id"],))["count"], 0)

    def test_input_validation_and_persistence_after_reinitialization(self):
        card = self.new_card()
        with self.assertRaises(ValueError):
            storage.set_publication(card["id"], True)
        with self.assertRaises(ValueError):
            storage.save_card(card["id"], {}, [], "unknown")
        storage.save_card(card["id"], {"title": "Сохраняемая карточка"}, [], "draft")
        storage.set_publication(card["id"], True)
        for link in ("javascript:alert(1)", "file:///local", "https://", "https://example.org:bad", "https://ex ample.org", "https://user:password@example.org"):
            with self.subTest(link=link), self.assertRaises(ValueError):
                storage.submit_proposal(card["id"], 1, "Идея", "План", link)
        with self.assertRaises(ValueError):
            storage.submit_proposal(card["id"], 1, "TBD", "План", "https://example.org")
        with self.assertRaises(ValueError):
            storage.decide_proposal(1, "automatic")
        with self.assertRaises(ValueError):
            storage.create_team("", "team@example.org")
        team_id = storage.create_team("Новая команда", "students@example.org")
        proposal_id = storage.submit_proposal(card["id"], team_id, "Сохраняемая идея", "Сохраняемый план", "https://example.org/demo")
        storage.save_answers(card["task_id"], {"users": "Агрономы"})
        storage.save_suggestions(card["task_id"], {"users": "Агрономы"}, "Локальный режим", {"users": "Ответ бизнеса"})
        storage.init_db()
        self.assertEqual(self.card(card["id"])["title"], "Сохраняемая карточка")
        self.assertEqual(storage.one("SELECT team_id FROM proposals WHERE id=?", (proposal_id,))["team_id"], team_id)
        task = storage.one("SELECT * FROM tasks WHERE id=?", (card["task_id"],))
        self.assertEqual(json.loads(task["answers"]), {"users": "Агрономы"})
        self.assertEqual(json.loads(task["suggestions"])["fields"], {"users": "Агрономы"})

    def test_legacy_schema_migration_preserves_existing_records(self):
        legacy_path = Path(self.temp.name) / "legacy.sqlite3"
        db = sqlite3.connect(legacy_path)
        try:
            db.executescript("""
                CREATE TABLE tasks (id INTEGER PRIMARY KEY, description TEXT NOT NULL,
                    questions TEXT NOT NULL DEFAULT '{}', answers TEXT NOT NULL DEFAULT '{}',
                    question_mode TEXT NOT NULL DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE cards (id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL UNIQUE REFERENCES tasks(id),
                    title TEXT NOT NULL DEFAULT '', context TEXT NOT NULL DEFAULT '', need TEXT NOT NULL DEFAULT '',
                    users TEXT NOT NULL DEFAULT '', data TEXT NOT NULL DEFAULT '', constraints TEXT NOT NULL DEFAULT '',
                    outcome TEXT NOT NULL DEFAULT '', success TEXT NOT NULL DEFAULT '', contact TEXT NOT NULL DEFAULT '',
                    interaction TEXT NOT NULL DEFAULT '', confirmed_fields TEXT NOT NULL DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'draft', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT NOT NULL, contact TEXT NOT NULL);
                CREATE TABLE proposals (id INTEGER PRIMARY KEY, card_id INTEGER NOT NULL REFERENCES cards(id),
                    team_id INTEGER NOT NULL REFERENCES teams(id), idea TEXT NOT NULL, plan TEXT NOT NULL,
                    link TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
                INSERT INTO tasks(id,description,answers) VALUES (42,'Existing business draft','{"users":"Existing answer"}');
                INSERT INTO cards(id,task_id,title,context,confirmed_fields,status)
                    VALUES (73,42,'Existing title','Existing context','["context"]','published');
                INSERT INTO teams(id,name,contact) VALUES (51,'Existing team','existing@example.org');
                INSERT INTO proposals(id,card_id,team_id,idea,plan,link,status)
                    VALUES (64,73,51,'Existing idea','Existing plan','https://example.org/existing','accepted');
            """)
            db.commit()
        finally:
            db.close()
        with patch.object(storage, "DB_PATH", legacy_path):
            before = {table: storage.rows(f"SELECT * FROM {table}") for table in ("tasks", "cards", "teams", "proposals")}
            storage.init_db()
            storage.init_db()
            for table, records in before.items():
                current = storage.rows(f"SELECT * FROM {table}")
                self.assertEqual(len(current), len(records))
                for original, migrated in zip(records, current):
                    for key, value in original.items():
                        self.assertEqual(migrated[key], value, f"{table}.{key}")
            migrated = storage.one("SELECT * FROM tasks WHERE id=42")
            self.assertIsNotNone(migrated["business_id"])
            self.assertEqual(migrated["suggestions"], "{}")
            self.assertEqual(migrated["suggestion_mode"], "")


if __name__ == "__main__":
    unittest.main()
