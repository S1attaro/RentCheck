# Haan's part: Fair Rent Check + Compare Towns

The project is split so we never edit the same files.

| Who | Owns | Folders |
|---|---|---|
| Connor | Shared base, town page, data import, JSON API, login, past lease form | `rentcheck/`, `core/`, `towns/`, `leases/`, `templates/`, `static/` |
| Haan | Fair Rent Check page (with the AI feature), Compare Towns page | `checks/`, `compare/` |

Both your apps are already registered in settings, have URLs (`/check/` and `/compare/`), and show a "Coming soon" page. The nav bar already links to them. You only need to fill them in.

## Rules so we don't break each other

1. Only edit files inside `checks/` and `compare/`.
2. Work on your own branch, for example `haan/checks` and `haan/compare`. Merge to `main` through a pull request.
3. Read data through these helper functions. Don't write to Connor's tables.
4. If you need a new field on `Town`, `RentPoint`, or `LeaseReport`, text Connor first.
5. Your pages extend `base.html` like this:
   ```django
   {% extends "base.html" %}
   {% block title %}Fair Rent Check{% endblock %}
   {% block content %} ... {% endblock %}
   ```
   Form helper: `{% include "includes/form.html" %}` renders any Django form with errors.
   Charts: Chart.js is already in the repo. Add `{% load static %}<script src="{% static 'js/chart.umd.min.js' %}"></script>` in `{% block scripts %}`.

## What you can use from Connor's part

```python
from towns.models import Town, RentPoint, EnrollmentPoint, BEDROOM_CHOICES
from towns import stats
from leases.stats import reported_summary

stats.typical_rent(town, bedrooms=2)      # median rent, last 12 months, or None
stats.yearly_change(town, bedrooms=2)     # % change vs a year ago, or None
stats.rent_series(town, bedrooms=2)       # [{"month": "2025-08", "rent": 1250.0}, ...]
stats.enrollment_series(town)             # [{"year": 2025, "students": 56000}, ...]
stats.yearly_change_dollars(town, 2)      # $ change vs a year ago, or None
stats.town_summary(town, bedrooms=2)      # dict: name, slug, typical_rent, yearly_change_pct, students,
                                          #   source_label, is_demo, size_fallback ...
reported_summary(town, bedrooms=2)        # {"count", "enough", "median_unit_rent", "median_paid_vs_asking"}
```

`bedrooms=None` means all unit sizes. If a size has no data, the stats fall back to all sizes and `town_summary` sets `size_fallback=True`. Real data (Census, Zillow) is always used over demo data.

**Current listings** (from RentCast, once Connor runs `fetch_rentcast`) are the best source for "similar places":

```python
from towns.models import Listing
Listing.objects.filter(town=town, bedrooms=2)   # address, zip_code, property_type, bedrooms, bathrooms,
                                                # square_feet, price, days_on_market, latitude, longitude
stats.listing_summary(town, bedrooms=2)         # {"count", "median_price", "rows": cheapest 8}
stats.source_comparison(town, bedrooms=2)       # latest rent from each source, for showing a range
```

Lease reports have these fields you can use for "similar places" and the model: `bedrooms`, `unit_rent` (whole-unit rent, already converted from per-bed), `asking_rent`, `property_type`, `lease_months`, `furnished`, `square_feet`, `walk_minutes`, `utilities_included`, `lease_start`. Skip reports where `flagged=True` (likely typos).

JSON version of the same data: `/api/towns/` and `/api/towns/<slug>/?bedrooms=2`.

## Task 1: Fair Rent Check (`checks/`)

Matches wireframe page 3. Form on the left, result and similar places on the right.

Suggested model in `checks/models.py`:

```python
class RentCheck(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    town = models.ForeignKey("towns.Town", on_delete=models.CASCADE, related_name="rent_checks")
    bedrooms = models.PositiveSmallIntegerField(choices=BEDROOM_CHOICES)
    monthly_rent = models.PositiveIntegerField()
    per_person = models.BooleanField(default=False)
    utilities_included = models.BooleanField(default=False)
    expected_low = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    expected_high = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    rating = models.CharField(max_length=10)  # "low", "fair", "high", "unknown"
    created_at = models.DateTimeField(auto_now_add=True)
```

Steps:
- [ ] Form: town, bedrooms, monthly rent, per person checkbox, utilities. Validate rent is 100 to 10000.
- [ ] Version 1 rating (no AI yet): compare the price to `stats.typical_rent(town, bedrooms)`. Under 90% = low, over 110% = high, else fair. If typical rent is None, rating is "unknown" with a clear message.
- [ ] Save each check as a `RentCheck` row and show the result.
- [ ] "Similar places": current `Listing` rows in the same town and size (closest price or size first), plus lease reports.
- [ ] After the result, link to `/leases/new/?town=<slug>` ("Paid a lease here? Share it").
- [ ] Version 2 rating (the AI feature, see `docs/FIRST_DRAFT.md` section 3): replace the 90/110 rule with the trained price model's expected range.
- [ ] Tests in `checks/tests.py`: form validation, each rating, the unknown case.

## Task 2: Compare Towns (`compare/`)

Matches wireframe page 4. Up to 4 towns, a chart on top, a table below, CSV button.

Steps:
- [ ] Pick up to 4 towns with a GET form (checkboxes or 4 dropdowns). More than 4 shows an error.
- [ ] Table: one row per town with typical rent, yearly change, latest enrollment, students reported paid. Use `stats.town_summary` and `reported_summary`.
- [ ] Sortable table: clicking a column header sorts by it (`?sort=typical_rent`).
- [ ] Chart: rent over time for each picked town on one line chart (`stats.rent_series`).
- [ ] CSV download at `/compare/csv/?towns=a,b,c` using Python's `csv` module and `HttpResponse(content_type="text/csv")`.
- [ ] Tests in `compare/tests.py`: 0 towns, 5 towns (error), CSV has the right header and rows.

No model needed here unless you want saved comparisons.

## Setup

See `README.md`. Short version:

```bash
python -m venv .venv
.venv\Scripts\activate            # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python manage.py refresh_data     # real numbers, needs internet and keys in .env
python manage.py runserver
python manage.py test             # Connor's tests should pass before and after your changes
```
