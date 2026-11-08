from django.urls import path

from . import views

app_name = "towns"

urlpatterns = [
    path("", views.town_list, name="list"),
    path("<slug:slug>/", views.town_detail, name="detail"),
]
