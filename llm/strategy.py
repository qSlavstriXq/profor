# Стратегия для школьника: собираем данные из базы, отдаём модели,
# сверяем её ответ с базой. Пока нет ключа Qwen, вместо модели работает заглушка.

import logging
from pathlib import Path

from proftests.models import Test
from proftests.services import build_result

from . import client
from .schemas import Direction, NextStep, Strategy, TestAnalysis

logger = logging.getLogger("llm")

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "strategy_system.txt"


def build_input(participant, programs=None):
    """Данные для модели. Только результаты, без кода участника:
    модели не нужно знать, кто это, поэтому и не отправляем."""
    latest = {}  # последнее прохождение каждого теста
    for attempt in participant.attempts.select_related("test"):  # от новых к старым
        latest.setdefault(attempt.test_id, attempt)

    tests = []
    for attempt in latest.values():
        tests.append({
            "test_code": attempt.test.code,
            "title": attempt.test.title,
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
        {"id": p["id"], "university": p["university"], "name": p["name"], "category": p["category"]}
        for p in (programs or [])
    ]
    return {"tests": tests, "available_tests": available_tests, "programs": programs}


def check_against_data(strategy, data):
    """Убирает из ответа модели всё, чего нет в наших данных.

    Модель может ошибиться и указать несуществующую программу или тест.
    Такое в отчёт не попадает, а в журнал пишется предупреждение.
    """
    program_ids = {p["id"] for p in data["programs"]}
    taken_codes = {t["test_code"] for t in data["tests"]}
    available_codes = {t["test_code"] for t in data["available_tests"]}

    for direction in strategy.directions:
        unknown = [pid for pid in direction.program_ids if pid not in program_ids]
        if unknown:
            logger.warning("Модель указала программы не из базы: %s", unknown)
            direction.program_ids = [pid for pid in direction.program_ids if pid in program_ids]

    strategy.test_analysis = [
        item for item in strategy.test_analysis if item.test_code in taken_codes
    ]

    for step in strategy.next_steps:
        if step.test_code is not None and step.test_code not in available_codes:
            logger.warning("Модель указала тест не с сайта: %s", step.test_code)
            step.test_code = None
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
            why=top["about"] or "Это самая выраженная шкала в твоём результате.",
        ))

    if not directions:
        directions.append(Direction(
            title="Сначала пройди профтест",
            why="Без результатов тестов подобрать направления не получится.",
        ))

    next_steps = [
        NextStep(
            kind="test", title=t["title"], test_code=t["test_code"],
            why=t["description"] or "Поможет лучше понять твои интересы.",
        )
        for t in data["available_tests"]
    ]
    return Strategy(
        summary="Помощник на основе ИИ пока не подключён. Ниже краткие итоги по твоим тестам.",
        test_analysis=analysis,
        directions=directions,
        next_steps=next_steps[:6],
    )


def generate_strategy(participant, programs=None, llm_client=None):
    """Возвращает (стратегия, источник). Источник: "llm" или "stub"."""
    data = build_input(participant, programs)

    if not data["tests"]:
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
