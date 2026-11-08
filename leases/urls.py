from django.urls import path

from . import views

app_name = "leases"

urlpatterns = [
    path("", views.MyReportsView.as_view(), name="mine"),
    path("new/", views.ReportCreateView.as_view(), name="new"),
    path("<int:pk>/edit/", views.ReportUpdateView.as_view(), name="edit"),
    path("<int:pk>/delete/", views.ReportDeleteView.as_view(), name="delete"),
]
