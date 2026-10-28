import json
from pathlib import Path

from django.db import transaction

from admissions.models import Subject

from .models import Interpretation, Option, Question, Scale, Test
from .scoring import expand_test_data, validate_test_data

DATA_DIR = Path(__file__).resolve().parent / "data"


class TestDataError(Exception):
    """Файл теста содержит ошибки или тест нельзя перезаписать."""


def read_test_file(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


@transaction.atomic
def load_test(data):
    """Создаёт или полностью пересоздаёт тест по данным из JSON.

    transaction.atomic: если что-то сломается посередине,
    база вернётся к прежнему состоянию, полутеста не останется.
    """
    data = expand_test_data(data)  # сокращения формата -> обычные варианты ответа
    errors = validate_test_data(data)
    errors += [
        f"шкала {s['code']}: неизвестный предмет {s['subject']!r}"
        for s in data.get("scales", []) if s.get("subject") and s["subject"] not in Subject.values
    ]
    if errors:
        raise TestDataError("; ".join(errors))

    test = Test.objects.filter(code=data["code"]).first()
    if test is not None and test.attempts.exists():
        if structure_of_test(test) != structure_of_data(data):
            # Иначе старые ответы школьников потеряют связь с вопросами
            raise TestDataError(
                f"тест {data['code']} уже проходили, а в файле поменялись шкалы, вопросы или баллы; "
                "поменяйте code, чтобы создать новую версию"
            )
        # Поменялись только тексты: обновляем их на месте, ответы остаются привязаны
        update_texts(test, data)
        return test

    if test is not None:
        test.scales.all().delete()  # вместе со шкалами удалятся варианты и расшифровки
        test.questions.all().delete()
    else:
        test = Test(code=data["code"])

    save_test_fields(test, data)
    create_content(test, data)
    return test


def structure_of_data(data):
    """Скелет теста без текстов: коды шкал и у каждого вопроса шкалы и баллы вариантов.
    Если скелет не поменялся, баллы старых прохождений остаются верными."""
    return (
        [s["code"] for s in data["scales"]],
        [[(o["scale"], o.get("points", 1)) for o in q["options"]] for q in data["questions"]],
    )


def structure_of_test(test):
    return (
        [s.code for s in test.scales.all()],
        [[(o.scale.code, o.points) for o in q.options.select_related("scale")]
         for q in test.questions.all()],
    )


def update_texts(test, data):
    save_test_fields(test, data)
    for scale, item in zip(test.scales.all(), data["scales"]):
        scale.name = item["name"]
        scale.description = item.get("description", "")
        scale.subject = item.get("subject", "")
        scale.save()
        # На расшифровки ответы не ссылаются, их можно пересоздать
        scale.interpretations.all().delete()
        create_interpretations(scale, item)
    for question, item in zip(test.questions.all(), data["questions"]):
        question.text = item.get("text", "")
        question.save()
        for option, option_item in zip(question.options.all(), item["options"]):
            option.text = option_item["text"]
            option.save()


def save_test_fields(test, data):
    test.title = data["title"]
    test.description = data.get("description", "")
    test.instruction = data.get("instruction", "")
    test.source = data.get("source", "")
    test.kind = data.get("kind", Test.Kind.CAREER)
    test.is_active = data.get("is_active", True)
    test.save()


def create_interpretations(scale, item):
    Interpretation.objects.bulk_create(
        Interpretation(
            scale=scale, min_points=i["min"], max_points=i["max"],
            level=i["level"], text=i["text"],
        )
        for i in item["interpretations"]
    )


def create_content(test, data):
    scales = {}
    for order, item in enumerate(data["scales"], start=1):
        scale = Scale.objects.create(
            test=test, code=item["code"], name=item["name"],
            description=item.get("description", ""), order=order,
            subject=item.get("subject", ""),
        )
        scales[scale.code] = scale
        create_interpretations(scale, item)

    for number, item in enumerate(data["questions"], start=1):
        question = Question.objects.create(test=test, order=number, text=item.get("text", ""))
        Option.objects.bulk_create(
            Option(
                question=question, order=order, text=o["text"],
                scale=scales[o["scale"]], points=o.get("points", 1),
            )
            for order, o in enumerate(item["options"], start=1)
        )
