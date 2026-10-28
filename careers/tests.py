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


class SiteTests(TestCase):
    """Подбор профессий по тесту и страницы профессий."""

    def setUp(self):
        from admissions.models import Program, University
        from proftests.models import Interpretation, Scale, Test

        self.test = Test.objects.create(code="klimov-ddo", title="ДДО", kind=Test.Kind.CAREER)
        for order, (code, name) in enumerate([("tech", "Человек — техника"), ("signs", "Человек — знак")]):
            scale = Scale.objects.create(test=self.test, code=code, name=name, order=order)
            Interpretation.objects.create(scale=scale, min_points=0, max_points=12, level="Средний", text="")
        hidden = Test.objects.create(code="holland", title="Голланд", is_active=False)
        Scale.objects.create(test=hidden, code="r", name="Реалистический тип")
        scales = {"klimov-ddo": {"tech", "signs"}, "holland": {"r"}}
        load_professions({"professions": [
            profession(code="both", title="Программист", test_scales={"klimov-ddo": ["signs", "tech"], "holland": ["r"]}),
            profession(code="tech", title="Автомеханик", test_scales={"klimov-ddo": ["tech"]}, directions=["23"]),
            profession(code="signs", title="Бухгалтер", test_scales={"klimov-ddo": ["signs"]}, directions=["38"],
                       verified=True),
        ]}, scales)
        university = University.objects.create(name="Тестовый университет", short_name="ТУ")
        Program.objects.create(university=university, name="Программная инженерия", direction_code="09.03.04")

    def make_attempt(self, scores):
        from django.utils import timezone

        from proftests.models import Attempt, Participant
        from proftests.services import SESSION_KEY

        participant = Participant.objects.create()
        session = self.client.session
        session[SESSION_KEY] = participant.code
        session.save()
        return Attempt.objects.create(participant=participant, test=self.test,
                                      finished_at=timezone.now(), scores=scores)

    def test_order_by_strongest_scales(self):
        from .services import professions_for_attempt

        attempt = self.make_attempt({"tech": 8, "signs": 5})
        found = [(item["profession"].code, item["fits"]) for item in professions_for_attempt(attempt)]
        self.assertEqual(found, [
            ("both", ["Человек — техника", "Человек — знак"]),  # подходит обеим шкалам
            ("tech", ["Человек — техника"]),                     # самой сильной
            ("signs", ["Человек — знак"]),
        ])

    def test_zero_scale_is_ignored(self):
        from .services import professions_for_attempt

        attempt = self.make_attempt({"tech": 8, "signs": 0})
        # Обе подходят одной шкале, поэтому по алфавиту: Автомеханик, Программист
        self.assertEqual([i["profession"].code for i in professions_for_attempt(attempt)], ["tech", "both"])

    def test_result_page_shows_professions(self):
        attempt = self.make_attempt({"tech": 8, "signs": 5})
        response = self.client.get(f"/tests/result/{attempt.pk}/")
        self.assertContains(response, "Какие профессии вам подходят")
        self.assertContains(response, "/professions/both/")

    def test_list_page(self):
        response = self.client.get("/professions/")
        self.assertContains(response, "3 профессии")
        self.assertContains(response, "Не проверено", count=2)

    def test_subject_filter_needs_all_subjects(self):
        # Математика есть у всех трёх, история — ни у кого
        self.assertContains(self.client.get("/professions/?subject=math"), "3 из 3")
        response = self.client.get("/professions/?subject=math&subject=history")
        self.assertContains(response, "0 из 3")
        self.assertContains(response, "Уберите один из предметов")

    def test_subject_filter_lists_only_used_subjects(self):
        response = self.client.get("/professions/?subject=astrology")
        self.assertContains(response, 'value="informatics"')
        self.assertNotContains(response, 'value="biology"')  # ни одной профессии с биологией
        self.assertNotContains(response, "из 3")  # неизвестный предмет не считается фильтром

    def test_detail_page(self):
        response = self.client.get("/professions/both/")
        self.assertContains(response, "Математика, Информатика")
        self.assertContains(response, "ТУ: Программная инженерия")
        self.assertContains(response, "Человек — знак")
        self.assertNotContains(response, "Реалистический тип")  # Голланд скрыт на сайте

    def test_unverified_hidden_by_setting(self):
        from django.test import override_settings

        with override_settings(SHOW_UNVERIFIED_DATA=False):
            self.assertEqual(self.client.get("/professions/both/").status_code, 404)
            self.assertContains(self.client.get("/professions/"), "Бухгалтер")
