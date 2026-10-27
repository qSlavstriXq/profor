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
