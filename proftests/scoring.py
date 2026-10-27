# Подсчёт результатов профтестов и проверка файлов с тестами.
# Не зависит от Django, поэтому легко тестируется (как admissions/chances.py).


def validate_test_data(data):
    """Проверяет содержимое JSON-файла теста. Возвращает список ошибок.

    Пустой список значит, что файл в порядке.
    """
    errors = []
    for field in ("code", "title", "scales", "questions"):
        if not data.get(field):
            errors.append(f"нет поля {field}")
    if errors:
        return errors

    scale_codes = [scale["code"] for scale in data["scales"]]
    if len(scale_codes) != len(set(scale_codes)):
        errors.append("коды шкал повторяются")

    for number, question in enumerate(data["questions"], start=1):
        options = question.get("options", [])
        if len(options) < 2:
            errors.append(f"вопрос {number}: меньше двух вариантов ответа")
        for option in options:
            if option.get("scale") not in scale_codes:
                errors.append(f"вопрос {number}: неизвестная шкала {option.get('scale')!r}")

    for scale in data["scales"]:
        errors.extend(_check_interpretations(scale, max_points(data, scale["code"])))
    return errors


def max_points(data, scale_code):
    """Сколько баллов максимум можно набрать по шкале.

    В каждом вопросе выбирается один вариант, поэтому берём лучший
    вариант для этой шкалы в каждом вопросе.
    """
    total = 0
    for question in data["questions"]:
        points = [
            option.get("points", 1)
            for option in question.get("options", [])
            if option.get("scale") == scale_code
        ]
        total += max(points, default=0)
    return total


def _check_interpretations(scale, top):
    """Расшифровки должны покрывать все баллы от 0 до top без дыр и наложений."""
    ranges = sorted((item["min"], item["max"]) for item in scale.get("interpretations", []))
    if not ranges:
        return [f"шкала {scale['code']}: нет расшифровок"]

    expected_start = 0
    for low, high in ranges:
        if low != expected_start or high < low:
            return [f"шкала {scale['code']}: расшифровки должны идти подряд от 0 до {top}"]
        expected_start = high + 1
    if expected_start - 1 != top:
        return [f"шкала {scale['code']}: расшифровки должны идти подряд от 0 до {top}"]
    return []


def calculate_scores(scale_codes, chosen_options):
    """Складывает баллы по шкалам.

    scale_codes: все шкалы теста, например ["nature", "tech"]
    chosen_options: выбранные варианты [{"scale": "nature", "points": 1}, ...]

    Шкалы без баллов тоже попадают в ответ с нулём,
    чтобы в результате были видны все шкалы.
    """
    scores = {code: 0 for code in scale_codes}
    for option in chosen_options:
        scores[option["scale"]] += option["points"]
    return scores


def interpret(points, interpretations):
    """Находит расшифровку, в диапазон которой попали баллы."""
    for item in interpretations:
        if item["min"] <= points <= item["max"]:
            return item
    return None


def ranked(scores):
    """Шкалы от самой выраженной к самой слабой.

    При равных баллах сохраняется исходный порядок шкал.
    """
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
