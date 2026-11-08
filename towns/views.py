from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render

from leases.stats import reported_summary

from . import stats
from .models import BEDROOM_CHOICES, Town


def search_towns(query):
    towns = Town.objects.all()
    if query:
        towns = towns.filter(
            Q(name__icontains=query) | Q(university__icontains=query) | Q(state__iexact=query)
        )
    return towns


def parse_bedrooms(request):
    """Read ?bedrooms= from the URL. Returns None for all sizes."""
    value = request.GET.get("bedrooms", "")
    if value == "":
        return None
    try:
        bedrooms = int(value)
    except ValueError:
        raise Http404("bedrooms must be a number")
    if bedrooms not in dict(BEDROOM_CHOICES):
        raise Http404("bedrooms must be 0 to 5")
    return bedrooms


def town_list(request):
    query = request.GET.get("q", "").strip()
    towns = search_towns(query)
    rows = [stats.town_summary(t) for t in towns]
    return render(request, "towns/town_list.html", {"rows": rows, "query": query})


def town_detail(request, slug):
    town = get_object_or_404(Town, slug=slug)
    bedrooms = parse_bedrooms(request)
    context = {
        "town": town,
        "summary": stats.town_summary(town, bedrooms),
        "comparison": stats.source_comparison(town, bedrooms),
        "listings": stats.listing_summary(town, bedrooms),
        "reported": reported_summary(town, bedrooms),
        "bedroom_choices": BEDROOM_CHOICES,
        "bedrooms": bedrooms,
    }
    return render(request, "towns/town_detail.html", context)


# ---------- JSON API ----------

def api_town_list(request):
    query = request.GET.get("q", "").strip()
    towns = search_towns(query)
    return JsonResponse({"count": towns.count(), "results": [stats.town_summary(t) for t in towns]})


def api_town_detail(request, slug):
    try:
        town = Town.objects.get(slug=slug)
    except Town.DoesNotExist:
        return JsonResponse({"error": f"No town with slug '{slug}'"}, status=404)
    try:
        bedrooms = parse_bedrooms(request)
    except Http404 as e:
        return JsonResponse({"error": str(e)}, status=400)

    data = stats.town_summary(town, bedrooms)
    data["rent"] = stats.rent_series(town, bedrooms)
    data["rent_by_source"] = stats.rent_by_source(town, bedrooms)
    data["source_labels"] = {k: stats.SOURCE_LABELS[k] for k in data["rent_by_source"]}
    data["enrollment"] = stats.enrollment_series(town)
    data["reported_leases"] = reported_summary(town, bedrooms)
    listings = stats.listing_summary(town, bedrooms)
    data["listings"] = {"count": listings["count"], "median_price": listings["median_price"]}
    return JsonResponse(data)
