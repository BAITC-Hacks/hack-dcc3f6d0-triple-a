"""Local, deterministic MVP logic. No external services."""

from copy import deepcopy
from uuid import uuid4

SKILLS = ["Python", "AI / ML", "Web", "Frontend", "Backend", "Data Analysis", "Design", "Mobile"]
FIELDS = {
    "title": ("Название задачи", 10, 12, "Укажите конкретное название: что нужно создать или улучшить."),
    "problem": ("Описание проблемы", 20, 100, "Опишите текущий процесс, пользователей и основную трудность (от 100 символов)."),
    "goal": ("Цель", 15, 60, "Укажите измеримую цель и кому она поможет (от 60 символов)."),
    "result": ("Ожидаемый результат", 20, 80, "Перечислите итоговые материалы и критерии приёмки (от 80 символов)."),
    "requirements": ("Требования", 15, 60, "Добавьте ограничения, доступные данные и требования к решению (от 60 символов)."),
    "deadline": ("Срок выполнения", 10, 1, "Укажите реалистичный срок выполнения."),
    "skills": ("Необходимые навыки", 10, 1, "Выберите хотя бы один необходимый навык."),
}

RESPONSE_MIN_LENGTHS = {
    "team": 2,
    "proposal": 30,
    "experience": 10,
    "contact": 5,
}


def evaluate(data):
    score, strengths, improvements = 0, [], []
    for key, (label, weight, minimum, tip) in FIELDS.items():
        value = data.get(key, "")
        size = len(value) if isinstance(value, list) else len(str(value).strip())
        points = round(weight * min(size / minimum, 1))
        score += points
        if size >= minimum:
            strengths.append(f"{label}: достаточно информации для первичного знакомства.")
        else:
            improvements.append(f"{label}: {tip}")
    required = all(data.get(key) and str(data[key]).strip() for key in FIELDS)
    return {"score": score, "strengths": strengths, "improvements": improvements,
            "ready": bool(required and score >= 75)}


def publish(tasks, draft, submission_id=None):
    """Publish a validated draft once, even if the submit action is repeated."""
    assessment = evaluate(draft)
    if not assessment["ready"]:
        raise ValueError("Заполните все основные поля и наберите минимум 75 баллов.")
    if submission_id:
        existing = next((item for item in tasks if item.get("submission_id") == submission_id), None)
        if existing:
            return existing
    task = deepcopy(draft)
    task.update(id=uuid4().hex, score=assessment["score"], owned=True,
                status="Открыта", selected_team=None, responses=[], submission_id=submission_id)
    tasks.append(task)
    return task


def submit_response(task, team, proposal, experience, contact):
    if task["selected_team"]:
        raise ValueError("Команда для этой задачи уже выбрана.")
    values = [team.strip(), proposal.strip(), experience.strip(), contact.strip()]
    if not all(values):
        raise ValueError("Заполните все поля предложения, включая контакт для связи.")
    labels = {
        "team": "Название команды",
        "proposal": "Предложение команды",
        "experience": "Навыки / опыт",
        "contact": "Контакт",
    }
    for field, value in zip(RESPONSE_MIN_LENGTHS, values):
        minimum = RESPONSE_MIN_LENGTHS[field]
        if len(value) < minimum:
            raise ValueError(f'{labels[field]}: минимум {minimum} символов.')
    if any(r["team"].casefold() == values[0].casefold() for r in task["responses"]):
        raise ValueError("Предложение от команды с таким названием уже отправлено.")
    response = dict(zip(["team", "proposal", "experience", "contact"], values))
    response.update(id=uuid4().hex, status="На рассмотрении")
    task["responses"].append(response)
    return response


def select_team(task, response_id):
    if task["selected_team"]:
        raise ValueError("Команда для дальнейшей работы уже выбрана.")
    response = next((r for r in task["responses"] if r["id"] == response_id), None)
    if response is None:
        raise ValueError("Предложение не найдено.")
    task["selected_team"] = response_id
    task["status"] = "Команда выбрана"
    response["status"] = "Выбрана"
    for other in task["responses"]:
        if other["id"] != response_id:
            other["status"] = "Не выбрана"


def demo_tasks():
    examples = [
        ("AI-помощник для интернет-магазина", 94, ["Python", "AI / ML", "Backend"], "4 недели",
         "Менеджеры интернет-магазина ежедневно отвечают на повторяющиеся вопросы о товарах, оплате и доставке. Покупатели долго ждут ответа и уходят, не завершив заказ.",
         "Сократить время первого ответа покупателю до одной минуты и разгрузить менеджеров поддержки.",
         "Работающий прототип помощника на тестовом каталоге, инструкция запуска и проверка на 30 типовых вопросах. Ответы должны ссылаться на данные каталога."),
        ("Анализ отзывов клиентов", 87, ["Python", "Data Analysis", "AI / ML"], "3 недели",
         "Сеть кофеен собирает отзывы из разных каналов. Руководителю сложно вручную выделить повторяющиеся жалобы и понять, какие изменения важнее для гостей.",
         "Выделить основные темы обращений и сравнить динамику удовлетворённости по точкам за месяц.",
         "Дашборд с темами и тональностью отзывов, отчёт о трёх основных проблемах и воспроизводимый скрипт обработки CSV."),
        ("Система автоматизации заявок", 81, ["Web", "Frontend", "Backend", "Design"], "5 недель",
         "Небольшая сервисная компания принимает заявки по телефону и в таблицах. Заявки теряются, а сотрудники тратят время на уточнение текущего статуса работ.",
         "Собрать заявки в одном интерфейсе и сделать сроки и этапы обработки прозрачными для сотрудников.",
         "Прототип реестра заявок с формой создания, фильтрацией по статусам и демонстрацией полного пути заявки от поступления до закрытия."),
    ]
    return [dict(id=f"demo-{i}", title=title, score=score, skills=skills, deadline=deadline,
                 problem=problem, goal=goal, result=result,
                 requirements="Используйте обезличенные тестовые данные. Решение должно запускаться локально и сопровождаться краткой инструкцией для бизнеса.",
                 extra="Демонстрационная задача. Рейтинг задан для примера оформления каталога.",
                 status="Открыта", owned=False, selected_team=None, responses=[])
            for i, (title, score, skills, deadline, problem, goal, result) in enumerate(examples)]
