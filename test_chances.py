import unittest

from admissions.chances import (
    classify,
    evaluate,
    expected_score,
    reference_score,
    trend_per_year,
)


class TestReferenceAndTrend(unittest.TestCase):
    def test_reference_gives_more_weight_to_recent_years(self):
        self.assertAlmostEqual(reference_score([240, 250, 260]), 253.33, places=2)

    def test_reference_single_year(self):
        self.assertEqual(reference_score([200]), 200)

    def test_trend_growth(self):
        self.assertAlmostEqual(trend_per_year([235, 241, 248, 261]), 8.67, places=2)

    def test_trend_single_year_is_zero(self):
        self.assertEqual(trend_per_year([200]), 0)

    def test_expected_adds_growth(self):
        self.assertAlmostEqual(expected_score([235, 241, 248, 261]), 259.17, places=2)

    def test_expected_ignores_falling_trend(self):
        self.assertAlmostEqual(expected_score([300, 290, 280]), 286.67, places=2)


class TestClassify(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(classify(10), "страховка")
        self.assertEqual(classify(9), "реалистично")
        self.assertEqual(classify(-5), "реалистично")
        self.assertEqual(classify(-6), "амбициозно")
        self.assertEqual(classify(-20), "амбициозно")
        self.assertEqual(classify(-21), "очень сложно")


class TestEvaluate(unittest.TestCase):
    def make_program(self, **extra):
        program = {
            "subjects": ["math", "russian"],
            "passing_scores": [170, 170, 170],
        }
        program.update(extra)
        return program

    def test_missing_subject_returns_none(self):
        program = self.make_program(subjects=["math", "social"])
        self.assertIsNone(evaluate({"math": 80}, program))

    def test_insurance(self):
        result = evaluate({"math": 90, "russian": 90}, self.make_program())
        self.assertEqual(result["category"], "страховка")

    def test_below_minimum_makes_program_unavailable(self):
        program = self.make_program(min_scores={"russian": 70})
        result = evaluate({"math": 100, "russian": 65}, program)
        self.assertEqual(result["category"], "недоступно")
        self.assertEqual(result["below_minimum"], ["russian"])

    def test_minimum_met_does_not_block(self):
        program = self.make_program(min_scores={"russian": 70})
        result = evaluate({"math": 90, "russian": 90}, program)
        self.assertEqual(result["below_minimum"], [])
        self.assertEqual(result["category"], "страховка")

    def test_growing_program_is_harder_than_flat_average(self):
        program = {
            "subjects": ["math", "informatics", "russian"],
            "passing_scores": [235, 241, 248, 261],
        }
        student = {"math": 90, "informatics": 90, "russian": 88}  # сумма 268
        result = evaluate(student, program)
        self.assertEqual(result["category"], "реалистично")

    def test_single_year_of_statistics(self):
        # Всего один год: роста посчитать нельзя, ориентир равен этому баллу
        program = self.make_program(passing_scores=[165])
        result = evaluate({"math": 85, "russian": 85}, program)  # сумма 170
        self.assertEqual(result["reference"], 165)
        self.assertEqual(result["trend"], 0)
        self.assertEqual(result["margin"], 5)
        self.assertEqual(result["category"], "реалистично")


if __name__ == "__main__":
    unittest.main()