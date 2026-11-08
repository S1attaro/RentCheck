from django.contrib import admin

from .models import LeaseReport


@admin.register(LeaseReport)
class LeaseReportAdmin(admin.ModelAdmin):
    list_display = ["town", "bedrooms", "monthly_rent", "asking_rent", "per_person", "lease_start", "user"]
    list_filter = ["town", "bedrooms", "per_person"]
