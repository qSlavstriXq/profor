from collections import Counter

from django.shortcuts import redirect, render

from .models import Subject
from .services import CATEGORY_ORDER, DEFAULT_CATEGORIES, apply_filters, build_recommendations

# Под этим ключом баллы ЕГЭ хранятся в сессии браузера: их учитывает стратегия
SCORES_SESSION_KEY = "ege_scores"


def programs(request):
    if request.method == "POST":
        scores = {}
        for code, _label in Subject.choices:
            raw = request.POST.get(code, "").strip()
            if raw.isdigit() and 0 <= int(raw) <= 100:
                scores[code] = int(raw)
        request.session[SCORES_SESSION_KEY] = scores
        # Перенаправляем на обычную страницу: тогда обновление страницы
        # не будет предлагать «отправить форму ещё раз»
        return redirect("admissions:programs")

    # Если школьник уже вводил баллы, подставляем их в форму и сразу показываем подбор
    scores = request.session.get(SCORES_SESSION_KEY, {})
    fields = [
        {"code": code, "label": label, "value": scores.get(code, "")}
        for code, label in Subject.choices
    ]
    context = {"fields": fields, "results": None}
    if not scores:
        return render(request, "admissions/programs.html", context)

    # Фильтры приходят в адресе страницы (?university=hse&category=...),
    # поэтому ссылку с фильтрами можно сохранить или отправить
    university = request.GET.get("university", "")
    query = request.GET.get("q", "")
    if "filtered" in request.GET:
        categories = request.GET.getlist("category")  # пусто: все категории
    else:
        categories = DEFAULT_CATEGORIES

    all_results = build_recommendations(scores)
    # Счётчики по категориям: с учётом вуза и поиска, но без фильтра по категории
    counts = Counter(r["category"] for r in apply_filters(all_results, university, None, query))

    context.update({
        "results": apply_filters(all_results, university, categories, query),
        "total": len(all_results),
        "universities": sorted({(r["university_code"], r["university"]) for r in all_results},
                               key=lambda pair: pair[1]),
        "categories": [
            {"name": name, "count": counts[name], "checked": name in categories}
            for name in CATEGORY_ORDER
        ],
        "selected_university": university,
        "query": query,
    })
    return render(request, "admissions/programs.html", context)
