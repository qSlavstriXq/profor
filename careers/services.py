# Подбор профессий по результатам профтестов и данные для страницы профессии.

from django.conf import settings

from admissions.models import Program, Subject
from proftests.models import Scale
from proftests.scoring import ranked

from .models import Profession

# Сколько самых выраженных шкал теста учитываем при подборе (как в стратегии)
TOP_SCALES = 2


def visible_professions():
    """Профессии для показа на сайте. Непроверенные скрываются настройкой SHOW_UNVERIFIED_DATA."""
    professions = Profession.objects.all()
    if not settings.SHOW_UNVERIFIED_DATA:
        professions = professions.filter(verified=True)
    return professions


def filter_by_subjects(professions, subject_codes):
    """Профессии, где пригодятся все выбранные предметы."""
    return [p for p in professions if all(code in p.subjects for code in subject_codes)]


def subject_choices(professions, selected):
    """Предметы для фильтра: только те, что встречаются в каталоге, в порядке Subject."""
    present = {code for profession in professions for code in profession.subjects}
    return [
        {"code": code, "name": name, "checked": code in selected}
        for code, name in Subject.choices if code in present
    ]


def professions_for_scales(test_code, scale_codes):
    """Профессии, которые подходят хотя бы одной шкале: [(профессия, [коды шкал])].

    scale_codes идут от самой сильной шкалы к слабой. Первыми идут профессии,
    подходящие сразу нескольким шкалам, затем подходящие самой сильной.
    """
    result = []
    for profession in visible_professions():
        fits = [code for code in scale_codes if code in profession.test_scales.get(test_code, [])]
        if fits:
            result.append((profession, fits))
    # sorted не меняет порядок равных, поэтому внутри группы остаётся алфавит
    return sorted(result, key=lambda pair: (-len(pair[1]), scale_codes.index(pair[1][0])))


def professions_for_attempt(attempt):
    """Профессии по самым выраженным шкалам прохождения теста.

    Возвращает [{"profession": ..., "fits": [названия шкал]}].
    """
    strong = [code for code, points in ranked(attempt.scores)[:TOP_SCALES] if points > 0]
    names = {scale.code: scale.name for scale in attempt.test.scales.all()}
    return [
        {"profession": profession, "fits": [names[code] for code in fits]}
        for profession, fits in professions_for_scales(attempt.test.code, strong)
    ]


def profession_details(profession):
    """Данные для страницы профессии: предметы, типы по тестам, программы из нашей базы."""
    subjects = [Subject(code).label for code in profession.subjects]

    # Только тесты, которые видны на сайте: черновики (например, Голланд) не показываем
    scales = Scale.objects.filter(
        test__code__in=profession.test_scales.keys(), test__is_active=True,
    ).select_related("test")
    tests = {}
    for scale in scales:
        if scale.code in profession.test_scales[scale.test.code]:
            tests.setdefault(scale.test.title, []).append(scale.name)

    programs = Program.objects.select_related("university").order_by("university__name", "name")
    if not settings.SHOW_UNVERIFIED_DATA:
        programs = programs.filter(verified=True)
    programs = [p for p in programs if p.direction_code and profession.fits_direction(p.direction_code)]

    return {
        "subjects": subjects,
        "tests": [{"title": title, "scales": names} for title, names in tests.items()],
        "programs": programs,
    }
