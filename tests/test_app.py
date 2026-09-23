"""End-to-end UI checks on an isolated database; never call the live API."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import storage
from rating import evaluate_card

ROOT = Path(__file__).resolve().parents[1]


class AppFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_patch = patch.object(storage, "DB_PATH", Path(self.temp.name) / "ui.sqlite3")
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.env_patch = patch.dict(os.environ, {"OPENAI_API_KEY": ""})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.at = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
        self.assert_clean()

    def assert_clean(self):
        self.assertEqual([item.message for item in self.at.exception], [])

    def click(self, key):
        self.at.button(key=key).click().run(timeout=30)
        self.assert_clean()

    def test_draft_to_human_selection_and_restart(self):
        description = (
            "Название: Помощник агронома\n"
            "Контекст: Агрономы составляют планы обхода вручную.\n"
            "Потребность: Нужен помощник для планирования работ.\n"
            "Пользователи: Агрономы\n"
            "Ожидаемый результат: План работ на неделю."
        )
        self.at.text_area(key="draft_description").input(description)
        self.click("create_task")
        task = storage.one("SELECT * FROM tasks ORDER BY id DESC LIMIT 1")
        task_id = task["id"]
        questions = json.loads(task["questions"])
        self.assertGreaterEqual(len(questions), 3)
        self.assertIn("локаль", task["question_mode"].lower())
        answers = {
            "title": "Помощник агронома", "context": "Агрономы составляют планы обхода вручную.",
            "need": "Нужен помощник для планирования работ.", "users": "Агрономы",
            "data": "Таблица культур и наблюдений за симптомами.",
            "constraints": "Прототип работает в браузере без персональных данных.",
            "outcome": "План работ на неделю.",
            "success": "Агроном проверяет план на пяти учебных примерах.",
            "contact": "agro@example.org", "interaction": "Онлайн-встреча каждую неделю.",
        }
        for field in questions:
            self.at.text_area(key=f"answer_{task_id}_{field}").input(answers.get(field, "Уточним на совместной встрече."))
        self.click(f"suggest_{task_id}")
        self.click(f"apply_{task_id}")
        card = storage.one("SELECT * FROM cards WHERE task_id=?", (task_id,))
        card_id = card["id"]
        self.assertEqual(card["title"], "Помощник агронома")
        self.assertEqual(card["data"], answers["data"])
        self.assertEqual(evaluate_card(card)["score"], 0)
        for checkbox in self.at.checkbox:
            if checkbox.key.startswith(f"check_{card_id}_") and not checkbox.disabled:
                checkbox.check()
        self.click(f"confirm_card_{card_id}")
        card = storage.one("SELECT * FROM cards WHERE id=?", (card_id,))
        self.assertEqual(evaluate_card(card)["score"], 100)

        # Editing a confirmed value drops its points until a separate human confirmation.
        context_widget = next(item for item in self.at.text_area if item.label == "Контекст")
        context_widget.input("Агрономы составляют план вручную каждый понедельник.")
        self.click(f"save_card_{card_id}")
        card = storage.one("SELECT * FROM cards WHERE id=?", (card_id,))
        self.assertNotIn("context", json.loads(card["confirmed_fields"]))
        self.assertEqual(evaluate_card(card)["score"], 80)
        context_check = next(item for item in self.at.checkbox if item.label == "Подтверждаю: контекст")
        self.assertFalse(context_check.value)
        context_check.check()
        self.click(f"confirm_card_{card_id}")
        self.click(f"publish_{card_id}")
        self.assertEqual(storage.one("SELECT status FROM cards WHERE id=?", (card_id,))["status"], "published")

        self.at.selectbox(key="demo_role").select("Команда").run()
        self.assert_clean()
        self.at.selectbox(key="proposal_card").select(card_id)
        self.at.text_area(key="proposal_idea").input("Предлагаем интерфейс составления недельного плана.")
        self.at.text_area(key="proposal_plan").input("Согласуем поля, создадим прототип, проведём демонстрацию.")
        self.at.text_input(key="proposal_link").input("https://example.org/agro-prototype")
        self.click("send_proposal")
        proposal = storage.one("SELECT * FROM proposals ORDER BY id DESC LIMIT 1")
        self.assertEqual(proposal["card_id"], card_id)
        self.assertEqual(proposal["status"], "pending")
        self.at.selectbox(key="demo_role").select("Бизнес").run()
        self.assert_clean()
        self.at.selectbox(key=f"decision_{proposal['id']}").select("accepted")
        self.click(f"decide_{proposal['id']}")
        self.assertEqual(storage.one("SELECT status FROM proposals WHERE id=?", (proposal["id"],))["status"], "accepted")

        counts = [len(storage.rows(f"SELECT id FROM {table}")) for table in ("tasks", "cards", "teams", "proposals")]
        self.at = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
        self.assert_clean()
        self.assertEqual(counts, [len(storage.rows(f"SELECT id FROM {table}")) for table in ("tasks", "cards", "teams", "proposals")])
        self.assertEqual(storage.one("SELECT status FROM proposals WHERE id=?", (proposal["id"],))["status"], "accepted")

    def test_zero_score_publication_and_proposal(self):
        task_id = storage.create_task("Нужна помощь с планированием мероприятий.", {}, "Локальный")
        card = storage.one("SELECT * FROM cards WHERE task_id=?", (task_id,))
        storage.save_card(card["id"], {"title": "Планирование мероприятий"}, [], "draft")
        self.at.run()
        self.at.selectbox(key=f"task_selection_{1}").select(task_id).run()
        self.click(f"publish_{card['id']}")
        self.assertEqual(evaluate_card(storage.one("SELECT * FROM cards WHERE id=?", (card["id"],)))["score"], 0)
        self.at.selectbox(key="demo_role").select("Команда").run()
        self.at.selectbox(key="proposal_card").select(card["id"])
        self.at.text_area(key="proposal_idea").input("Начнём с совместного уточнения задачи.")
        self.at.text_area(key="proposal_plan").input("Проведём интервью и согласуем требования.")
        self.at.text_input(key="proposal_link").input("https://example.org/brief")
        self.click("send_proposal")
        self.assertEqual(storage.one("SELECT card_id FROM proposals ORDER BY id DESC LIMIT 1")["card_id"], card["id"])

    def test_switching_team_clears_unsent_proposal(self):
        self.at.selectbox(key="demo_role").select("Команда").run()
        self.at.text_area(key="proposal_idea").input("Идея первой команды")
        self.at.text_area(key="proposal_plan").input("План первой команды")
        self.at.text_input(key="proposal_link").input("https://example.org/team-one")
        self.at.selectbox(key="team_profile").select(2).run()
        self.assert_clean()
        self.assertEqual(self.at.text_area(key="proposal_idea").value, "")
        self.assertEqual(self.at.text_area(key="proposal_plan").value, "")
        self.assertEqual(self.at.text_input(key="proposal_link").value, "")


if __name__ == "__main__":
    unittest.main()
