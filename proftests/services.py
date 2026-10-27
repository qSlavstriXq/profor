from django.db import transaction
from django.utils import timezone

from .models import Answer, Attempt, Participant
from .scoring import calculate_scores, interpret, ranked

# Под этим ключом код участника хранится в сессии браузера
SESSION_KEY = "participant_code"


def current_participant(request):
    """Участник из сессии или None, если школьник ещё не проходил тесты."""
    code = request.session.get(SESSION_KEY)
    if not code:
        return None
    return Participant.objects.filter(code=code).first()


def get_or_create_participant(request):
    """Создаём участника только при первом прохождении теста,
    а не при каждом заходе на сайт, чтобы не копить пустые записи."""
    participant = current_participant(request)
    if participant is None:
        participant = Participant.objects.create()
        remember_participant(request, participant)
    return participant


def remember_participant(request, participant):
    request.session[SESSION_KEY] = participant.code


def forget_participant(request):
    request.session.pop(SESSION_KEY, None)


def find_participant(code):
    """Ищет участника по коду, который школьник ввёл вручную."""
    code = code.strip().upper()
    if not code.startswith("P-"):
        code = "P-" + code
    return Participant.objects.filter(code=code).first()


def collect_answers(test, post_data):
    """Достаёт ответы из отправленной формы.

    Возвращает (ответы, номера вопросов без ответа).
    Ответы: {вопрос: выбранный вариант}. Вариант принимаем, только если
    он относится к этому вопросу, иначе считаем, что ответа нет.
    """
    answers = {}
    missing = []
    for question in test.questions.prefetch_related("options"):
        raw = post_data.get(f"q{question.pk}", "")
        option = next((o for o in question.options.all() if str(o.pk) == raw), None)
        if option is None:
            missing.append(question.order)
        else:
            answers[question] = option
    return answers, missing


@transaction.atomic
def save_attempt(participant, test, answers):
    """Сохраняет прохождение с ответами и сразу считает баллы."""
    scores = calculate_scores(
        [scale.code for scale in test.scales.all()],
        [{"scale": option.scale.code, "points": option.points} for option in answers.values()],
    )
    attempt = Attempt.objects.create(
        participant=participant, test=test,
        finished_at=timezone.now(), scores=scores,
    )
    Answer.objects.bulk_create(
        Answer(attempt=attempt, question=question, option=option)
        for question, option in answers.items()
    )
    return attempt


def build_result(attempt):
    """Готовит результат для показа: шкалы от сильной к слабой с расшифровкой."""
    scales = {
        scale.code: scale
        for scale in attempt.test.scales.prefetch_related("interpretations")
    }
    rows = []
    for code, points in ranked(attempt.scores):
        scale = scales[code]
        levels = [
            {"min": i.min_points, "max": i.max_points, "level": i.level, "text": i.text}
            for i in scale.interpretations.all()
        ]
        rows.append({
            "code": code,
            "name": scale.name,
            "description": scale.description,
            "points": points,
            "max_points": max(item["max"] for item in levels),
            "interpretation": interpret(points, levels),
        })
    return rows
