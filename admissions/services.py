from django.conf import settings

from .chances import evaluate
from .models import Program, Subject

# Порядок показа: сначала самое реалистичное
CATEGORY_ORDER = {
    "реалистично": 0,
    "амбициозно": 1,
    "страховка": 2,
    "очень сложно": 3,
    "недоступно": 4,
}


def exam_subjects(exams):
    """Предметы программы в формате движка: группа выбора становится списком.

    [math, russian, physics(гр. 1), informatics(гр. 1)]
    -> ["math", "russian", ["physics", "informatics"]]
    """
    subjects = []
    groups = {}
    for exam in exams:
        if exam.choice_group is None:
            subjects.append(exam.subject)
        elif exam.choice_group in groups:
            groups[exam.choice_group].append(exam.subject)
        else:
            groups[exam.choice_group] = [exam.subject]
            subjects.append(groups[exam.choice_group])  # тот же список, дополнится позже
    return subjects


def build_recommendations(student_scores):
    """Берёт программы из базы и оценивает их для школьника.

    Непроверенные программы участвуют, только если это разрешено
    настройкой SHOW_UNVERIFIED_DATA (в .env).
    """
    programs = Program.objects.select_related("university").prefetch_related("exams", "stats")
    if not settings.SHOW_UNVERIFIED_DATA:
        programs = programs.filter(verified=True, university__verified=True)

    results = []
    for program in programs:
        passing_scores = [
            stat.passing_score_budget
            for stat in program.stats.all()
            if stat.passing_score_budget is not None
        ]
        exams = list(program.exams.all())
        subjects = exam_subjects(exams)
        min_scores = {exam.subject: exam.min_score for exam in exams}
        if not passing_scores or not subjects:
            continue  # данных не хватает, программу не показываем

        result = evaluate(
            student_scores,
            {
                "subjects": subjects,
                "passing_scores": passing_scores,
                "min_scores": min_scores,
            },
        )
        if result is None:
            continue  # у школьника нет нужного предмета

        results.append({
            "id": program.pk,
            "university": program.university.short_name or program.university.name,
            "name": program.name,
            "faculty": program.faculty,
            "direction_code": program.direction_code,
            "subjects": [Subject(code).label for code in result["subjects"]],
            "budget_places": _latest_places(program),
            "verified": program.verified and program.university.verified,
            "source_url": program.source_url,
            "total": result["total"],
            "reference": result["reference"],
            "margin": result["margin"],
            "trend": result["trend"],
            "category": result["category"],
            "below_minimum": [Subject(code).label for code in result["below_minimum"]],
            "years": len(passing_scores),
        })

    results.sort(key=lambda r: (CATEGORY_ORDER[r["category"]], -r["margin"]))
    return results


def _latest_places(program):
    """Бюджетные места за последний год, по которому они известны."""
    stats = [stat for stat in program.stats.all() if stat.budget_places is not None]
    return stats[-1].budget_places if stats else None
