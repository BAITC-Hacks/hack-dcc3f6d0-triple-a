"""AI Sana Challenge Hub: business briefs, human review and team proposals."""

import hashlib
import json
import os

import streamlit as st

from questions import LOCAL, generate_questions, suggest_fields
from rating import CARD_FIELDS, LABELS, evaluate_card, is_meaningful
from storage import (
    apply_suggestions, create_task, create_team, decide_proposal, init_db,
    one, rows, save_answers, save_card, save_suggestions, set_publication,
    submit_proposal,
)

STATUSES = {"pending": "На рассмотрении", "accepted": "Принято", "declined": "Отклонено"}


def flash(message, kind="success"):
    st.session_state["flash"] = (kind, message)
    st.rerun()


def version(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def heading(card):
    result = evaluate_card(card)
    publication = "Опубликована" if card["status"] == "published" else "Не опубликована"
    return f"#{card['id']} · {card['title'] or 'Без названия'} · {result['score']}/100 · {publication}"


def show_rating(card):
    result = evaluate_card(card)
    st.progress(result["score"] / 100, text=f"Готовность: {result['score']}/100 — {result['level']}")
    st.dataframe(
        [{"Критерий": item["criterion"], "Баллы": f"{item['earned']} / {item['maximum']}",
          "Что нужно уточнить": item["reason"] or "Заполнено и подтверждено"}
         for item in result["breakdown"]],
        hide_index=True, width="stretch",
    )
    st.caption("Баллы за содержание и ручное подтверждение. Уровень готовности не ограничивает публикацию.")


def catalog():
    cards = rows("SELECT * FROM cards ORDER BY id DESC")
    search = st.text_input("Поиск по названию, контексту, потребности и данным", key="catalog_search").casefold().strip()
    sorting = st.selectbox("Сортировка", ["Сначала новые", "По готовности: выше", "По готовности: ниже", "По названию"], key="catalog_sort")
    if search:
        cards = [card for card in cards if search in " ".join(card[field] for field in ("title", "context", "need", "data")).casefold()]
    if sorting.startswith("По готовности"):
        cards.sort(key=lambda card: evaluate_card(card)["score"], reverse=sorting.endswith("выше"))
    elif sorting == "По названию":
        cards.sort(key=lambda card: card["title"].casefold())
    st.caption(f"Найдено: {len(cards)}. Неопубликованные карточки тоже видны; отклик доступен после публикации.")
    for card in cards:
        with st.expander(heading(card)):
            for field in CARD_FIELDS[1:]:
                st.write(f"**{LABELS[field]}:**")
                st.text(card[field] or "Не указано")
            show_rating(card)
            if card["status"] == "published":
                st.caption("Чтобы отправить предложение, выберите роль «Команда» и вкладку «Работа команды».")


def business_page(business_id):
    st.subheader("1. Черновик бизнеса")
    st.caption("Например: нужен помощник агронома — культура, погода и симптомы → план на неделю.")
    with st.form("new_task"):
        description = st.text_area("Короткое описание задачи", key="draft_description", max_chars=12000)
        create = st.form_submit_button("Получить уточняющие вопросы", key="create_task")
    if create:
        if not is_meaningful(description):
            st.error("Опишите задачу своими словами.")
        else:
            with st.spinner("Готовим вопросы по недостающим сведениям…"):
                questions, mode, error = generate_questions(description.strip())
            task_id = create_task(description, questions, mode, business_id=business_id)
            st.session_state[f"task_selection_{business_id}"] = task_id
            message = f"Задача создана. {mode}."
            if error:
                message += f" {error}"
            flash(message, "warning" if error else "success")

    tasks = rows("SELECT id,description FROM tasks WHERE business_id=? ORDER BY id DESC", (business_id,))
    if not tasks:
        st.info("Создайте первый черновик.")
        return
    task_names = {task["id"]: task["description"] for task in tasks}
    task_key = f"task_selection_{business_id}"
    if st.session_state.get(task_key) not in task_names:
        st.session_state[task_key] = tasks[0]["id"]
    task_id = st.selectbox("Задача для редактирования", list(task_names), key=task_key,
                           format_func=lambda ident: f"#{ident} · {task_names[ident][:100]}")
    task = one("SELECT * FROM tasks WHERE id=?", (task_id,))
    card = one("SELECT * FROM cards WHERE task_id=?", (task_id,))
    with st.expander("Исходный черновик"):
        st.text(task["description"])

    st.subheader("2. Уточнения и предложение карточки")
    questions = json.loads(task["questions"] or "{}") or LOCAL
    answers = json.loads(task["answers"] or "{}")
    st.caption(f"Режим вопросов: {task['question_mode'] or 'Локальный (демонстрационная задача)'}")
    with st.form(f"answers_{task_id}"):
        entered = {}
        for field, question in questions.items():
            entered[field] = st.text_area(question, value=answers.get(field, ""),
                                          key=f"answer_{task_id}_{field}", max_chars=6000)
        generate = st.form_submit_button("Сохранить ответы и предложить поля карточки", key=f"suggest_{task_id}")
    if generate:
        answers.update(entered)
        save_answers(task_id, answers)
        with st.spinner("Готовим предложения только из ваших сведений…"):
            fields, sources, mode, error = suggest_fields(task["description"], answers)
        save_suggestions(task_id, fields, mode, sources)
        message = f"Предложения подготовлены. {mode}. Проверьте их перед переносом."
        if error:
            message += f" {error}"
        flash(message, "warning" if error else "success")

    proposal = json.loads(task.get("suggestions") or "{}")
    if proposal.get("fields"):
        st.caption(f"Режим предложения полей: {task.get('suggestion_mode') or 'Локальный'}")
        st.dataframe(
            [{"Поле": LABELS[field], "Предложение": proposal["fields"].get(field, "") or "Неизвестно — оставляем пустым",
              "Источник": proposal.get("sources", {}).get(field, "")}
             for field in CARD_FIELDS],
            hide_index=True, width="stretch",
        )
        st.caption("В таблице — цитаты из черновика и ответов. Заполненные вручную поля сохраняются; новые значения нужно подтвердить.")
        if st.button("Применить предложения к пустым полям", key=f"apply_{task_id}"):
            applied = apply_suggestions(card["id"], proposal["fields"])
            flash("Перенесены поля: " + ", ".join(LABELS[field] for field in applied) if applied else "Пустых полей с новыми сведениями нет.", "success" if applied else "info")

    st.subheader("3. Редактирование и ручное подтверждение")
    card_values = {field: card[field] for field in CARD_FIELDS}
    card_version = version(card_values)
    with st.form(f"edit_{card['id']}_{card_version}"):
        values = {
            field: st.text_area(LABELS[field], value=card[field], height=90,
                                key=f"value_{card['id']}_{card_version}_{field}", max_chars=12000)
            for field in CARD_FIELDS
        }
        save = st.form_submit_button("Сохранить текст карточки", key=f"save_card_{card['id']}")
    if save:
        try:
            reset = save_card(card["id"], values, json.loads(card["confirmed_fields"]), card["status"])
            message = "Текст сохранён."
            if reset:
                message += " Подтвердите изменённые поля заново: " + ", ".join(LABELS[field] for field in reset) + "."
            flash(message)
        except ValueError as exc:
            st.error(str(exc))

    st.caption("Подтверждения ниже относятся к сохранённому тексту. Сначала сохраните все правки.")
    confirmed = set(json.loads(card["confirmed_fields"]))
    confirmation_version = version([card_values, sorted(confirmed)])
    with st.form(f"confirm_{card['id']}_{confirmation_version}"):
        selected = []
        for field in CARD_FIELDS:
            meaningful = is_meaningful(card[field])
            if st.checkbox(f"Подтверждаю: {LABELS[field].lower()}", value=meaningful and field in confirmed,
                           disabled=not meaningful, key=f"check_{card['id']}_{confirmation_version}_{field}"):
                selected.append(field)
        confirm = st.form_submit_button("Подтвердить выбранные поля", key=f"confirm_card_{card['id']}")
    if confirm:
        save_card(card["id"], card_values, selected, card["status"])
        flash("Ручные подтверждения сохранены. Рейтинг пересчитан.")

    st.subheader("4. Готовность и публикация")
    show_rating(card)
    st.write("**Публикация:** " + ("опубликована" if card["status"] == "published" else "не опубликована"))
    if card["status"] == "published":
        if st.button("Снять с публикации", key=f"unpublish_{card['id']}"):
            set_publication(card["id"], False)
            flash("Карточка снята с публикации.")
    else:
        if st.button("Опубликовать карточку", key=f"publish_{card['id']}"):
            try:
                set_publication(card["id"], True)
                flash("Карточка опубликована. Команды могут отправлять предложения при любом рейтинге.")
            except ValueError as exc:
                st.error(str(exc))

    st.subheader("5. Предложения и выбор команд")
    st.caption("Можно принять одну, несколько или ни одной команды. Каждое решение сохраняется вручную.")
    proposals = rows(
        "SELECT p.*,t.name AS team_name,t.contact AS team_contact FROM proposals p "
        "JOIN teams t ON t.id=p.team_id WHERE p.card_id=? ORDER BY p.id DESC", (card["id"],))
    if not proposals:
        st.info("Пока предложений нет.")
    for item in proposals:
        with st.expander(f"{item['team_name']} · {STATUSES[item['status']]}", expanded=True):
            for label, field in (("Идея", "idea"), ("План", "plan"), ("Ссылка", "link"), ("Контакт", "team_contact")):
                st.write(f"**{label}:**")
                st.text(item[field])
            with st.form(f"decision_form_{item['id']}"):
                status = st.selectbox("Решение бизнеса", list(STATUSES),
                                      index=list(STATUSES).index(item["status"]),
                                      format_func=STATUSES.get, key=f"decision_{item['id']}")
                decision = st.form_submit_button("Сохранить решение", key=f"decide_{item['id']}")
            if decision:
                try:
                    decide_proposal(item["id"], status, business_id=business_id)
                    flash(f"Решение сохранено: {STATUSES[status]}.")
                except ValueError as exc:
                    st.error(str(exc))


def student_page(team_id):
    st.subheader("Отклик на задачу")
    published = rows("SELECT * FROM cards WHERE status='published' ORDER BY id DESC")
    if published and team_id is not None:
        by_id = {card["id"]: card for card in published}
        with st.form("proposal"):
            card_id = st.selectbox("Выберите задачу", list(by_id), format_func=lambda ident: heading(by_id[ident]), key="proposal_card")
            idea = st.text_area("Идея", key="proposal_idea", max_chars=12000)
            plan = st.text_area("План", key="proposal_plan", max_chars=12000)
            link = st.text_input("Ссылка на материалы", key="proposal_link")
            send = st.form_submit_button("Отправить предложение", key="send_proposal")
        if send:
            try:
                submit_proposal(card_id, team_id, idea, plan, link)
                flash("Предложение отправлено. Решение принимает бизнес.")
            except ValueError as exc:
                st.error(str(exc))
    else:
        st.info("Для отклика нужна команда и опубликованная задача.")

    st.subheader("Предложения вашей команды")
    for item in rows(
        "SELECT p.*,c.title FROM proposals p JOIN cards c ON p.card_id=c.id "
        "WHERE p.team_id=? ORDER BY p.id DESC", (team_id,)):
        st.write(f"**{item['title'] or 'Без названия'} · {STATUSES[item['status']]}**")
        st.text(item["idea"])
        st.caption(item["link"])

    with st.expander("Добавить команду"):
        with st.form("new_team"):
            name = st.text_input("Название команды", key="new_team_name")
            contact = st.text_input("Контакт команды", key="new_team_contact")
            add = st.form_submit_button("Создать команду", key="create_team")
        if add:
            try:
                st.session_state["next_team"] = create_team(name, contact)
                flash("Команда создана и выбрана в демопрофиле.")
            except ValueError as exc:
                st.error(str(exc))


def main():
    st.set_page_config(page_title="AI Sana Challenge Hub", page_icon="🧩", layout="wide")
    init_db()
    st.title("AI Sana Challenge Hub")
    st.caption("Бизнес формулирует задачу. Студенты предлагают решение. Бизнес выбирает команды.")
    if os.getenv("OPENAI_API_KEY"):
        st.info("OpenAI подключён для вопросов и предложений полей. При сбое включится локальный резерв; фактический режим виден у каждого результата.")
    else:
        st.info("Локальный режим: вопросы и предложения полей работают без OpenAI. Ключ в окружении не задан.")
    notice = st.session_state.pop("flash", None)
    if notice:
        getattr(st, notice[0])(notice[1])

    st.sidebar.caption("Демонстрационные профили — без авторизации.")
    role = st.sidebar.selectbox("Роль", ["Бизнес", "Команда"], key="demo_role")
    if role == "Бизнес":
        profiles = rows("SELECT id,name FROM business_profiles ORDER BY id")
        names = {profile["id"]: profile["name"] for profile in profiles}
        business_id = st.sidebar.selectbox("Профиль бизнеса", list(names), format_func=names.get, key="business_profile")
        if st.session_state.get("previous_business") not in (None, business_id):
            st.session_state.pop("draft_description", None)
        st.session_state["previous_business"] = business_id
        catalog_tab, work_tab = st.tabs(["Каталог", "Работа бизнеса"])
        with catalog_tab:
            catalog()
        with work_tab:
            business_page(business_id)
    else:
        teams = rows("SELECT id,name FROM teams ORDER BY id")
        names = {team["id"]: team["name"] for team in teams}
        pending_team = st.session_state.pop("next_team", None)
        if pending_team in names:
            st.session_state["team_profile"] = pending_team
        team_id = st.sidebar.selectbox("Профиль команды", list(names), format_func=names.get, key="team_profile") if names else None
        # Separate form state by profile; an unsent proposal must not cross teams.
        previous_team = st.session_state.get("previous_team")
        if previous_team is not None and previous_team != team_id:
            for key in ("proposal_idea", "proposal_plan", "proposal_link", "proposal_card"):
                st.session_state.pop(key, None)
        st.session_state["previous_team"] = team_id
        catalog_tab, work_tab = st.tabs(["Каталог", "Работа команды"])
        with catalog_tab:
            catalog()
        with work_tab:
            student_page(team_id)


if __name__ == "__main__":
    main()

