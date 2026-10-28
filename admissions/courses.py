# Каталог курсов: загрузка из admissions/data/courses/courses.json.
# Формат описан в admissions/data/courses/README.md

import re

from django.db import transaction

from .loader import DATA_DIR
from .models import Course

COURSES_FILE = DATA_DIR / "courses" / "courses.json"
DIRECTION_RE = re.compile(r"\d\d(\.\d\d\.\d\d)?")


class CourseDataError(Exception):
    """Файл каталога содержит ошибки."""


def validate_courses(data):
    """Возвращает список ошибок. Пустой список: файл в порядке."""
    errors = []
    seen = set()
    for number, item in enumerate(data.get("courses", []), start=1):
        where = f"курс {number} ({item.get('code', 'без кода')})"
        for field in ("code", "title", "provider", "url"):
            if not item.get(field):
                errors.append(f"{where}: не заполнено поле {field}")
        if item.get("code") in seen:
            errors.append(f"{where}: код повторяется")
        seen.add(item.get("code"))
        if not str(item.get("url", "")).startswith("https://"):
            errors.append(f"{where}: url должен начинаться с https://")
        for direction in item.get("directions", []):
            if not DIRECTION_RE.fullmatch(direction):
                errors.append(f"{where}: направление {direction!r} должно быть вида 09 или 09.03.04")
    return errors


@transaction.atomic
def load_courses(data):
    """Создаёт или обновляет курсы по коду. Курсы, которых нет в файле, удаляются."""
    errors = validate_courses(data)
    if errors:
        raise CourseDataError("; ".join(errors))
    codes = []
    for item in data.get("courses", []):
        Course.objects.update_or_create(
            code=item["code"],
            defaults={
                "title": item["title"],
                "provider": item["provider"],
                "url": item["url"],
                "description": item.get("description", ""),
                "directions": item.get("directions", []),
                "professions": item.get("professions", ""),
                "is_free": item.get("is_free"),
                "verified": item.get("verified", False),
            },
        )
        codes.append(item["code"])
    Course.objects.exclude(code__in=codes).delete()
    return len(codes)
