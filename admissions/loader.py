# Загрузка вузов и программ из JSON-файлов в папке admissions/data.
# Один файл = один вуз. Образец формата: admissions/data/README.md

import json
from pathlib import Path

from django.db import transaction

from .models import AdmissionStat, Program, ProgramExam, Subject, University

DATA_DIR = Path(__file__).resolve().parent / "data"

SUBJECTS = set(Subject.values)
STUDY_FORMS = set(Program.StudyForm.values)


class UniversityDataError(Exception):
    """Файл вуза содержит ошибки."""


def read_university_file(path):
    with open(path, encoding="utf-8") as file:
        return json.load(file)


def _check_exam(exam, where, errors):
    if exam.get("subject") not in SUBJECTS:
        errors.append(f"{where}: неизвестный предмет {exam.get('subject')!r}")
    score = exam.get("min_score", 0)
    if not isinstance(score, int) or not 0 <= score <= 100:
        errors.append(f"{where}: min_score должен быть числом от 0 до 100")


def validate_university_data(data):
    """Возвращает список ошибок. Пустой список: файл в порядке."""
    errors = []
    for field in ("code", "name"):
        if not data.get(field):
            errors.append(f"не заполнено поле {field}")

    seen = set()
    for number, program in enumerate(data.get("programs", []), start=1):
        where = f"программа {number} ({program.get('name', 'без названия')})"
        if not program.get("name"):
            errors.append(f"{where}: нет названия")
        study_form = program.get("study_form", "full_time")
        if study_form not in STUDY_FORMS:
            errors.append(f"{where}: неизвестная форма обучения {study_form!r}")

        key = (program.get("faculty", ""), program.get("name"), study_form)
        if key in seen:
            errors.append(f"{where}: повторяется (факультет, название и форма совпадают)")
        seen.add(key)

        for exam in program.get("exams", []):
            if "one_of" in exam:
                if len(exam["one_of"]) < 2:
                    errors.append(f"{where}: в one_of нужно минимум два предмета")
                for option in exam["one_of"]:
                    _check_exam(option, where, errors)
            else:
                _check_exam(exam, where, errors)

        years = set()
        for stat in program.get("stats", []):
            year = stat.get("year")
            if not isinstance(year, int) or not 2000 <= year <= 2100:
                errors.append(f"{where}: неверный год {year!r}")
            if year in years:
                errors.append(f"{where}: год {year} указан дважды")
            years.add(year)
            for field in ("passing_score_budget", "passing_score_paid"):
                score = stat.get(field)
                if score is not None and (not isinstance(score, int) or not 0 <= score <= 500):
                    errors.append(f"{where}, {year}: {field} должен быть числом от 0 до 500")
    return errors


@transaction.atomic
def load_university(data):
    """Создаёт или обновляет вуз и его программы по данным из JSON.

    Программы находим по (факультет, название, форма обучения) и обновляем,
    поэтому их id не меняются и сохранённые стратегии школьников не ломаются.
    Программы, которых больше нет в файле, удаляются.
    """
    errors = validate_university_data(data)
    if errors:
        raise UniversityDataError("; ".join(errors))

    university, _ = University.objects.update_or_create(
        code=data["code"],
        defaults={
            "name": data["name"],
            "short_name": data.get("short_name", ""),
            "city": data.get("city", "Москва"),
            "website": data.get("website", ""),
            "has_dormitory": data.get("has_dormitory", False),
            "source_url": data.get("source_url", ""),
            "verified": data.get("verified", False),
        },
    )

    kept_ids = []
    for item in data.get("programs", []):
        program, _ = Program.objects.update_or_create(
            university=university,
            faculty=item.get("faculty", ""),
            name=item["name"],
            study_form=item.get("study_form", Program.StudyForm.FULL_TIME),
            defaults={
                "direction_code": item.get("direction_code", ""),
                "tuition_per_year": item.get("tuition_per_year"),
                "source_url": item.get("source_url", data.get("source_url", "")),
                "verified": item.get("verified", False),
            },
        )
        kept_ids.append(program.pk)

        # Предметы и статистику проще пересоздать: на них никто не ссылается
        program.exams.all().delete()
        for group, exam in enumerate(item.get("exams", []), start=1):
            if "one_of" in exam:
                options, choice_group = exam["one_of"], group
            else:
                options, choice_group = [exam], None
            ProgramExam.objects.bulk_create(
                ProgramExam(
                    program=program, subject=o["subject"],
                    min_score=o.get("min_score", 0), choice_group=choice_group,
                )
                for o in options
            )

        program.stats.all().delete()
        AdmissionStat.objects.bulk_create(
            AdmissionStat(
                program=program, year=s["year"],
                passing_score_budget=s.get("passing_score_budget"),
                budget_places=s.get("budget_places"),
                passing_score_paid=s.get("passing_score_paid"),
                paid_places=s.get("paid_places"),
                source_url=s.get("source_url", ""),
            )
            for s in item.get("stats", [])
        )

    university.programs.exclude(pk__in=kept_ids).delete()
    return university
