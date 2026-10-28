import copy

from django.test import SimpleTestCase, TestCase

from .loader import DATA_DIR, TestDataError, load_test, read_test_file
from .models import Attempt, Participant, generate_participant_code
from .scoring import calculate_scores, interpret, max_points, ranked, validate_test_data


def small_test_data():
    """Маленький тест на 2 вопроса и 2 шкалы для проверок."""
    levels = [
        {"min": 0, "max": 0, "level": "низкая", "text": "..."},
        {"min": 1, "max": 2, "level": "высокая", "text": "..."},
    ]
    return {
        "code": "mini",
        "title": "Мини-тест",
        "scales": [
            {"code": "a", "name": "Шкала А", "interpretations": copy.deepcopy(levels)},
            {"code": "b", "name": "Шкала Б", "interpretations": copy.deepcopy(levels)},
        ],
        "questions": [
            {"options": [{"text": "А1", "scale": "a"}, {"text": "Б1", "scale": "b"}]},
            {"options": [{"text": "А2", "scale": "a"}, {"text": "Б2", "scale": "b"}]},
        ],
    }


class TestValidation(SimpleTestCase):
    def test_correct_data_has_no_errors(self):
        self.assertEqual(validate_test_data(small_test_data()), [])

    def test_unknown_scale(self):
        data = small_test_data()
        data["questions"][0]["options"][0]["scale"] = "zzz"
        self.assertIn("вопрос 1: неизвестная шкала 'zzz'", validate_test_data(data))

    def test_gap_in_interpretations(self):
        data = small_test_data()
        data["scales"][0]["interpretations"][1]["min"] = 2  # балл 1 без расшифровки
        self.assertEqual(len(validate_test_data(data)), 1)

    def test_interpretations_must_reach_max(self):
        data = small_test_data()
        data["scales"][1]["interpretations"][1]["max"] = 1  # максимум 2 балла
        self.assertEqual(len(validate_test_data(data)), 1)

    def test_max_points(self):
        self.assertEqual(max_points(small_test_data(), "a"), 2)

    def test_klimov_file_is_valid(self):
        data = read_test_file(DATA_DIR / "klimov_ddo.json")
        self.assertEqual(validate_test_data(data), [])
        self.assertEqual(len(data["questions"]), 20)
        # В ДДО по каждой шкале ровно 8 утверждений
        for scale in data["scales"]:
            self.assertEqual(max_points(data, scale["code"]), 8)


class TestScoring(SimpleTestCase):
    def test_scales_without_answers_get_zero(self):
        scores = calculate_scores(["a", "b"], [{"scale": "a", "points": 1}])
        self.assertEqual(scores, {"a": 1, "b": 0})

    def test_points_add_up(self):
        chosen = [{"scale": "a", "points": 1}, {"scale": "a", "points": 2}]
        self.assertEqual(calculate_scores(["a"], chosen), {"a": 3})

    def test_interpret_finds_range(self):
        levels = small_test_data()["scales"][0]["interpretations"]
        self.assertEqual(interpret(0, levels)["level"], "низкая")
        self.assertEqual(interpret(2, levels)["level"], "высокая")
        self.assertIsNone(interpret(5, levels))

    def test_ranked_keeps_order_on_tie(self):
        self.assertEqual(
            ranked({"a": 1, "b": 3, "c": 1}),
            [("b", 3), ("a", 1), ("c", 1)],
        )


class TestParticipantCode(SimpleTestCase):
    def test_code_format(self):
        code = generate_participant_code()
        self.assertRegex(code, r"^P-[2-9A-HJKMNP-Z]{6}$")


