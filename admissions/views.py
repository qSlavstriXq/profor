from django.shortcuts import render

from .models import Subject
from .services import build_recommendations


def home(request):
    scores = {}
    results = None

    if request.method == "POST":
        for code, _label in Subject.choices:
            raw = request.POST.get(code, "").strip()
            if raw.isdigit() and 0 <= int(raw) <= 100:
                scores[code] = int(raw)
        results = build_recommendations(scores)

    fields = [
        {"code": code, "label": label, "value": scores.get(code, "")}
        for code, label in Subject.choices
    ]
    return render(request, "admissions/home.html", {"fields": fields, "results": results})