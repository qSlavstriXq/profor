# ВСЕ ДАННЫЕ ВЫМЫШЛЕННЫЕ, только для обучения.

# Баллы школьника по предметам ЕГЭ (ключ: предмет, значение: балл)
STUDENT = {"math": 85, "informatics": 80, "russian": 88, "physics": 70}

# Список программ. Каждая программа это словарь с её данными.
PROGRAMS = [
    {
        "university": "Университет А",
        "name": "Прикладная информатика",
        "subjects": ["math", "informatics", "russian"],
        "passing_scores": [245, 250, 258],  # проходные за 3 года, от старого к новому
    },
    {
        "university": "Университет Б",
        "name": "Экономика",
        "subjects": ["math", "russian", "social"],
        "passing_scores": [240, 246, 249],
    },
    {
        "university": "Университет В",
        "name": "Физика",
        "subjects": ["math", "physics", "russian"],
        "passing_scores": [220, 226, 228],
    },
    {
        "university": "Университет Г",
        "name": "Прикладная математика",
        "subjects": ["math", "informatics", "russian"],
        "passing_scores": [262, 266, 270],
    },
]


def reference_score(passing_scores):
    """Ориентир: средний проходной балл за прошлые годы."""
    return sum(passing_scores) / len(passing_scores)


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
    """Оценивает одну программу. Если не хватает предмета, возвращает None."""
    for subject in program["subjects"]:
        if subject not in student:
            return None

    total = sum(student[subject] for subject in program["subjects"])
    reference = reference_score(program["passing_scores"])
    margin = total - reference

    return {
        "total": total,
        "reference": reference,
        "margin": margin,
        "category": classify(margin),
    }


def main():
    for program in PROGRAMS:
        result = evaluate(STUDENT, program)
        title = f"{program['university']}, {program['name']}"
        if result is None:
            print(f"{title}: нет нужного предмета, пропускаем")
        else:
            print(
                f"{title}: {result['category']} "
                f"(ваши {result['total']}, ориентир {result['reference']:.0f}, "
                f"разница {result['margin']:+.0f})"
            )


if __name__ == "__main__":
    main()