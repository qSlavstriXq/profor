from django.shortcuts import render

from .models import Subject
from .services import build_recommendations

# Под этим ключом баллы ЕГЭ хранятся в сессии браузера: их учитывает стратегия
SCORES_SESSION_KEY = "ege_scores"


def programs(request):
    # Если школьник уже вводил баллы, подставляем их в форму
    scores = request.session.get(SCORES_SESSION_KEY, {})
    results = None

    if request.method == "POST":
        scores = {}
        for code, _label in Subject.choices:
            raw = request.POST.get(code, "").strip()
            if raw.isdigit() and 0 <= int(raw) <= 100:
                scores[code] = int(raw)
        request.session[SCORES_SESSION_KEY] = scores
        results = build_recommendations(scores)

    fields = [
        {"code": code, "label": label, "value": scores.get(code, "")}
        for code, label in Subject.choices
    ]
    return render(request, "admissions/programs.html", {"fields": fields, "results": results})
