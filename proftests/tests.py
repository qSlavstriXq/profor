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
