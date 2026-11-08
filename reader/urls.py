from django.urls import path

from . import views

app_name = "reader"

urlpatterns = [
    path("", views.reader_page, name="page"),
    path("api/", views.reader_api, name="api"),
]
