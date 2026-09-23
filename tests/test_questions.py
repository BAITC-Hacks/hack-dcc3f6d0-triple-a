"""Offline checks: never contact OpenAI or read a real API key."""

import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from questions import CARD_FIELDS, FIELDS, generate_questions, suggest_fields


class QuestionsTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def mock_api(self, payload=None, error=None):
        os.environ["OPENAI_API_KEY"] = "test-placeholder-not-a-real-key"
        client = MagicMock()
        client.__enter__.return_value = client
        client.responses.create.return_value = SimpleNamespace(output_text=json.dumps(payload, ensure_ascii=False))
        client.responses.create.side_effect = error
        patched = patch("openai.OpenAI", return_value=client)
        constructor = patched.start()
        self.addCleanup(patched.stop)
        return client, constructor

    def empty_fields(self):
        return {field: {"value": "", "source": ""} for field in CARD_FIELDS}

    def test_no_key_questions_target_gaps(self):
        questions, mode, error = generate_questions(
            "Пользователи: агрономы\nДанные: CSV наблюдений", {"contact": "demo@example.org"})
        self.assertGreaterEqual(len(questions), 3)
        for known in ("users", "data", "contact"):
            self.assertNotIn(known, questions)
        self.assertIn("Локальный", mode)
        self.assertIsNone(error)

    def test_all_fields_known_still_have_three_distinct_detail_keys(self):
        answers = {field: f"Подробный ответ по полю {field}" for field in FIELDS}
        questions, _, _ = generate_questions("Исходный процесс", answers)
        self.assertGreaterEqual(len(questions), 3)
        self.assertTrue(all(key.startswith("detail_") for key in questions))
        self.assertFalse(set(questions) & set(answers))

    def test_local_suggestions_copy_only_sources(self):
        fields, sources, mode, error = suggest_fields(
            "Название: Помощник агронома\nПользователи: Агрономы\nДанные: не знаю",
            {"outcome": "План на неделю", "contact": "—", "constraints": {"bad": "type"}})
        self.assertEqual(set(fields), set(CARD_FIELDS))
        self.assertEqual(fields["title"], "Помощник агронома")
        self.assertEqual(fields["users"], "Агрономы")
        self.assertEqual(fields["outcome"], "План на неделю")
        for unknown in ("data", "contact", "constraints"):
            self.assertEqual(fields[unknown], "")
        self.assertIn("Ответ", sources["outcome"])
        self.assertIn("Локальный", mode)
        self.assertIsNone(error)

    def test_free_draft_is_only_verbatim_context(self):
        draft = "Нужен помощник агронома: культура, погода, симптомы → план на неделю."
        fields, sources, _, _ = suggest_fields(draft)
        self.assertEqual(fields["context"], draft)
        self.assertEqual([key for key, value in fields.items() if value], ["context"])
        self.assertIn(draft, sources["context"])

    def test_questions_api_success_and_request_configuration(self):
        expected, _, _ = generate_questions("Процесс бизнеса")
        client, constructor = self.mock_api(expected)
        questions, mode, error = generate_questions("Процесс бизнеса")
        self.assertEqual(questions, expected)
        self.assertIn("OpenAI API", mode)
        self.assertIsNone(error)
        constructor.assert_called_once_with(timeout=20, max_retries=0)
        request = client.responses.create.call_args.kwargs
        self.assertFalse(request["store"])
        self.assertEqual(request["text"]["format"]["type"], "json_schema")
        self.assertNotIn("api_key", request)

    def test_fields_api_success(self):
        payload = self.empty_fields()
        payload["title"] = {"value": "Помощник агронома", "source": "draft"}
        payload["outcome"] = {"value": "План на неделю", "source": "answer:outcome"}
        self.mock_api(payload)
        fields, sources, mode, error = suggest_fields(
            "Название: Помощник агронома", {"outcome": "План на неделю"})
        self.assertEqual(fields["title"], "Помощник агронома")
        self.assertEqual(fields["outcome"], "План на неделю")
        self.assertEqual(fields["data"], "")
        self.assertIn("Ответ", sources["outcome"])
        self.assertIn("OpenAI API", mode)
        self.assertIsNone(error)

    def test_api_error_never_exposes_exception(self):
        self.mock_api(error=RuntimeError("SECRET_TOKEN_AND_PRIVATE_BODY"))
        for result in (generate_questions("Процесс"), suggest_fields("Процесс")):
            self.assertIn("резервный", result[-2])
            self.assertTrue(result[-1])
            self.assertNotIn("SECRET", str(result))

    def test_questions_reject_wrong_types_duplicates_and_non_json(self):
        valid, _, _ = generate_questions("Процесс")
        client, _ = self.mock_api(valid)
        invalid_values = [[], {key: ["Вопрос?"] for key in valid}, {key: "Одинаковый вопрос?" for key in valid}]
        for invalid in invalid_values:
            with self.subTest(invalid=invalid):
                client.responses.create.return_value.output_text = json.dumps(invalid)
                questions, mode, error = generate_questions("Процесс")
                self.assertGreaterEqual(len(questions), 3)
                self.assertIn("резервный", mode)
                self.assertTrue(error)
        client.responses.create.return_value.output_text = "not json"
        self.assertIn("резервный", generate_questions("Процесс")[-2])

    def test_hallucinated_fields_fall_back_without_new_facts(self):
        payload = self.empty_fields()
        payload["data"] = {"value": "10000 строк CSV", "source": "draft"}
        self.mock_api(payload)
        fields, _, mode, error = suggest_fields("Нужен помощник агронома")
        self.assertEqual(fields["data"], "")
        self.assertNotIn("10000", str(fields))
        self.assertIn("резервный", mode)
        self.assertTrue(error)

    def test_fact_from_unrelated_answer_is_not_accepted(self):
        payload = self.empty_fields()
        payload["contact"] = {"value": "Агрономы", "source": "answer:users"}
        self.mock_api(payload)
        fields, _, mode, _ = suggest_fields("Процесс", {"users": "Агрономы"})
        self.assertEqual(fields["contact"], "")
        self.assertIn("резервный", mode)

    def test_truncated_negation_is_rejected_for_answers_and_draft(self):
        payload = self.empty_fields()
        client, _ = self.mock_api(payload)
        fact = "1000 размеченных снимков отсутствуют."
        for source, draft, answers in (
            ("answer:data", "Нужен помощник", {"data": fact}),
            ("draft", "Данные: " + fact, {}),
            ("draft", fact, {}),
        ):
            with self.subTest(source=source, draft=draft):
                payload["data"] = {"value": "1000 размеченных снимков", "source": source}
                client.responses.create.return_value.output_text = json.dumps(payload)
                fields, _, mode, error = suggest_fields(draft, answers)
                self.assertNotEqual(fields["data"], "1000 размеченных снимков")
                self.assertIn("резервный", mode)
                self.assertTrue(error)

    def test_local_multiline_source_preserves_crlf(self):
        draft = "Данные: Таблица CSV\r\nБез персональных данных\r\nПользователи: агрономы"
        fields, _, _, _ = suggest_fields(draft)
        self.assertEqual(fields["data"], "Таблица CSV\r\nБез персональных данных")
        self.assertIn(fields["data"], draft)

    def test_fields_reject_malformed_and_placeholder_values(self):
        client, _ = self.mock_api({})
        placeholder = self.empty_fields()
        placeholder["data"] = {"value": "не знаю", "source": "draft"}
        wrong_type = self.empty_fields()
        wrong_type["data"] = {"value": ["CSV"], "source": "draft"}
        for invalid in ({}, [], placeholder, wrong_type):
            with self.subTest(invalid=invalid):
                client.responses.create.return_value.output_text = json.dumps(invalid)
                fields, _, mode, error = suggest_fields("Данные: не знаю")
                self.assertEqual(fields["data"], "")
                self.assertIn("резервный", mode)
                self.assertTrue(error)


if __name__ == "__main__":
    unittest.main()
