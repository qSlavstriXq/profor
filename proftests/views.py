from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from admissions.models import Course
from careers.models import Profession
from careers.services import professions_for_attempt
from admissions.views import SCORES_SESSION_KEY
from llm import client as llm_client
from llm import strategy as llm_strategy

from . import services
from .models import Test

# Сколько подходящих профессий показываем на странице результата
MAX_PROFESSIONS = 10


def test_list(request):
    tests = Test.objects.filter(is_active=True)
    return render(request, "proftests/test_list.html", {"tests": tests})


def test_detail(request, code):
    test = get_object_or_404(Test, code=code, is_active=True)
    return render(request, "proftests/test_detail.html", {"test": test})


def test_take(request, code):
    test = get_object_or_404(Test, code=code, is_active=True)
    questions = list(test.questions.prefetch_related("options"))
    missing = []

    if request.method == "POST":
        answers, missing = services.collect_answers(test, request.POST)
        if not missing:
            participant = services.get_or_create_participant(request)
            attempt = services.save_attempt(participant, test, answers)
            # Redirect после POST: если обновить страницу, ответы не отправятся второй раз
            return redirect("proftests:result", attempt_id=attempt.pk)
        # Если что-то пропущено, показываем форму снова, не теряя отмеченные ответы
        chosen = {question.pk: option.pk for question, option in answers.items()}
        for question in questions:
            question.selected = chosen.get(question.pk)

    return render(request, "proftests/test_take.html", {
        "test": test,
        "questions": questions,
        "missing": missing,
    })


def result(request, attempt_id):
    participant = services.current_participant(request)
    # Результат видит только его владелец. Чужой результат выглядит как
    # несуществующая страница, чтобы нельзя было перебирать номера.
    if participant is None:
        raise Http404
    attempt = get_object_or_404(
        participant.attempts.select_related("test"), pk=attempt_id,
    )
    professions = []
    if attempt.test.kind == Test.Kind.CAREER:
        professions = professions_for_attempt(attempt)
    return render(request, "proftests/result.html", {
        "attempt": attempt,
        "rows": services.build_result(attempt),
        "professions": professions[:MAX_PROFESSIONS],
        "more_professions": len(professions) > MAX_PROFESSIONS,
    })


def my_results(request):
    participant = services.current_participant(request)
    error = None

    if request.method == "POST":
        found = services.find_participant(request.POST.get("code", ""))
        if found is None:
            error = "Такого кода нет. Проверьте, что он введён без ошибок."
        else:
            services.remember_participant(request, found)
            return redirect("proftests:my_results")

    attempts = participant.attempts.select_related("test") if participant else []
    external = participant.external_results.all() if participant else []
    return render(request, "proftests/my_results.html", {
        "participant": participant,
        "attempts": attempts,
        "external": external,
        "error": error,
    })


@require_POST
def forget_code(request):
    """Убрать код из этого браузера, например на общем компьютере в школе."""
    services.forget_participant(request)
    return redirect("proftests:my_results")


def strategy(request):
    participant = services.current_participant(request)
    if participant is None:
        return redirect("proftests:my_results")

    scores = request.session.get(SCORES_SESSION_KEY, {})
    basis = llm_strategy.make_basis(participant, scores)
    has_tests = bool(basis["attempts"] or basis["external"])
    saved = llm_strategy.saved_strategy(participant, basis) if has_tests else None

    if request.method == "POST":
        # Модель зовём только по кнопке и только если готовой стратегии нет:
        # так обновление страницы не тратит токены
        if has_tests and saved is None:
            _strategy, source = llm_strategy.create_strategy(participant, scores)
            if source == "stub" and llm_client.is_configured():
                messages.warning(
                    request,
                    "Не удалось получить ответ ИИ-помощника. Показаны краткие итоги, попробуйте позже.",
                )
        return redirect("proftests:strategy")

    if saved is not None:
        current, source = saved, "llm"
    elif has_tests and not llm_client.is_configured():
        current, source = llm_strategy.generate_strategy(participant)  # бесплатная заглушка
    else:
        current, source = None, None  # покажем кнопку «Составить стратегию»

    return render(request, "proftests/strategy.html", {
        "has_tests": has_tests,
        "has_scores": bool(scores),
        "source": source,
        "strategy": _present(current, scores, participant) if current else None,
    })


def _present(strategy, scores, participant):
    """Подставляет названия тестов и программ вместо кодов и id."""
    tests = {test.code: test for test in Test.objects.all()}
    programs = {p["id"]: p for p in llm_strategy.pick_programs(scores, participant)}
    courses = Course.objects.in_bulk([s.course_id for s in strategy.next_steps if s.course_id])
    professions = Profession.objects.in_bulk(
        [code for d in strategy.directions for code in d.profession_codes], field_name="code",
    )

    return {
        "summary": strategy.summary,
        "test_analysis": [
            {"title": tests[item.test_code].title if item.test_code in tests else item.test_code,
             "summary": item.summary}
            for item in strategy.test_analysis
        ],
        "directions": [
            {
                "title": d.title,
                "why": d.why,
                # Профессию могли убрать из каталога после того, как стратегия сохранена
                "professions": [professions[code] for code in d.profession_codes if code in professions],
                # Программа могла пропасть из подбора (поменялись баллы), такие не показываем
                "programs": [programs[pid] for pid in d.program_ids if pid in programs],
            }
            for d in strategy.directions
        ],
        "next_steps": [
            {
                "kind": step.kind,
                "title": step.title,
                "why": step.why,
                "for_profession": step.for_profession,
                "test_code": step.test_code if step.test_code in tests else None,
                # Курс могли убрать из каталога после того, как стратегия сохранена
                "course": courses.get(step.course_id),
            }
            for step in strategy.next_steps
        ],
    }
