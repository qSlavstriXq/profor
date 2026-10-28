# Стратегия для школьника: собираем данные из базы, отдаём модели,
# сверяем её ответ с базой. Пока нет ключа Qwen, вместо модели работает заглушка.

import logging
from pathlib import Path

from django.conf import settings

from admissions.models import Course, Subject
from admissions.services import build_recommendations
from careers.services import professions_for_attempt
from proftests.directions import matching_scales
from proftests.models import StrategyReport, Test
from proftests.scoring import ranked
from proftests.services import build_result

from . import client
from .schemas import Direction, NextStep, Strategy, TestAnalysis

logger = logging.getLogger("llm")

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "strategy_system.txt"

# Сколько программ максимум отдаём модели: больше программ, больше токенов
MAX_PROGRAMS = 15

# Сколько курсов из каталога максимум отдаём модели
MAX_COURSES = 15

# Сколько профессий из каталога максимум отдаём модели
MAX_PROFESSIONS = 15

# Сколько профессий показываем в направлении, когда стратегию собирает код без модели
STUB_PROFESSIONS = 5

# Сколько самых выраженных шкал каждого теста учитываем при подборе программ
TOP_SCALES = 2


def latest_attempts(participant):
    """Последнее прохождение каждого теста: {id теста: прохождение}."""
    latest = {}
    for attempt in participant.attempts.select_related("test"):  # от новых к старым
        latest.setdefault(attempt.test_id, attempt)
    return latest


def strong_scales(participant):
    """Самые выраженные шкалы по последним тестам: [(код теста, код шкалы, название)]."""
    result = []
    for attempt in latest_attempts(participant).values():
        names = {scale.code: scale.name for scale in attempt.test.scales.all()}
        for code, points in ranked(attempt.scores)[:TOP_SCALES]:
            if points > 0:
                result.append((attempt.test.code, code, names[code]))
    return result


def pick_programs(scores, participant=None):
    """Программы с шансами по баллам ЕГЭ. Недоступные модели не отдаём.

    Если передан участник, у каждой программы появляется поле fits: каким его
    сильным сторонам по профтестам она соответствует. Такие программы идут первыми,
    а внутри порядок по шансам сохраняется (sorted не меняет порядок равных).
    """
    if not scores:
        return []
    programs = [p for p in build_recommendations(scores) if p["category"] != "недоступно"]
    if participant is not None:
        strong = strong_scales(participant)
        for program in programs:
            program["fits"] = [
                name for test_code, code, name in strong
                if matching_scales(test_code, program["direction_code"], [code])
            ]
        programs.sort(key=lambda p: not p["fits"])
    return programs[:MAX_PROGRAMS]


def make_basis(participant, scores):
    """На каких данных строится стратегия. Если это поменялось, старая устарела."""
    attempt_ids = sorted(a.pk for a in latest_attempts(participant).values())
    # Внешние результаты: id и время загрузки, чтобы заметить и новые, и обновлённые
    external = sorted([r.pk, r.imported_at.isoformat()] for r in participant.external_results.all())
    return {"attempts": attempt_ids, "external": external, "scores": scores or {},
            "grade": participant.grade}


def saved_strategy(participant, basis):
    """Сохранённая стратегия, если она построена на тех же данных, иначе None."""
    report = participant.strategy_reports.first()  # самая новая
    if report is None or report.basis != basis:
        return None
    return Strategy.model_validate(report.content)


def create_strategy(participant, scores, llm_client=None):
    """Составляет стратегию и сохраняет её, если ответила модель.

    Возвращает (стратегия, источник), как generate_strategy.
    """
    strategy, source = generate_strategy(participant, pick_programs(scores, participant), llm_client)
    if source == "llm":
        StrategyReport.objects.create(
            participant=participant,
            model_name=settings.QWEN_MODEL,
            basis=make_basis(participant, scores),
            content=strategy.model_dump(),
        )
    return strategy, source


def pick_professions(participant):
    """Профессии из каталога по самым выраженным шкалам профтестов.

    Модель выбирает профессии только из этого списка. Если профессия подходит
    шкалам нескольких тестов, она идёт выше.
    """
    found = {}
    for attempt in latest_attempts(participant).values():
        if attempt.test.kind != Test.Kind.CAREER:
            continue
        for item in professions_for_attempt(attempt):
            entry = found.setdefault(item["profession"].code, {"profession": item["profession"], "fits": []})
            entry["fits"].extend(item["fits"])
    # sorted не меняет порядок равных: внутри остаётся порядок подбора по тесту
    entries = sorted(found.values(), key=lambda entry: -len(entry["fits"]))
    return [
        {
            "code": entry["profession"].code,
            "title": entry["profession"].title,
            "fits": entry["fits"],
            "subjects": [Subject(code).label for code in entry["profession"].subjects],
            "directions": entry["profession"].directions,
        }
        for entry in entries[:MAX_PROFESSIONS]
    ]


