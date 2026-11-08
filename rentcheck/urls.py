from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("django.contrib.auth.urls")),
    path("", include("core.urls")),
    path("towns/", include("towns.urls")),
    path("leases/", include("leases.urls")),
    path("api/", include("towns.api_urls")),
    path("read-listing/", include("reader.urls")),
    # Haan's apps
    path("check/", include("checks.urls")),
    path("compare/", include("compare.urls")),
]
