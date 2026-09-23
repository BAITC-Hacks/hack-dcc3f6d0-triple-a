"""AI Sana — run with: python -m streamlit run app.py."""

from html import escape

import streamlit as st

from utils import SKILLS, demo_tasks, evaluate, publish, select_team, submit_response

st.set_page_config(page_title="AI Sana · Практика с результатом", page_icon="✦", layout="wide")
st.markdown("""
<style>
.block-container {max-width:1180px;padding-top:2rem;padding-bottom:4rem}
h1,h2,h3 {letter-spacing:-.035em}
h1 {font-size:2.7rem!important}
p {line-height:1.65}
.hero {background:linear-gradient(115deg,#143B40,#216B63);color:white;
 padding:44px 46px;border-radius:24px;margin:20px 0 26px}
.hero h1 {color:white;font-size:3.5rem!important;max-width:750px;line-height:1.1;margin:14px 0}
.hero p {color:#DCEEEB;max-width:720px;font-size:1.08rem}
.eyebrow {font-size:.76rem;font-weight:700;letter-spacing:.16em;text-transform:uppercase}
.pill {display:inline-block;background:#E7F2EF;color:#196557;padding:4px 10px;
 border-radius:8px;font-size:.8rem;margin:2px 5px 5px 0}
.score {display:inline-block;font-weight:750;font-size:1.2rem;color:#176B5E;
 background:#E7F2EF;padding:7px 12px;border-radius:10px;margin-bottom:10px}
.muted {color:#677B89;font-size:.88rem}
div[data-testid="stVerticalBlockBorderWrapper"]>div {border-radius:16px}
div[data-testid="stMetric"] {background:#EDF3F4;border-radius:14px;padding:14px 18px}
.stButton button,.stFormSubmitButton button {border-radius:10px;min-height:42px}
@media(max-width:700px){.hero{padding:25px}.hero h1{font-size:2.3rem!important}}
</style>
""", unsafe_allow_html=True)

PAGES = ["Главная", "Создать задачу", "Каталог задач", "Отклики для бизнеса"]
DEFAULT_DRAFT = {"title": "", "problem": "", "goal": "", "result": "", "requirements": "",
                 "deadline": "", "skills": [], "extra": ""}
for key, value in {"tasks": demo_tasks(), "page": "Главная", "draft": DEFAULT_DRAFT.copy(),
                   "assessment": None, "improving": False, "active_task": None,
                   "responding": None, "flash": None}.items():
    if key not in st.session_state:
        st.session_state[key] = value
S = st.session_state


def go(page, task_id=None):
    S.page = page
    S.active_task = task_id
    S.responding = None
    st.rerun()


def tags(skills):
    st.markdown("".join(f'<span class="pill">{escape(skill)}</span>' for skill in skills), unsafe_allow_html=True)


def rating(score):
    st.markdown(f'<div class="score">{int(score)} <small>/ 100</small></div>', unsafe_allow_html=True)


def home():
    st.markdown('''<div class="hero"><div class="eyebrow">AI SANA · БИЗНЕС × СТУДЕНТЫ</div>
    <h1>Реальные задачи.<br>Новые возможности.</h1>
    <p>Превратите идею в понятную задачу для студентов. Находите практические проекты,
    предлагайте решения и создавайте результат вместе.</p></div>''', unsafe_allow_html=True)
    left, right, _ = st.columns([1.2, 1.2, 2])
    if left.button("Создать задачу →", type="primary", use_container_width=True):
        go("Создать задачу")
    if right.button("Смотреть каталог", use_container_width=True):
        go("Каталог задач")
    st.write("")
    st.markdown("### От описания проблемы — к совместной работе")
    st.write("Платформа помогает бизнесу создавать качественные практические задачи, а студентам находить проекты и предлагать свои решения.")
    a, b = st.columns(2)
    with a, st.container(border=True):
        st.caption("01 / ДЛЯ БИЗНЕСА")
        st.subheader("Сформулируйте задачу. Найдите команду.")
        st.write("Опишите проблему, получите оценку полноты и рекомендации. Опубликуйте задачу и сами выберите команду из поступивших предложений.")
    with b, st.container(border=True):
        st.caption("02 / ДЛЯ СТУДЕНТОВ")
        st.subheader("Выберите проект. Предложите решение.")
        st.write("Найдите интересную задачу по своим навыкам. Изучите ожидаемый результат и отправьте предложение от вашей команды.")
    st.write("")
    for col, title, body in zip(st.columns(3), ["Понятный старт", "Качество заметно", "Выбор за бизнесом"],
        ["Структура карточки помогает описать главное и договориться об ожиданиях.",
         "Чем полнее описание, тем выше рейтинг и позиция задачи в каталоге.",
         "Студенты откликаются самостоятельно. Представитель бизнеса выбирает команду вручную."]):
        with col:
            st.markdown(f"#### {title}")
            st.write(body)


