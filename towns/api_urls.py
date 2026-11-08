from django.urls import path

from . import views

app_name = "api"

urlpatterns = [
    path("towns/", views.api_town_list, name="town-list"),
    path("towns/<slug:slug>/", views.api_town_detail, name="town-detail"),
]
