import json
from pathlib import Path

from django.db import transaction

from .models import Interpretation, Option, Question, Scale, Test
from .scoring import validate_test_data

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
    errors = validate_test_data(data)
    if errors:
        raise TestDataError("; ".join(errors))

    test = Test.objects.filter(code=data["code"]).first()
    if test is not None:
        if test.attempts.exists():
            # Иначе старые ответы школьников потеряют связь с вопросами
            raise TestDataError(
                f"тест {data['code']} уже проходили, поменяйте code, чтобы создать новую версию"
            )
        test.scales.all().delete()  # вместе со шкалами удалятся варианты и расшифровки
        test.questions.all().delete()
    else:
        test = Test(code=data["code"])

    test.title = data["title"]
    test.description = data.get("description", "")
    test.instruction = data.get("instruction", "")
    test.source = data.get("source", "")
    test.save()

    scales = {}
    for order, item in enumerate(data["scales"], start=1):
        scale = Scale.objects.create(
            test=test, code=item["code"], name=item["name"],
            description=item.get("description", ""), order=order,
        )
        scales[scale.code] = scale
        Interpretation.objects.bulk_create(
            Interpretation(
                scale=scale, min_points=i["min"], max_points=i["max"],
                level=i["level"], text=i["text"],
            )
            for i in item["interpretations"]
        )

    for number, item in enumerate(data["questions"], start=1):
        question = Question.objects.create(test=test, order=number, text=item.get("text", ""))
        Option.objects.bulk_create(
            Option(
                question=question, order=order, text=o["text"],
                scale=scales[o["scale"]], points=o.get("points", 1),
            )
            for order, o in enumerate(item["options"], start=1)
        )
    return test
