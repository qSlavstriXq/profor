# Каталог профессий: загрузка из careers/data/professions.json.
# Формат описан в careers/data/README.md

import json
import re
from pathlib import Path

from django.db import transaction

from admissions.models import Subject
from proftests.loader import DATA_DIR as TESTS_DIR

from .models import Profession

DATA_DIR = Path(__file__).resolve().parent / "data"
PROFESSIONS_FILE = DATA_DIR / "professions.json"
DIRECTION_RE = re.compile(r"\d\d(\.\d\d\.\d\d)?")


class ProfessionDataError(Exception):
    """Файл профессий содержит ошибки."""


def test_scale_codes():
    """Шкалы всех тестов из proftests/data: {"klimov-ddo": {"nature", "tech", ...}, ...}.

    Берём из файлов, а не из базы, чтобы проверять и тесты, которые ещё не загружены
    или скрыты (как черновик Голланда).
    """
    result = {}
    for path in TESTS_DIR.glob("*.json"):
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
        result[data["code"]] = {scale["code"] for scale in data.get("scales", [])}
    return result


def validate_professions(data, scales=None):
    """Возвращает список ошибок. Пустой список: файл в порядке.

    scales: шкалы тестов, как у test_scale_codes(); в тестах подставляем свои.
    """
    if scales is None:
        scales = test_scale_codes()
    errors = []
    seen = set()
    for number, item in enumerate(data.get("professions", []), start=1):
        where = f"профессия {number} ({item.get('code', 'без кода')})"
        for field in ("code", "title", "description"):
            if not item.get(field):
                errors.append(f"{where}: не заполнено поле {field}")
        if item.get("code") in seen:
            errors.append(f"{where}: код повторяется")
        seen.add(item.get("code"))
        for test_code, codes in item.get("test_scales", {}).items():
            if test_code not in scales:
                errors.append(f"{where}: теста {test_code!r} нет")
                continue
            for code in codes:
                if code not in scales[test_code]:
                    errors.append(f"{where}: у теста {test_code} нет шкалы {code!r}")
        for subject in item.get("subjects", []):
            if subject not in Subject.values:
                errors.append(f"{where}: неизвестный предмет {subject!r}")
        for direction in item.get("directions", []):
            if not DIRECTION_RE.fullmatch(direction):
                errors.append(f"{where}: направление {direction!r} должно быть вида 09 или 09.03.04")
        for link in item.get("links", []):
            if not link.get("title") or not str(link.get("url", "")).startswith("https://"):
                errors.append(f"{where}: у ссылки нужны title и url, начинающийся с https://")
    return errors


@transaction.atomic
def load_professions(data, scales=None):
    """Создаёт или обновляет профессии по коду. Профессии, которых нет в файле, удаляются."""
    errors = validate_professions(data, scales)
    if errors:
        raise ProfessionDataError("; ".join(errors))
    codes = []
    for item in data.get("professions", []):
        Profession.objects.update_or_create(
            code=item["code"],
            defaults={
                "title": item["title"],
                "description": item["description"],
                "test_scales": item.get("test_scales", {}),
                "subjects": item.get("subjects", []),
                "directions": item.get("directions", []),
                "links": item.get("links", []),
                "verified": item.get("verified", False),
            },
        )
        codes.append(item["code"])
    Profession.objects.exclude(code__in=codes).delete()
    return len(codes)
