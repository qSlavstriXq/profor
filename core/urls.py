from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("tests/", include("proftests.urls")),
    path("programs/", include("admissions.urls")),
    path("", include("pages.urls")),
]

# Локально Django сам отдаёт загруженные файлы (фото, логотипы вузов).
# На настоящем сервере этим занимается веб-сервер, поэтому только при DEBUG.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
