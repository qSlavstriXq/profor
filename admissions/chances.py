# Расчёт шансов поступления. Не зависит от Django, поэтому легко тестируется.

# Сколько годовых приростов проходного балла добавляем к ориентиру,
# если проходной балл растёт. Значение подбирается на реальных данных.
TREND_WEIGHT = 1.0


def reference_score(passing_scores):
    """Взвешенное среднее проходных баллов: чем новее год, тем больший вес.

    Баллы идут от старого года к новому, веса 1, 2, 3, ...
    """
    weights = range(1, len(passing_scores) + 1)
    weighted_sum = sum(score * w for score, w in zip(passing_scores, weights))
    return weighted_sum / sum(weights)


def trend_per_year(passing_scores):
    """Средний годовой прирост проходного балла (от первого года к последнему)."""
    if len(passing_scores) < 2:
        return 0.0
    return (passing_scores[-1] - passing_scores[0]) / (len(passing_scores) - 1)


def expected_score(passing_scores):
    """Ожидаемый проходной балл: взвешенное среднее плюс рост, если он есть.

    Если проходной балл падает, ориентир не снижаем: осторожная оценка лучше.
    """
    growth = max(trend_per_year(passing_scores), 0)
    return reference_score(passing_scores) + TREND_WEIGHT * growth


def classify(margin):
    """По разнице между баллами школьника и ориентиром выдаёт категорию."""
    if margin >= 10:
        return "страховка"
    if margin >= -5:
        return "реалистично"
    if margin >= -20:
        return "амбициозно"
    return "очень сложно"


def evaluate(student, program):
    """Оценивает одну программу для школьника.

    student: {"math": 85, ...}
    program: {"subjects": [...], "passing_scores": [...],
              "min_scores": {"russian": 70}  # необязательно
             }

    Возвращает None, если у школьника нет нужного предмета.
    Если по какому-то предмету не хватает минимального балла,
    категория будет "недоступно".
    """
    for subject in program["subjects"]:
        if subject not in student:
            return None

    total = sum(student[subject] for subject in program["subjects"])
    reference = expected_score(program["passing_scores"])
    margin = total - reference

    min_scores = program.get("min_scores", {})
    below_minimum = [
        subject
        for subject in program["subjects"]
        if student[subject] < min_scores.get(subject, 0)
    ]

    category = "недоступно" if below_minimum else classify(margin)

    return {
        "total": total,
        "reference": reference,
        "margin": margin,
        "trend": trend_per_year(program["passing_scores"]),
        "below_minimum": below_minimum,
        "category": category,
    }