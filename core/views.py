from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import redirect, render

from leases.models import LeaseReport
from towns import stats
from towns.models import DataImport, Town

from .forms import SignupForm


def home(request):
    rows = [stats.town_summary(t) for t in Town.objects.all()]
    context = {
        "rows": rows,
        "town_count": len(rows),
        "lease_count": LeaseReport.objects.count(),
        "last_import": DataImport.objects.exclude(source="demo").filter(rows__gt=0).first(),
    }
    return render(request, "core/home.html", context)


def signup(request):
    if request.user.is_authenticated:
        return redirect("leases:mine")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Account created. You can share a past lease now.")
        return redirect("leases:new")
    return render(request, "registration/signup.html", {"form": form})
