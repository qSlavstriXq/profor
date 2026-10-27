from django.conf import settings


def site(request):
    """Данные, нужные на каждой странице: название сайта для шапки и заголовков.

    Context processor добавляет их во все шаблоны сразу,
    чтобы не передавать в каждой view отдельно.
    """
    return {
        "SITE_NAME": settings.SITE_NAME,
        "SITE_TAGLINE": settings.SITE_TAGLINE,
    }