def build_input(participant, programs=None):
    """Данные для модели. Только результаты, без кода участника:
    модели не нужно знать, кто это, поэтому и не отправляем."""
    latest = latest_attempts(participant)

    tests = []
    for attempt in latest.values():
        tests.append({
            "test_code": attempt.test.code,
            "title": attempt.test.title,
            "kind": attempt.test.kind,
            "scales": [
                {
                    "name": row["name"],
                    "points": row["points"],
                    "max": row["max_points"],
                    "level": row["interpretation"]["level"] if row["interpretation"] else None,
                    "about": row["description"],
                }
                for row in build_result(attempt)
            ],
        })

    available_tests = [
        {"test_code": test.code, "title": test.title, "description": test.description}
        for test in Test.objects.filter(is_active=True).exclude(pk__in=latest.keys())
    ]

    # Отправляем только то, что нужно для объяснения: меньше данных, меньше токенов
    programs = [
        {"id": p["id"], "university": p["university"], "name": p["name"],
         "direction_code": p.get("direction_code", ""),
         "category": p["category"], "fits": p.get("fits", []),
         "tuition_per_year": p.get("tuition_per_year"), "paid_category": p.get("paid_category")}
        for p in (programs or [])
    ]
    # Результаты из центра профориентации и других источников вне сайта
    external_results = [
        {
            "source": r.source_name,
            "test": r.test_name,
            "date": r.taken_at.isoformat() if r.taken_at else None,
            "scales": r.scales,
        }
        for r in participant.external_results.all()
    ]
    return {"grade": participant.grade, "tests": tests, "external_results": external_results,
            "available_tests": available_tests, "programs": programs,
            "professions": pick_professions(participant),
            "courses": pick_courses(programs)}


def pick_courses(programs):
    """Курсы из каталога, подходящие к направлениям программ из подбора.
    Если программ нет (школьник не ввёл баллы), отдаём любые курсы каталога."""
    courses = Course.objects.order_by("pk")
    if not settings.SHOW_UNVERIFIED_DATA:
        courses = courses.filter(verified=True)
    codes = [p["direction_code"] for p in programs if p.get("direction_code")]
    if codes:
        courses = [c for c in courses if any(c.fits_direction(code) for code in codes)]
    return [
        {"id": c.pk, "title": c.title, "provider": c.provider,
         "description": c.description, "professions": c.professions}
        for c in list(courses)[:MAX_COURSES]
    ]


def check_against_data(strategy, data):
    """Убирает из ответа модели всё, чего нет в наших данных.

    Модель может ошибиться и указать несуществующую программу или тест.
    Такое в отчёт не попадает, а в журнал пишется предупреждение.
    """
    program_ids = {p["id"] for p in data["programs"]}
    profession_codes = {p["code"] for p in data.get("professions", [])}
    taken_codes = {t["test_code"] for t in data["tests"]}
    available_codes = {t["test_code"] for t in data["available_tests"]}
    course_ids = {c["id"] for c in data.get("courses", [])}

    for direction in strategy.directions:
        unknown = [pid for pid in direction.program_ids if pid not in program_ids]
        if unknown:
            logger.warning("Модель указала программы не из базы: %s", unknown)
            direction.program_ids = [pid for pid in direction.program_ids if pid in program_ids]
        unknown = [code for code in direction.profession_codes if code not in profession_codes]
        if unknown:
            logger.warning("Модель указала профессии не из каталога: %s", unknown)
            direction.profession_codes = [c for c in direction.profession_codes if c in profession_codes]

    strategy.test_analysis = [
        item for item in strategy.test_analysis if item.test_code in taken_codes
    ]

    # План только на текущий и следующие классы, по одному пункту на класс, по порядку
    grade = data.get("grade") or 9
    plan = {}
    for item in strategy.plan:
        if item.grade >= grade:
            plan.setdefault(item.grade, item)
    strategy.plan = [plan[g] for g in sorted(plan)]

    for step in strategy.next_steps:
        if step.test_code is not None and step.test_code not in available_codes:
            logger.warning("Модель указала тест не с сайта: %s", step.test_code)
            step.test_code = None
        if step.course_id is not None and step.course_id not in course_ids:
            logger.warning("Модель указала курс не из каталога: %s", step.course_id)
            step.course_id = None
    return strategy


def stub_strategy(data):
    """Ответ без модели, собранный кодом из тех же данных.

    Нужен, пока не подключён Qwen, и на случай, если модель недоступна.
    """
    analysis = []
    directions = []
    for test in data["tests"]:
        top = test["scales"][0]
        analysis.append(TestAnalysis(
            test_code=test["test_code"],
            summary=f"Сильнее всего выражена шкала «{top['name']}»: "
                    f"{top['points']} из {top['max']}.",
        ))
        directions.append(Direction(
            title=top["name"],
            why=top["about"] or "Это самая выраженная шкала в вашем результате.",
            profession_codes=[
                p["code"] for p in data.get("professions", []) if top["name"] in p["fits"]
            ][:STUB_PROFESSIONS],
        ))

    if not directions:
        directions.append(Direction(
            title="Сначала пройдите профтест",
            why="Без результатов тестов подобрать направления не получится.",
        ))

    next_steps = [
        NextStep(
            kind="test", title=t["title"], test_code=t["test_code"],
            why=t["description"] or "Поможет лучше понять ваши интересы.",
        )
        for t in data["available_tests"]
    ]
    return Strategy(
        summary="Помощник на основе ИИ пока не подключён. Ниже краткие итоги по вашим тестам.",
        test_analysis=analysis,
        directions=directions,
        next_steps=next_steps[:6],
    )


def generate_strategy(participant, programs=None, llm_client=None):
    """Возвращает (стратегия, источник). Источник: "llm" или "stub"."""
    data = build_input(participant, programs)

    if not data["tests"] and not data["external_results"]:
        return stub_strategy(data), "stub"  # нечего анализировать, токены не тратим
    if llm_client is None and not client.is_configured():
        return stub_strategy(data), "stub"

    prompt = PROMPT_PATH.read_text(encoding="utf-8")
    try:
        strategy = client.ask_json(prompt, data, Strategy, client=llm_client)
    except client.LLMError as error:
        logger.error("Не удалось получить стратегию от модели: %s", error)
        return stub_strategy(data), "stub"
    return check_against_data(strategy, data), "llm"
