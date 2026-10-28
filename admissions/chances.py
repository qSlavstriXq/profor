# Расчёт шансов поступления. Не зависит от Django, поэтому легко тестируется.

# Сколько годовых приростов проходного балла добавляем к ориентиру,
# если проходной балл растёт. Значение подбирается на реальных данных.
TREND_WEIGHT = 1.0

# Запас баллов над ориентиром, начиная с которого программа считается «страховкой».
# Проверено на реальных данных (tools/backtest_chances.py): в 90% случаев
# проходной балл оказывается выше ожидаемого не больше чем на 14 баллов.
SAFE_MARGIN = 15


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
    if margin >= SAFE_MARGIN:
        return "страховка"
    if margin >= -5:
        return "реалистично"
    if margin >= -20:
        return "амбициозно"
    return "очень сложно"


def choose_subjects(student, subjects, min_scores):
    """Выбирает, какие предметы школьника засчитать.

    subjects: ["math", "russian", ["physics", "informatics"]]
    Список внутри списка означает «один предмет на выбор». Берём тот,
    где школьник проходит минимальный порог, а среди них самый высокий балл.

    Возвращает None, если какого-то предмета у школьника нет.
    """
    chosen = []
    for item in subjects:
        options = [item] if isinstance(item, str) else item
        available = [s for s in options if s in student]
        if not available:
            return None
        chosen.append(max(
            available,
            key=lambda s: (student[s] >= min_scores.get(s, 0), student[s]),
        ))
    return chosen


def evaluate(student, program):
    """Оценивает одну программу для школьника.

    student: {"math": 85, ...}
    program: {"subjects": ["math", ["physics", "informatics"]],
              "passing_scores": [...],
              "min_scores": {"russian": 70}  # необязательно
             }

    Возвращает None, если у школьника нет нужного предмета.
    Если по какому-то предмету не хватает минимального балла,
    категория будет "недоступно".
    """
    min_scores = program.get("min_scores", {})
    subjects = choose_subjects(student, program["subjects"], min_scores)
    if subjects is None:
        return None

    total = sum(student[subject] for subject in subjects)
    reference = expected_score(program["passing_scores"])
    margin = total - reference

    below_minimum = [
        subject
        for subject in subjects
        if student[subject] < min_scores.get(subject, 0)
    ]

    category = "недоступно" if below_minimum else classify(margin)

    return {
        "subjects": subjects,
        "total": total,
        "reference": reference,
        "margin": margin,
        "trend": trend_per_year(program["passing_scores"]),
        "below_minimum": below_minimum,
        "category": category,
    }