def create_task():
    st.caption("ДЛЯ БИЗНЕСА / НОВАЯ ЗАДАЧА")
    st.title("Хороший проект начинается с ясной задачи")
    st.write("Опишите контекст и ожидаемый результат. Полнота карточки определяет её место в каталоге.")
    st.caption("1. Описание → 2. Оценка и улучшение → 3. Публикация")
    if S.improving:
        st.info("Уточните поля по рекомендациям ниже и снова нажмите «Оценить качество задачи».")
        for tip in (S.assessment or {}).get("improvements", []):
            st.write(f"• {tip}")
    form_col, help_col = st.columns([2.3, 1])
    with help_col, st.container(border=True):
        st.markdown("### Что делает задачу сильной?")
        st.write("**Контекст** — кто столкнулся с проблемой и как она решается сейчас.")
        st.write("**Цель** — какое изменение вы хотите получить.")
        st.write("**Результат** — что команда должна передать и как вы это проверите.")
        st.divider()
        st.caption("Локальная оценка 0–100 учитывает заполненность и длину полей. Она не проверяет смысл текста и не использует AI API.")
        st.caption("Публикация доступна от 75 баллов при заполнении всех основных полей. Дополнительная информация необязательна.")
    with form_col:
        # Widgets stay outside a form so edits immediately invalidate old ratings.
        draft = {}
        draft["title"] = st.text_input("Название задачи", value=S.draft["title"], placeholder="Например, анализ отзывов клиентов", max_chars=140, key="draft_title")
        draft["problem"] = st.text_area("Первоначальное описание проблемы", value=S.draft["problem"], height=130, placeholder="Кто сталкивается с проблемой? Какой процесс нужно улучшить?", key="draft_problem")
        a, b = st.columns(2)
        with a:
            draft["goal"] = st.text_area("Цель", value=S.draft["goal"], height=125, placeholder="Какое измеримое изменение ожидаете?", key="draft_goal")
        with b:
            draft["result"] = st.text_area("Ожидаемый результат", value=S.draft["result"], height=125, placeholder="Что нужно передать? Как проверим результат?", key="draft_result")
        draft["requirements"] = st.text_area("Требования", value=S.draft["requirements"], placeholder="Данные, ограничения, технологии и критерии качества", key="draft_requirements")
        a, b = st.columns(2)
        with a:
            draft["deadline"] = st.text_input("Срок выполнения", value=S.draft["deadline"], placeholder="Например, 4 недели после старта", key="draft_deadline")
        with b:
            draft["skills"] = st.multiselect("Необходимые навыки", SKILLS, default=S.draft["skills"], key="draft_skills")
        draft["extra"] = st.text_area("Дополнительная информация · необязательно", value=S.draft["extra"], placeholder="Материалы, пожелания или особенности проекта", key="draft_extra")
        if draft != S.draft:
            S.draft = draft
            if not S.improving:
                S.assessment = None
        if st.button("Оценить качество задачи", type="primary", use_container_width=True):
            S.assessment = evaluate(draft)
            S.assessed_draft = draft.copy()
            S.improving = False
            st.rerun()
    if S.assessment and S.draft == S.get("assessed_draft"):
        result = S.assessment
        st.divider()
        a, b = st.columns([1, 3])
        a.metric("Рейтинг задачи", f'{result["score"]}/100')
        with b:
            st.progress(result["score"] / 100)
            if result["ready"]:
                st.success("Задача готова к публикации. Более подробное описание может поднять её выше в каталоге.")
            else:
                st.warning("Карточке нужны уточнения: заполните основные поля и наберите 75 баллов.")
        a, b = st.columns(2)
        with a:
            st.markdown("#### Сильные стороны")
            for item in result["strengths"]:
                st.write(f"• {item}")
            if not result["strengths"]:
                st.write("Начните с описания проблемы и ожидаемого результата.")
        with b:
            st.markdown("#### Что улучшить · рекомендации")
            for item in result["improvements"]:
                st.write(f"• {item}")
            if not result["improvements"]:
                st.write("Все основные поля заполнены. Перед публикацией проверьте измеримость цели и реалистичность срока.")
        a, b = st.columns(2)
        if a.button("Улучшить задачу", use_container_width=True):
            S.improving = True
            st.rerun()
        if b.button("Опубликовать задачу", type="primary", disabled=not result["ready"], use_container_width=True):
            task = publish(S.tasks, S.draft)
            S.draft = DEFAULT_DRAFT.copy()
            S.assessment = None
            S.improving = False
            for key in list(S.keys()):
                if key.startswith("draft_"):
                    del S[key]
            S.flash = f'Задача «{task["title"]}» опубликована и добавлена в каталог.'
            go("Каталог задач")
    elif S.get("assessed_draft"):
        st.caption("После изменения карточки оцените её снова, чтобы обновить рейтинг.")


