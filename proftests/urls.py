from django.urls import path

from . import views

app_name = "proftests"

urlpatterns = [
    path("", views.test_list, name="list"),
    path("my/", views.my_results, name="my_results"),
    path("my/forget/", views.forget_code, name="forget_code"),
    path("result/<int:attempt_id>/", views.result, name="result"),
    path("<slug:code>/", views.test_detail, name="detail"),
    path("<slug:code>/take/", views.test_take, name="take"),
]
