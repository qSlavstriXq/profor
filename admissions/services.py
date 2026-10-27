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


def build_recommendations(student_scores):
    """Берёт проверенные программы из базы и оценивает их для школьника."""
    programs = (
        Program.objects.filter(verified=True)
        .select_related("university")
        .prefetch_related("exams", "stats")
    )

    results = []
    for program in programs:
        passing_scores = [
            stat.passing_score_budget
            for stat in program.stats.all()
            if stat.passing_score_budget is not None
        ]
        exams = list(program.exams.all())
        subjects = [exam.subject for exam in exams]
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
            "university": program.university.name,
            "name": program.name,
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