# Каталог курсов: загрузка из admissions/data/courses/courses.json.
# Формат описан в admissions/data/courses/README.md

import re

from django.db import transaction

from .loader import DATA_DIR
from .models import Course, Subject

COURSES_FILE = DATA_DIR / "courses" / "courses.json"
DIRECTION_RE = re.compile(r"\d\d(\.\d\d\.\d\d)?")
GRADES = {9, 10, 11}  # классы, для которых работает сайт


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
        if item.get("kind", Course.Kind.COURSE) not in Course.Kind.values:
            errors.append(f"{where}: неизвестный вид {item.get('kind')!r}")
        for grade in item.get("grades", []):
            if grade not in GRADES:
                errors.append(f"{where}: класс {grade!r} должен быть 9, 10 или 11")
        for subject in item.get("subjects", []):
            if subject not in Subject.values:
                errors.append(f"{where}: неизвестный предмет {subject!r}")
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
                "kind": item.get("kind", Course.Kind.COURSE),
                "title": item["title"],
                "provider": item["provider"],
                "url": item["url"],
                "description": item.get("description", ""),
                "directions": item.get("directions", []),
                "grades": item.get("grades", []),
                "subjects": item.get("subjects", []),
                "professions": item.get("professions", ""),
                "is_free": item.get("is_free"),
                "verified": item.get("verified", False),
            },
        )
        codes.append(item["code"])
    Course.objects.exclude(code__in=codes).delete()
    return len(codes)