def catalog():
    st.caption("ПРОЕКТЫ / ОТКРЫТЫЙ КАТАЛОГ")
    st.title("Найдите задачу, которая вам интересна")
    st.write("Навыки команды встречаются с реальными потребностями бизнеса. Более полные задачи — выше в каталоге.")
    a, b, c = st.columns([2, 1.5, 1.3])
    query = a.text_input("Поиск", placeholder="Название или описание")
    skills = b.multiselect("Навыки", SKILLS)
    order = c.selectbox("Сортировка", ["Рейтинг: по убыванию", "Рейтинг: по возрастанию"])
    tasks = [t for t in S.tasks if query.strip().casefold() in (t["title"] + " " + t["problem"]).casefold()
             and (not skills or set(skills).issubset(t["skills"]))]
    tasks.sort(key=lambda t: t["score"], reverse=order.endswith("убыванию"))
    st.caption(f"Найдено задач: {len(tasks)} · Фильтр учитывает все выбранные навыки")
    if not tasks:
        st.info("Задачи не найдены. Измените запрос или уберите часть навыков.")
    for start in range(0, len(tasks), 2):
        for col, task in zip(st.columns(2), tasks[start:start + 2]):
            with col, st.container(border=True):
                rating(task["score"])
                st.subheader(task["title"])
                st.write(task["problem"][:180] + ("…" if len(task["problem"]) > 180 else ""))
                tags(task["skills"])
                st.caption(f'{task["deadline"]} · {task["status"]} · ' + ("Ваша задача" if task["owned"] else "Демо"))
                if st.button("Подробнее →", key=f'open_{task["id"]}', use_container_width=True):
                    go("Страница задачи", task["id"])


