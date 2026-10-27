from django.test import SimpleTestCase

from .templatetags.russian import plural


class PluralTests(SimpleTestCase):
    FORMS = "балл,балла,баллов"

    def test_forms(self):
        cases = {
            1: "1 балл", 2: "2 балла", 4: "4 балла", 5: "5 баллов", 11: "11 баллов",
            12: "12 баллов", 14: "14 баллов", 21: "21 балл", 22: "22 балла", 111: "111 баллов",
            0: "0 баллов",
        }
        for number, expected in cases.items():
            self.assertEqual(plural(number, self.FORMS), expected)

    def test_negative_and_float(self):
        # Знак не пишем: «не хватает 7 баллов» вместо «-7»
        self.assertEqual(plural(-7, self.FORMS), "7 баллов")
        self.assertEqual(plural(2.6, self.FORMS), "3 балла")
