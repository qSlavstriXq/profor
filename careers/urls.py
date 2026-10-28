from django.urls import path

from . import views

app_name = "careers"

urlpatterns = [
    path("", views.profession_list, name="list"),
    path("<slug:code>/", views.profession_detail, name="detail"),
]
