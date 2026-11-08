from django.contrib import admin

from .models import ApiCall, DataImport, EnrollmentPoint, Listing, RentPoint, Town


@admin.register(Town)
class TownAdmin(admin.ModelAdmin):
    list_display = ["name", "state", "university", "slug"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(RentPoint)
class RentPointAdmin(admin.ModelAdmin):
    list_display = ["town", "month", "bedrooms", "rent", "source"]
    list_filter = ["source", "town", "bedrooms"]


@admin.register(EnrollmentPoint)
class EnrollmentPointAdmin(admin.ModelAdmin):
    list_display = ["town", "year", "students", "source"]
    list_filter = ["source", "town"]


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ["address", "town", "bedrooms", "price", "days_on_market", "fetched_at"]
    list_filter = ["town", "bedrooms"]
    search_fields = ["address", "zip_code"]


@admin.register(ApiCall)
class ApiCallAdmin(admin.ModelAdmin):
    list_display = ["service", "called_at", "ok", "status_code", "error"]
    list_filter = ["service", "ok"]


@admin.register(DataImport)
class DataImportAdmin(admin.ModelAdmin):
    list_display = ["source", "finished_at", "rows", "detail"]
