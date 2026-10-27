from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import services
from .models import Test


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
    return render(request, "proftests/result.html", {
        "attempt": attempt,
        "rows": services.build_result(attempt),
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
    return render(request, "proftests/my_results.html", {
        "participant": participant,
        "attempts": attempts,
        "error": error,
    })


@require_POST
def forget_code(request):
    """Убрать код из этого браузера, например на общем компьютере в школе."""
    services.forget_participant(request)
    return redirect("proftests:my_results")
