import json
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase, override_settings

from proftests.loader import load_test
from proftests.models import Participant
from proftests.services import save_attempt
from proftests.tests import small_test_data

from .client import LLMError, LLMNotConfigured, ask_json
from .schemas import Strategy
from .strategy import build_input, check_against_data, generate_strategy


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
