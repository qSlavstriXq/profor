import json
import logging
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from admissions.models import AdmissionStat, Program, ProgramExam, University
from proftests.loader import DATA_DIR, load_test, read_test_file
from proftests.models import Participant, Question, StrategyReport
from proftests.services import SESSION_KEY
from proftests.services import save_attempt
from proftests.tests import small_test_data

from .client import LLMError, LLMNotConfigured, ask_json
from .schemas import Strategy
from .strategy import build_input, check_against_data, generate_strategy, pick_programs


def setUpModule():
    # Тесты нарочно подсовывают плохие ответы, и журнал засоряет вывод. Глушим его
    logging.disable(logging.CRITICAL)


def tearDownModule():
    logging.disable(logging.NOTSET)


class FakeClient:
    """Притворяется клиентом модели: по очереди отдаёт заготовленные ответы."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.answers.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50),
        )


def strategy_json(**changes):
    data = {
        "summary": "Итог",
        "test_analysis": [{"test_code": "mini", "summary": "Разбор"}],
        "directions": [{"title": "Направление", "why": "Потому что", "program_ids": [1, 999]}],
        "next_steps": [{"kind": "test", "title": "Ещё тест", "why": "Узнать больше",
                        "test_code": "no-such-test"}],
    }
    data.update(changes)
    return json.dumps(data, ensure_ascii=False)


class TestAskJson(SimpleTestCase):
    def test_valid_answer(self):
        result = ask_json("инструкция", {"a": 1}, Strategy, client=FakeClient(strategy_json()))
        self.assertEqual(result.summary, "Итог")

    def test_data_sent_as_compact_json(self):
        fake = FakeClient(strategy_json())
        ask_json("инструкция", {"имя": "шкала"}, Strategy, client=fake)
        self.assertEqual(fake.calls[0]["messages"][1]["content"], '{"имя":"шкала"}')

    def test_retry_after_bad_answer(self):
        fake = FakeClient("это не JSON", strategy_json())
        result = ask_json("инструкция", {}, Strategy, client=fake)
        self.assertEqual(result.summary, "Итог")
        self.assertEqual(len(fake.calls), 2)

    def test_two_bad_answers_raise(self):
        with self.assertRaises(LLMError):
            ask_json("инструкция", {}, Strategy, client=FakeClient("{}", "{}"))

    @override_settings(QWEN_API_KEY="")
    def test_no_key(self):
        with self.assertRaises(LLMNotConfigured):
            ask_json("инструкция", {}, Strategy)


class TestStrategy(TestCase):
    def setUp(self):
        test = load_test(small_test_data())
        self.participant = Participant.objects.create()
        question1, question2 = test.questions.prefetch_related("options")
        save_attempt(self.participant, test, {
            question1: question1.options.all()[0],
            question2: question2.options.all()[0],
        })

    def test_input_has_results_but_no_participant_code(self):
        data = build_input(self.participant)
        self.assertEqual(data["tests"][0]["scales"][0]["points"], 2)
        self.assertNotIn(self.participant.code, json.dumps(data, ensure_ascii=False))

    def test_unknown_ids_are_removed(self):
        data = build_input(self.participant, programs=[
            {"id": 1, "university": "Вуз", "name": "Программа", "category": "реалистично"},
        ])
        strategy = check_against_data(Strategy.model_validate_json(strategy_json()), data)
        self.assertEqual(strategy.directions[0].program_ids, [1])
        self.assertIsNone(strategy.next_steps[0].test_code)

    def test_courses_from_catalog_by_direction(self):
        from admissions.models import Course
        it = Course.objects.create(code="it", title="Курс ИТ", provider="Вуз",
                                   url="https://example.ru/it", directions=["09"])
        Course.objects.create(code="med", title="Курс медицины", provider="Вуз",
                              url="https://example.ru/med", directions=["31.05.01"])
        data = build_input(self.participant, programs=[
            {"id": 1, "university": "Вуз", "name": "ПИ", "category": "реалистично",
             "direction_code": "09.03.04"},
        ])
        self.assertEqual([c["id"] for c in data["courses"]], [it.pk])
        # Курс не из переданного списка модель указать не может
        step = {"kind": "course", "title": "Курс", "why": "Нужен", "course_id": 999}
        strategy = check_against_data(Strategy.model_validate_json(strategy_json(next_steps=[step])), data)
        self.assertIsNone(strategy.next_steps[0].course_id)

    @override_settings(QWEN_API_KEY="")
    def test_without_key_returns_stub(self):
        strategy, source = generate_strategy(self.participant)
        self.assertEqual(source, "stub")
        self.assertEqual(strategy.directions[0].title, "Шкала А")

    def test_with_model(self):
        strategy, source = generate_strategy(self.participant, llm_client=FakeClient(strategy_json()))
        self.assertEqual(source, "llm")
        self.assertEqual(strategy.summary, "Итог")

    def test_model_failure_falls_back_to_stub(self):
        strategy, source = generate_strategy(self.participant, llm_client=FakeClient("{}", "{}"))
        self.assertEqual(source, "stub")


class TestStrategyPage(TestCase):
    URL = "/tests/my/strategy/"

    def setUp(self):
        load_test(small_test_data())

    def pass_test(self):
        """Проходит мини-тест через сайт: в сессии появляется код участника."""
        data = {
            f"q{q.pk}": q.options.first().pk
            for q in Question.objects.filter(test__code="mini")
        }
        self.client.post("/tests/mini/take/", data)

    def use_fake_model(self, *answers):
        """Подменяет настоящего клиента модели фальшивым на время теста."""
        fake = FakeClient(*answers)
        patcher = mock.patch("llm.client._make_client", return_value=fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        return fake

    def test_without_participant_redirects(self):
        self.assertRedirects(self.client.get(self.URL), "/tests/my/")

    def test_without_tests_asks_to_pass_one(self):
        session = self.client.session
        session[SESSION_KEY] = Participant.objects.create().code
        session.save()
        self.assertContains(self.client.get(self.URL), "Сначала пройдите хотя бы один тест")

    @override_settings(QWEN_API_KEY="")
    def test_without_key_shows_stub(self):
        self.pass_test()
        response = self.client.get(self.URL)
        self.assertContains(response, "краткие итоги без ИИ-помощника")
        self.assertContains(response, "Шкала А")
        self.assertFalse(StrategyReport.objects.exists())

    @override_settings(QWEN_API_KEY="test-key")
    def test_get_does_not_call_model(self):
        fake = self.use_fake_model()
        self.pass_test()
        self.assertContains(self.client.get(self.URL), "Составить стратегию")
        self.assertEqual(fake.calls, [])

    @override_settings(QWEN_API_KEY="test-key")
    def test_button_calls_model_once_and_saves(self):
        fake = self.use_fake_model(strategy_json())
        self.pass_test()

        self.assertRedirects(self.client.post(self.URL), self.URL)
        self.assertContains(self.client.get(self.URL), "Итог")
        self.client.post(self.URL)  # повторное нажатие не тратит токены
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(StrategyReport.objects.count(), 1)

    @override_settings(QWEN_API_KEY="test-key")
    def test_new_test_result_makes_strategy_outdated(self):
        self.use_fake_model(strategy_json())
        self.pass_test()
        self.client.post(self.URL)
        self.pass_test()  # прошёл тест ещё раз
        self.assertContains(self.client.get(self.URL), "Составить стратегию")

    @override_settings(QWEN_API_KEY="test-key")
    def test_model_failure_shows_warning(self):
        self.use_fake_model("{}", "{}")
        self.pass_test()
        response = self.client.post(self.URL, follow=True)
        self.assertContains(response, "Не удалось получить ответ ИИ-помощника")
        self.assertFalse(StrategyReport.objects.exists())

    @override_settings(QWEN_API_KEY="test-key")
    def test_programs_from_ege_scores(self):
        university = University.objects.create(name="Тестовый вуз", verified=True)
        program = Program.objects.create(university=university, name="Информатика", verified=True)
        ProgramExam.objects.create(program=program, subject="math")
        ProgramExam.objects.create(program=program, subject="russian")
        AdmissionStat.objects.create(program=program, year=2025, passing_score_budget=150)

        self.client.post("/programs/", {"math": "80", "russian": "80"})  # баллы запомнятся
        fake = self.use_fake_model(strategy_json(directions=[
            {"title": "ИТ", "why": "Потому что", "program_ids": [program.pk]},
        ]))
        self.pass_test()
        self.client.post(self.URL)

        sent = json.loads(fake.calls[0]["messages"][1]["content"])
        self.assertEqual(sent["programs"][0]["id"], program.pk)
        self.assertContains(self.client.get(self.URL), "Тестовый вуз, Информатика")


class TestPickProgramsByTest(TestCase):
    """Программы, подходящие по профтесту, идут первыми."""

    def make_program(self, name, code, passing):
        university = University.objects.get_or_create(name="Вуз", verified=True)[0]
        program = Program.objects.create(
            university=university, name=name, direction_code=code, verified=True,
        )
        ProgramExam.objects.create(program=program, subject="math")
        ProgramExam.objects.create(program=program, subject="russian")
        AdmissionStat.objects.create(program=program, year=2025, passing_score_budget=passing)
        return program

    def setUp(self):
        # Школьник везде выбирает «знаковую систему», если она есть в вопросе
        test = load_test(read_test_file(DATA_DIR / "klimov_ddo.json"))
        self.participant = Participant.objects.create()
        answers = {}
        for question in test.questions.prefetch_related("options__scale"):
            options = list(question.options.all())
            answers[question] = next((o for o in options if o.scale.code == "signs"), options[0])
        save_attempt(self.participant, test, answers)

        # Медицина по шансам выше (страховка), информатика ниже (реалистично)
        self.medicine = self.make_program("Лечебное дело", "31.05.01", 140)
        self.it = self.make_program("Программная инженерия", "09.03.04", 160)

    def test_without_participant_order_by_chances(self):
        programs = pick_programs({"math": 80, "russian": 80})
        self.assertEqual(programs[0]["id"], self.it.pk)  # реалистично раньше страховки
        self.assertNotIn("fits", programs[0])

    def test_matching_program_goes_first(self):
        programs = pick_programs({"math": 80, "russian": 80}, self.participant)
        self.assertEqual(programs[0]["id"], self.it.pk)
        self.assertIn("Человек — знаковая система", programs[0]["fits"])

    def test_fits_sent_to_model(self):
        programs = pick_programs({"math": 80, "russian": 80}, self.participant)
        data = build_input(self.participant, programs)
        self.assertIn("fits", data["programs"][0])
