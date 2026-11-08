import json
import re

from django import forms
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from towns import stats
from towns.models import Town

from .ai import MAX_PASTE, read_listing

HOURLY_LIMIT = 20

LINK_ONLY = re.compile(r"^\s*(https?://|www\.)\S+\s*$", re.I)

SAMPLE = """Spacious 2 bed / 1 bath apartment, 3 blocks from the Main Quad in Champaign! 850 sq ft,
furnished, $1,350/month. Water and trash included, tenant pays electric and internet.
Available Aug 2027. Call (217) 555-0142 to tour."""


class ListingForm(forms.Form):
    text = forms.CharField(
        label="Paste the listing text (text only, links won't work)",
        max_length=MAX_PASTE,
        help_text="Links are not valid. Open the listing, press Ctrl+A then Ctrl+C to copy the whole page, and paste it here.",
        widget=forms.Textarea(attrs={"rows": 8, "placeholder": "Example: 2 bed / 1 bath near campus, $1,350/month, water included..."}),
        error_messages={
            "required": "Paste the listing text first.",
            "max_length": "That's too long. Copy just the listing part of the page and try again.",
        },
    )
    town = forms.ModelChoiceField(
        queryset=Town.objects.all(), required=False, empty_label="Figure it out from the listing",
        label="Town (optional)",
    )

    def clean_text(self):
        text = self.cleaned_data["text"]
        if LINK_ONLY.match(text):
            raise forms.ValidationError(
                "Links are not valid. Text only: open the listing, press Ctrl+A then Ctrl+C, "
                "and paste the page text here."
            )
        return text


def over_limit(request):
    """Simple limit so one visitor can't burn through the AI calls."""
    ip = request.META.get("REMOTE_ADDR", "unknown")
    key = f"reader-uses-{ip}"
    uses = cache.get(key, 0)
    if uses >= HOURLY_LIMIT:
        return True
    cache.set(key, uses + 1, 60 * 60)
    return False


def compare_to_town(fields, town):
    """How the listed rent compares to the town's typical rent for that size."""
    rent, beds = fields.get("monthly_rent"), fields.get("bedrooms")
    if not town or not rent:
        return None
    whole_unit = rent * beds if fields.get("rent_is_per_bed") and beds else rent
    typical = stats.typical_rent(town, beds)
    if not typical:
        return None
    diff = round((whole_unit - typical) / typical * 100)
    return {
        "whole_unit": whole_unit,
        "typical": typical,
        "diff_pct": diff,
        "source": stats.SOURCE_LABELS.get(stats.best_source(town, beds), ""),
        "above": diff > 0,
        "abs_diff": abs(diff),
    }


def reader_page(request):
    result = comparison = None
    form = ListingForm(request.POST or None)
    if request.method == "GET" and request.GET.get("sample"):
        form = ListingForm(initial={"text": SAMPLE})

    if request.method == "POST" and form.is_valid():
        if over_limit(request):
            form.add_error(None, "You've used the reader a lot this hour. Try again later.")
        else:
            result = read_listing(form.cleaned_data["text"])
            if form.cleaned_data["town"]:
                result["town"] = form.cleaned_data["town"]
                result["warnings"] = [w for w in result["warnings"] if "which town" not in w]
            comparison = compare_to_town(result["fields"], result["town"])

    return render(request, "reader/reader.html", {"form": form, "result": result, "comparison": comparison})


@csrf_exempt
@require_POST
def reader_api(request):
    """POST {"text": "..."} and get the details back as JSON."""
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Send JSON like {\"text\": \"...\"}"}, status=400)
    text = body.get("text", "") if isinstance(body, dict) else ""
    form = ListingForm({"text": text})
    if not form.is_valid():
        return JsonResponse({"error": form.errors["text"][0]}, status=400)
    if over_limit(request):
        return JsonResponse({"error": "Too many requests. Try again in an hour."}, status=429)

    result = read_listing(form.cleaned_data["text"])
    town = result["town"]
    return JsonResponse({
        "fields": result["fields"],
        "town": town.slug if town else None,
        "method": result["method"],
        "seconds": result["seconds"],
        "extras": result["extras"],
        "warnings": result["warnings"],
        "comparison": compare_to_town(result["fields"], town),
    })