class TestLoader(TestCase):
    def test_load_creates_everything(self):
        test = load_test(small_test_data())
        self.assertEqual(test.scales.count(), 2)
        self.assertEqual(test.questions.count(), 2)
        self.assertEqual(test.questions.first().options.count(), 2)

    def test_reload_replaces_content(self):
        load_test(small_test_data())
        data = small_test_data()
        data["title"] = "Новое название"
        test = load_test(data)
        self.assertEqual(test.title, "Новое название")
        self.assertEqual(test.questions.count(), 2)  # не задвоились

    def test_bad_data_is_rejected(self):
        data = small_test_data()
        del data["scales"]
        with self.assertRaises(TestDataError):
            load_test(data)

    def test_cannot_reload_test_with_attempts(self):
        test = load_test(small_test_data())
        Attempt.objects.create(participant=Participant.objects.create(), test=test)
        with self.assertRaises(TestDataError):
            load_test(small_test_data())


class TestSitePages(TestCase):
    def test_all_sections_open(self):
        load_test(small_test_data())
        for url in ["/", "/about/", "/tests/", "/tests/mini/", "/tests/mini/take/",
                    "/tests/my/", "/programs/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_unknown_test_is_404(self):
        self.assertEqual(self.client.get("/tests/nope/").status_code, 404)


class TestTakeTest(TestCase):
    def setUp(self):
        self.test = load_test(small_test_data())
        self.questions = list(self.test.questions.prefetch_related("options"))

    def answer(self, picks):
        """picks: номер варианта (0 или 1) для каждого вопроса по порядку."""
        data = {
            f"q{question.pk}": question.options.all()[pick].pk
            for question, pick in zip(self.questions, picks)
        }
        return self.client.post("/tests/mini/take/", data)

    def test_full_answers_save_attempt_and_show_result(self):
        response = self.answer([0, 1])  # одна «А», одна «Б»
        attempt = Attempt.objects.get()
        self.assertRedirects(response, f"/tests/result/{attempt.pk}/")
        self.assertEqual(attempt.scores, {"a": 1, "b": 1})
        self.assertEqual(attempt.answers.count(), 2)

        page = self.client.get(f"/tests/result/{attempt.pk}/")
        self.assertContains(page, attempt.participant.code)

    def test_missing_answer_shows_form_again(self):
        response = self.answer([0])  # на второй вопрос не ответили
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Пропущены: 2")
        self.assertFalse(Attempt.objects.exists())
        self.assertFalse(Participant.objects.exists())  # участник не создаётся зря

    def test_option_from_other_question_is_ignored(self):
        first, second = self.questions
        data = {
            f"q{first.pk}": second.options.first().pk,  # чужой вариант
            f"q{second.pk}": second.options.first().pk,
        }
        response = self.client.post("/tests/mini/take/", data)
        self.assertContains(response, "Пропущены: 1")

    def test_second_test_uses_same_participant(self):
        self.answer([0, 0])
        self.answer([1, 1])
        self.assertEqual(Participant.objects.count(), 1)
        self.assertEqual(Attempt.objects.count(), 2)

    def test_other_people_cannot_see_result(self):
        self.answer([0, 0])
        attempt = Attempt.objects.get()
        self.client.logout()  # новая сессия, как у другого человека
        self.client.cookies.clear()
        self.assertEqual(self.client.get(f"/tests/result/{attempt.pk}/").status_code, 404)

    def test_return_by_code(self):
        self.answer([0, 0])
        code = Participant.objects.get().code
        self.client.cookies.clear()

        response = self.client.post("/tests/my/", {"code": code.lower()})
        self.assertRedirects(response, "/tests/my/")
        self.assertContains(self.client.get("/tests/my/"), "Мини-тест")

    def test_wrong_code(self):
        response = self.client.post("/tests/my/", {"code": "P-AAAAAA"})
        self.assertContains(response, "Такого кода нет")

    def test_forget_code(self):
        self.answer([0, 0])
        self.client.post("/tests/my/forget/")
        self.assertContains(self.client.get("/tests/my/"), "введите свой код")


class TestDirectionsMapping(SimpleTestCase):
    """Таблица «тип профессий → направления обучения»."""

    def test_klimov_mapping_is_valid(self):
        from .directions import load_mapping, validate_mapping

        test = read_test_file(DATA_DIR / "klimov_ddo.json")
        mapping = load_mapping(test["code"])
        self.assertIsNotNone(mapping)
        self.assertEqual(validate_mapping(mapping, {s["code"] for s in test["scales"]}), [])

    def test_validation_finds_errors(self):
        from .directions import validate_mapping

        data = {"scales": {"zzz": {"groups": ["9"], "codes": ["09.03"]}}}
        self.assertEqual(len(validate_mapping(data, {"signs"})), 3)

    def test_group_and_exact_code(self):
        from .directions import matching_scales

        # Программная инженерия: группа 09 у «знаковой системы»
        self.assertEqual(matching_scales("klimov-ddo", "09.03.04", ["signs", "art"]), ["signs"])
        # Менеджмент: вся группа 38 у «знаковой», а отдельным кодом ещё и у «человек — человек»
        self.assertEqual(matching_scales("klimov-ddo", "38.03.02", ["people", "signs"]), ["people", "signs"])
        self.assertEqual(matching_scales("klimov-ddo", "", ["signs"]), [])
        self.assertEqual(matching_scales("no-such-test", "09.03.04", ["signs"]), [])


class TestFormatShortcuts(SimpleTestCase):
    """Сокращения формата: шкала ответов, обратные вопросы, правильный ответ."""

    def test_answer_scale_and_reverse(self):
        from .scoring import expand_test_data

        data = expand_test_data({
            "answer_scale": [{"text": "Нет", "points": 1}, {"text": "Да", "points": 3}],
            "questions": [{"text": "А", "scale": "s"}, {"text": "Б", "scale": "s", "reverse": True}],
        })
        direct, reverse = data["questions"]
        self.assertEqual([(o["text"], o["scale"], o["points"]) for o in direct["options"]],
                         [("Нет", "s", 1), ("Да", "s", 3)])
        self.assertEqual([o["points"] for o in reverse["options"]], [3, 1])

    def test_correct_answer(self):
        from .scoring import expand_test_data

        data = expand_test_data({"questions": [{"scale": "alg", "options": [
            {"text": "1", "correct": False}, {"text": "2", "correct": True},
        ]}]})
        self.assertEqual([o["points"] for o in data["questions"][0]["options"]], [0, 1])

    def test_examples_are_valid(self):
        from .scoring import expand_test_data

        for name in ("personality_example.json", "knowledge_example.json"):
            data = expand_test_data(read_test_file(DATA_DIR / "examples" / name))
            self.assertEqual(validate_test_data(data), [], name)

    def test_knowledge_needs_one_correct_answer(self):
        from .scoring import expand_test_data

        data = expand_test_data(read_test_file(DATA_DIR / "examples" / "knowledge_example.json"))
        data["questions"][0]["options"][0]["correct"] = True  # теперь правильных два
        self.assertIn("ровно один правильный", " ".join(validate_test_data(data)))


class TestNewKindsLoad(TestCase):
    def test_knowledge_test_loads_with_subject_and_scores(self):
        test = load_test(read_test_file(DATA_DIR / "examples" / "knowledge_example.json"))
        self.assertEqual(test.kind, "knowledge")
        self.assertFalse(test.is_active)  # образцы на сайте не показываются
        self.assertEqual(test.scales.get(code="algebra").subject, "math")
        # Все ответы правильные: алгебра 2 из 2, геометрия 1 из 1
        participant = Participant.objects.create()
        answers = {q: q.options.get(points=1) for q in test.questions.all()}
        from .services import save_attempt
        attempt = save_attempt(participant, test, answers)
        self.assertEqual(attempt.scores, {"algebra": 2, "geometry": 1})

    def test_unknown_subject_is_rejected(self):
        data = read_test_file(DATA_DIR / "examples" / "knowledge_example.json")
        data["scales"][0]["subject"] = "astrology"
        with self.assertRaises(TestDataError):
            load_test(data)

    def test_examples_can_be_shown_and_hidden(self):
        from io import StringIO

        from django.core.management import call_command

        from .models import Test
        codes = ["personality-example", "knowledge-math-example"]
        call_command("load_tests", "--examples", stdout=StringIO())
        self.assertEqual(Test.objects.filter(code__in=codes, is_active=True).count(), 2)
        call_command("load_tests", "--hide-examples", stdout=StringIO())
        self.assertEqual(Test.objects.filter(code__in=codes, is_active=True).count(), 0)


class TestExternalImport(TestCase):
    MAPPING = {
        "source": "center", "source_name": "Центр", "participant_code_column": "Код",
        "date_column": "Дата", "tests": [{"test_name": "Тест центра", "scales": [
            {"column": "Техника", "name": "Человек — техника", "max": 8,
             "levels": [{"min": 0, "max": 4, "level": "низкий"}, {"min": 5, "max": 8, "level": "высокий"}]},
        ]}],
    }

    def setUp(self):
        self.participant = Participant.objects.create()

    def rows(self, code=None, value="6", **extra):
        row = {"Код": (code or self.participant.code).lower(), "Дата": "15.10.2026",
               "Техника": value, "ФИО": "Иванов Иван"}
        row.update(extra)
        return [row]

    def test_saves_only_mapped_data(self):
        from .external import import_rows
        from .models import ExternalResult

        report = import_rows(self.MAPPING, self.rows())
        self.assertEqual(report["saved"], 1)
        result = ExternalResult.objects.get()
        self.assertEqual(result.scales, [{"name": "Человек — техника", "value": 6, "max": 8, "level": "высокий"}])
        self.assertNotIn("Иванов", str(result.__dict__))  # имя из таблицы не сохранилось

    def test_reimport_updates_instead_of_duplicating(self):
        from .external import import_rows
        from .models import ExternalResult

        import_rows(self.MAPPING, self.rows(value="6"))
        import_rows(self.MAPPING, self.rows(value="3"))
        self.assertEqual(ExternalResult.objects.get().scales[0]["value"], 3)

    def test_unknown_code_is_reported_not_created(self):
        from .external import import_rows

        report = import_rows(self.MAPPING, self.rows(code="P-NOSUCH"))
        self.assertEqual(report["unknown_codes"], [2])
        self.assertEqual(Participant.objects.count(), 1)

    def test_bad_date_saves_nothing(self):
        from .external import import_rows
        from .models import ExternalResult

        report = import_rows(self.MAPPING, self.rows(Дата="31.02.2026"))
        self.assertTrue(report["errors"])
        self.assertFalse(ExternalResult.objects.exists())

    def test_missing_column_is_an_error(self):
        from .external import ExternalDataError, import_rows

        with self.assertRaises(ExternalDataError):
            import_rows(self.MAPPING, [{"Код": self.participant.code}])

    def test_dry_run_saves_nothing(self):
        from .external import import_rows
        from .models import ExternalResult

        report = import_rows(self.MAPPING, self.rows(), dry_run=True)
        self.assertEqual(report["saved"], 1)
        self.assertFalse(ExternalResult.objects.exists())

    def test_example_mapping_is_valid(self):
        from .external import EXTERNAL_DIR, read_mapping

        read_mapping(EXTERNAL_DIR / "example-center.json")  # не бросает ошибку

    def test_results_go_to_strategy_input(self):
        from llm.strategy import build_input, make_basis
        from .external import import_rows

        import_rows(self.MAPPING, self.rows())
        data = build_input(self.participant)
        self.assertEqual(data["external_results"][0]["test"], "Тест центра")
        self.assertEqual(len(make_basis(self.participant, {})["external"]), 1)
