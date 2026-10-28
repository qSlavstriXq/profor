import json
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from .loader import PROFESSIONS_FILE, ProfessionDataError, load_professions, validate_professions
from .models import Profession

SCALES = {"klimov-ddo": {"tech", "signs"}, "holland": {"r", "i"}}


def profession(**extra):
    item = {
        "code": "p1",
        "title": "Программист",
        "description": "Пишет программы.",
        "test_scales": {"klimov-ddo": ["signs"]},
        "subjects": ["math", "informatics"],
        "directions": ["09", "01.03.02"],
    }
    item.update(extra)
    return item


class ValidateTests(SimpleTestCase):
    def errors(self, *items):
        return validate_professions({"professions": list(items)}, SCALES)

    def test_good_profession(self):
        self.assertEqual(self.errors(profession()), [])

    def test_required_fields(self):
        [error] = self.errors(profession(description=""))
        self.assertIn("description", error)

    def test_duplicate_code(self):
        self.assertEqual(len(self.errors(profession(), profession())), 1)

    def test_unknown_test_and_scale(self):
        errors = self.errors(profession(test_scales={"nope": ["x"], "holland": ["s"]}))
        self.assertEqual(len(errors), 2)

    def test_unknown_subject(self):
        [error] = self.errors(profession(subjects=["math", "drawing"]))
        self.assertIn("drawing", error)

    def test_bad_direction(self):
        [error] = self.errors(profession(directions=["9.03"]))
        self.assertIn("9.03", error)

    def test_link_must_be_https(self):
        [error] = self.errors(profession(links=[{"title": "Сайт", "url": "http://example.ru"}]))
        self.assertIn("https", error)


class LoadTests(TestCase):
    def test_create_update_delete(self):
        load_professions({"professions": [profession(), profession(code="p2")]}, SCALES)
        load_professions({"professions": [profession(title="Разработчик")]}, SCALES)
        self.assertEqual(list(Profession.objects.values_list("code", "title")), [("p1", "Разработчик")])

    def test_errors_change_nothing(self):
        load_professions({"professions": [profession()]}, SCALES)
        with self.assertRaises(ProfessionDataError):
            load_professions({"professions": [profession(code="p2", subjects=["drawing"])]}, SCALES)
        self.assertEqual(Profession.objects.get().code, "p1")

    def test_fits_direction(self):
        load_professions({"professions": [profession()]}, SCALES)
        p = Profession.objects.get()
        self.assertTrue(p.fits_direction("09.03.04"))
        self.assertTrue(p.fits_direction("01.03.02"))
        self.assertFalse(p.fits_direction("01.03.01"))


class RealDataTests(TestCase):
    """Настоящий файл careers/data/professions.json без ошибок и загружается командой."""

    def test_file_is_valid(self):
        with open(PROFESSIONS_FILE, encoding="utf-8") as file:
            data = json.load(file)
        self.assertEqual(validate_professions(data), [])

    def test_command_loads_file(self):
        call_command("load_professions", stdout=StringIO())
        self.assertTrue(Profession.objects.exists())