def task_detail():
    task = next((t for t in S.tasks if t["id"] == S.active_task), None)
    if not task:
        st.info("Выберите задачу в каталоге.")
        if st.button("Открыть каталог"):
            go("Каталог задач")
        return
    if st.button("← Каталог задач"):
        go("Каталог задач")
    st.title(task["title"])
    main, side = st.columns([2.3, 1])
    with side, st.container(border=True):
        st.metric("Рейтинг качества", f'{task["score"]}/100')
        st.progress(task["score"] / 100)
        st.write(f'**Срок:** {task["deadline"]}')
        st.write(f'**Статус:** {task["status"]}')
        tags(task["skills"])
        st.caption("Бизнес самостоятельно рассматривает предложения и выбирает команду.")
        if not task["selected_team"]:
            if st.button("Откликнуться", type="primary", use_container_width=True):
                S.responding = task["id"]
        else:
            st.info("Приём предложений завершён.")
    with main:
        for title, key in [("Описание проблемы", "problem"), ("Цель", "goal"), ("Ожидаемый результат", "result"), ("Требования", "requirements")]:
            st.markdown(f"### {title}")
            st.write(task[key])
        if task["extra"]:
            st.markdown("### Дополнительная информация")
            st.write(task["extra"])
    if S.responding == task["id"] and not task["selected_team"]:
        st.divider()
        st.subheader("Предложение вашей команды")
        st.caption("Расскажите о подходе к задаче и оставьте контакт. Все поля обязательны.")
        with st.form(f'response_{task["id"]}', clear_on_submit=False):
            team = st.text_input("Название команды")
            proposal = st.text_area("Предложение команды", placeholder="Как вы решите задачу? С чего начнёте?")
            experience = st.text_area("Навыки / опыт")
            contact = st.text_input("Контакт или дополнительная информация", placeholder="Email, Telegram или другой способ связи")
            if st.form_submit_button("Отправить предложение", type="primary"):
                try:
                    submit_response(task, team, proposal, experience, contact)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    S.responding = None
                    S.flash = "Предложение отправлено. Бизнес увидит его в разделе «Отклики для бизнеса»."
                    st.rerun()


def business():
    st.caption("ДЛЯ БИЗНЕСА / ПРЕДЛОЖЕНИЯ КОМАНД")
    st.title("Выберите, с кем продолжить работу")
    st.write("Изучите предложения и опыт участников. Решение принимаете вы — автоматического назначения нет.")
    st.caption("Демонстрационный режим: здесь доступны ваши задачи и демозадачи. Переключение ролей не требует входа.")
    total = sum(len(t["responses"]) for t in S.tasks)
    a, b, c = st.columns(3)
    a.metric("Ваших задач", sum(t["owned"] for t in S.tasks))
    b.metric("Предложений", total)
    c.metric("Команд выбрано", sum(bool(t["selected_team"]) for t in S.tasks))
    choices = sorted(S.tasks, key=lambda t: (not t["owned"], -len(t["responses"])))
    ids = [t["id"] for t in choices]
    task_id = st.selectbox("Задача", ids, format_func=lambda x: next(f'{t["title"]} · {len(t["responses"])} откл.' for t in choices if t["id"] == x))
    task = next(t for t in choices if t["id"] == task_id)
    if task["selected_team"]:
        chosen = next(r for r in task["responses"] if r["id"] == task["selected_team"])
        st.success(f'Команда выбрана для дальнейшей работы: {chosen["team"]}')
    if not task["responses"]:
        st.info("Предложений пока нет. Для демонстрации откройте задачу и отправьте отклик от имени студенческой команды.")
        if st.button("Открыть задачу и откликнуться"):
            go("Страница задачи", task_id)
    for response in task["responses"]:
        with st.container(border=True):
            a, b = st.columns([3, 1])
            a.subheader(response["team"])
            b.write(f'**{response["status"]}**')
            st.write(response["proposal"])
            st.write("**Навыки / опыт**")
            st.write(response["experience"])
            st.write("**Контакт / дополнительная информация**")
            st.write(response["contact"])
            if not task["selected_team"] and st.button("Выбрать команду", key=f'choose_{response["id"]}', type="primary"):
                select_team(task, response["id"])
                st.rerun()


brand, nav = st.columns([1, 4])
brand.markdown("## AI Sana")
with nav:
    for col, page in zip(st.columns(4), PAGES):
        if col.button(page, key=f"nav_{page}", type="primary" if S.page == page else "secondary", use_container_width=True):
            go(page)
st.caption("Практические задачи для бизнеса и студентов")
if S.flash:
    st.success(S.flash)
    S.flash = None
{"Главная": home, "Создать задачу": create_task, "Каталог задач": catalog,
 "Страница задачи": task_detail, "Отклики для бизнеса": business}.get(S.page, home)()
st.divider()
st.caption("AI Sana · MVP для хакатона · Данные хранятся в текущей сессии и могут сброситься при перезагрузке вкладки. Для демонстрации используйте одну вкладку.")
