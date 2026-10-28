from django.shortcuts import get_object_or_404, render

from admissions.models import Subject

from . import services


def profession_list(request):
    professions = list(services.visible_professions())
    # Неизвестные коды из адреса (опечатка, старая ссылка) просто пропускаем
    selected = [code for code in request.GET.getlist("subject") if code in Subject.values]
    return render(request, "careers/list.html", {
        "professions": services.filter_by_subjects(professions, selected),
        "total": len(professions),
        "subjects": services.subject_choices(professions, selected),
        "filtered": bool(selected),
    })


def profession_detail(request, code):
    profession = get_object_or_404(services.visible_professions(), code=code)
    return render(request, "careers/detail.html", {
        "profession": profession,
        **services.profession_details(profession),
    })
