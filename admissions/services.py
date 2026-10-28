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
        paid = _paid_chances(student_scores, program, subjects, min_scores)

        results.append({
            "id": program.pk,
            "university": program.university.short_name or program.university.name,
            "university_code": program.university.code or str(program.university.pk),
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
            "margin_points": round(result["margin"]),  # для текста: «запас 5 баллов»
            "trend": result["trend"],
            "category": result["category"],
            "below_minimum": [Subject(code).label for code in result["below_minimum"]],
            "years": len(passing_scores),
            "tuition_per_year": program.tuition_per_year,
            "paid_category": paid["category"] if paid else None,
            "paid_reference": paid["reference"] if paid else None,
            "paid_margin_points": round(paid["margin"]) if paid else None,
        })

    results.sort(key=lambda r: (CATEGORY_ORDER[r["category"]], -r["margin"]))
    return results


# Что показываем, пока школьник не выбрал категории сам: реальные варианты
DEFAULT_CATEGORIES = ["страховка", "реалистично", "амбициозно"]


def apply_filters(results, university="", categories=None, query=""):
    """Оставляет программы, подходящие под фильтры.

    university: код вуза, пусто = все вузы.
    categories: список категорий, пусто или None = все.
    query: часть названия программы или факультета, без учёта регистра.
    """
    query = query.strip().lower()
    return [
        r for r in results
        if (not university or r["university_code"] == university)
        and (not categories or r["category"] in categories)
        and (not query or query in r["name"].lower() or query in r["faculty"].lower())
    ]


def _paid_chances(student_scores, program, subjects, min_scores):
    """Шансы на платное: тот же расчёт, что и на бюджет, но по проходным баллам на платное.
    Если вуз их не публикует, возвращает None: шансы не выдумываем."""
    paid_scores = [
        stat.passing_score_paid
        for stat in program.stats.all()
        if stat.passing_score_paid is not None
    ]
    if not paid_scores:
        return None
    return evaluate(
        student_scores,
        {"subjects": subjects, "passing_scores": paid_scores, "min_scores": min_scores},
    )


def _latest_places(program):
    """Бюджетные места за последний год, по которому они известны."""
    stats = [stat for stat in program.stats.all() if stat.budget_places is not None]
    return stats[-1].budget_places if stats else None
