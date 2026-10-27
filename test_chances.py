import unittest

from chances import classify, evaluate, reference_score


class TestChances(unittest.TestCase):
    def test_reference_score(self):
        self.assertEqual(reference_score([240, 250, 260]), 250)

    def test_classify_boundaries(self):
        self.assertEqual(classify(15), "страховка")
        self.assertEqual(classify(9), "реалистично")
        self.assertEqual(classify(-5), "реалистично")
        self.assertEqual(classify(-6), "амбициозно")
        self.assertEqual(classify(-20), "амбициозно")
        self.assertEqual(classify(-21), "очень сложно")

    def test_missing_subject_returns_none(self):
        program = {
            "university": "Тест",
            "name": "Тест",
            "subjects": ["math", "social"],
            "passing_scores": [200],
        }
        self.assertIsNone(evaluate({"math": 80}, program))

    def test_evaluate_gives_insurance(self):
        program = {
            "university": "Тест",
            "name": "Тест",
            "subjects": ["math", "russian"],
            "passing_scores": [170, 170, 170],
        }
        result = evaluate({"math": 90, "russian": 90}, program)
        self.assertEqual(result["category"], "страховка")


if __name__ == "__main__":
    unittest.main()