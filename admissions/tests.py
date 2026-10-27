import copy

from django.test import TestCase, override_settings

from .loader import UniversityDataError, load_university, validate_university_data
from .models import Program
from .services import apply_filters, build_recommendations

SAMPLE = {
    "code": "test-u",
    "name": "Тестовый университет",
    "short_name": "ТУ",
    "source_url": "https://example.ru/priem",
    "programs": [
        {
            "faculty": "Факультет компьютерных наук",
            "name": "Программная инженерия",
            "direction_code": "09.03.04",
            "exams": [
                {"subject": "math", "min_score": 60},
                {"subject": "russian", "min_score": 50},
                {"one_of": [
                    {"subject": "informatics", "min_score": 60},
                    {"subject": "physics", "min_score": 55},
                ]},
            ],
            "stats": [
                {"year": 2023, "passing_score_budget": 240, "budget_places": 100},
                {"year": 2024, "passing_score_budget": 250, "budget_places": 90},
            ],
        },
    ],
}


def sample(**changes):
    data = copy.deepcopy(SAMPLE)
    data.update(changes)
    return data


class ValidateTests(TestCase):
    def test_sample_is_valid(self):
        self.assertEqual(validate_university_data(SAMPLE), [])

    def test_unknown_subject(self):
        data = sample()
        data["programs"][0]["exams"][0]["subject"] = "astrology"
        self.assertIn("неизвестный предмет", validate_university_data(data)[0])

    def test_duplicate_year(self):
        data = sample()
        data["programs"][0]["stats"].append({"year": 2024, "passing_score_budget": 255})
        self.assertIn("указан дважды", validate_university_data(data)[0])

    def test_one_of_needs_two_subjects(self):
        data = sample()
        data["programs"][0]["exams"][2]["one_of"].pop()
        self.assertIn("минимум два", validate_university_data(data)[0])


class LoadTests(TestCase):
    def test_creates_university_and_program(self):
        university = load_university(sample())
        program = university.programs.get()
        self.assertEqual(program.exams.count(), 4)
        self.assertEqual(program.exams.filter(choice_group__isnull=False).count(), 2)
        self.assertEqual(program.stats.count(), 2)
        self.assertFalse(program.verified)  # по умолчанию данные не проверены
        self.assertEqual(program.source_url, "https://example.ru/priem")  # взят у вуза

    def test_reload_keeps_program_id(self):
        # id нужен сохранённым стратегиям, поэтому повторная загрузка его не меняет
        first = load_university(sample()).programs.get().pk
        data = sample()
        data["programs"][0]["stats"][1]["passing_score_budget"] = 260
        program = load_university(data).programs.get()
        self.assertEqual(program.pk, first)
        self.assertEqual(program.stats.get(year=2024).passing_score_budget, 260)

    def test_removed_program_is_deleted(self):
        load_university(sample())
        load_university(sample(programs=[]))
        self.assertFalse(Program.objects.exists())

    def test_invalid_file_changes_nothing(self):
        data = sample()
        data["programs"][0]["study_form"] = "night"
        with self.assertRaises(UniversityDataError):
            load_university(data)
        self.assertFalse(Program.objects.exists())


class RecommendationTests(TestCase):
    def setUp(self):
        load_university(sample())

    def test_choice_group_uses_better_subject(self):
        scores = {"math": 80, "russian": 80, "physics": 90}
        [result] = build_recommendations(scores)
        self.assertEqual(result["subjects"], ["Математика", "Русский язык", "Физика"])
        self.assertEqual(result["budget_places"], 90)
        self.assertFalse(result["verified"])

    @override_settings(SHOW_UNVERIFIED_DATA=False)
    def test_unverified_hidden_by_setting(self):
        self.assertEqual(build_recommendations({"math": 80, "russian": 80, "physics": 90}), [])


class FilterTests(TestCase):
    RESULTS = [
        {"university_code": "hse", "name": "Экономика", "faculty": "Факультет экономических наук",
         "category": "реалистично"},
        {"university_code": "hse", "name": "Программная инженерия", "faculty": "ФКН",
         "category": "амбициозно"},
        {"university_code": "mipt", "name": "Прикладная математика", "faculty": "",
         "category": "очень сложно"},
    ]

    def names(self, **filters):
        return [r["name"] for r in apply_filters(self.RESULTS, **filters)]

    def test_no_filters_keeps_all(self):
        self.assertEqual(len(self.names()), 3)

    def test_by_university(self):
        self.assertEqual(self.names(university="mipt"), ["Прикладная математика"])

    def test_by_categories(self):
        self.assertEqual(self.names(categories=["реалистично", "амбициозно"]),
                         ["Экономика", "Программная инженерия"])

    def test_query_searches_name_and_faculty_ignoring_case(self):
        self.assertEqual(self.names(query="ПРОГРАММ"), ["Программная инженерия"])
        self.assertEqual(self.names(query="экономических"), ["Экономика"])


class ProgramsPageTests(TestCase):
    URL = "/programs/"

    def setUp(self):
        load_university(sample())  # проходной 240-250: с суммой 240 «реалистично»
        hard = sample(code="hard-u", short_name="Сложный")
        for stat in hard["programs"][0]["stats"]:
            stat["passing_score_budget"] = 299  # «очень сложно»
        load_university(hard)

    def enter_scores(self):
        return self.client.post(self.URL, {"math": "80", "russian": "80", "physics": "80"})

    def test_post_redirects_and_remembers_scores(self):
        response = self.enter_scores()
        self.assertRedirects(response, self.URL)
        self.assertEqual(self.client.session["ege_scores"]["math"], 80)

    def test_without_scores_only_form(self):
        response = self.client.get(self.URL)
        self.assertIsNone(response.context["results"])

    def test_by_default_hides_very_hard(self):
        self.enter_scores()
        response = self.client.get(self.URL)
        self.assertEqual([r["university"] for r in response.context["results"]], ["ТУ"])
        self.assertEqual(response.context["total"], 2)

    def test_all_categories_when_none_checked(self):
        self.enter_scores()
        response = self.client.get(self.URL, {"filtered": "1"})
        self.assertEqual(len(response.context["results"]), 2)

    def test_university_filter(self):
        self.enter_scores()
        response = self.client.get(self.URL, {"filtered": "1", "university": "hard-u"})
        self.assertEqual([r["university"] for r in response.context["results"]], ["Сложный"])
        self.assertContains(response, "Очень сложно (1)")
