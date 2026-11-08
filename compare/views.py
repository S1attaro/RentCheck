# Owner: Haan. See HAAN_TASKS.md.
from django.shortcuts import render


def compare_index(request):
    return render(request, "compare/index.html")
