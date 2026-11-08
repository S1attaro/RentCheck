# Owner: Haan. See HAAN_TASKS.md.
from django.shortcuts import render


def check_index(request):
    return render(request, "checks/index.html")
