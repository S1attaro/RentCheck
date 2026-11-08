from django.urls import path

from . import views

app_name = "checks"

urlpatterns = [
    path("", views.check_index, name="index"),
]
