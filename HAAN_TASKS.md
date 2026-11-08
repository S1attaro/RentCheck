# Haan's part: Fair Rent Check + Compare Towns

## Deadlines

| When | What |
|---|---|
| **First draft, Nov 16** | Steps 1 to 3 below: get set up, then build and merge **version 1 of Fair Rent Check** (form + simple rating + saved to the database). |
| **Final, Dec 8** | The rest of Fair Rent Check (similar places + the AI price model), all of Compare Towns, and tests for both. |

The assignment says every team member has to apply the technical skills themselves, and the grader can see who made each commit. So your commits need to be in the repo for the first draft.

## Who owns what

We each edit different folders so we never overwrite each other.

| Who | Owns | Folders |
|---|---|---|
| Connor | Shared base, town pages, data, JSON API, login, past lease form, Listing Reader (AI) | `rentcheck/`, `core/`, `towns/`, `leases/`, `reader/`, `templates/`, `static/` |
| Haan | Fair Rent Check (with the AI price model), Compare Towns | `checks/`, `compare/` |

Your two apps are already set up. They're in settings, have URLs (`/check/` and `/compare/`), are in the nav bar, and show a "Coming soon" page. You just fill them in.

## Step 1: Get set up

1. Send Connor your GitHub username. Accept the collaborator invite from the email or github.com/notifications.
2. Clone the repo and install it. In PowerShell:
   ```
   git clone https://github.com/S1attaro/RentCheck.git
   cd RentCheck
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```
   (Mac: `source .venv/bin/activate` instead.) If `activate` says scripts are disabled, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.
3. Connor will email you `env.txt`. Save it in the `RentCheck` folder (next to `manage.py`) and rename it to `.env`. It has our API keys. **Never commit it.** It's in `.gitignore`, so a normal `git add .` skips it.
4. Set up the database and data:
   ```
   python manage.py migrate
   python manage.py seed_demo
   python manage.py refresh_data
   python manage.py runserver
   ```
   Open http://127.0.0.1:8000. Towns should show real numbers (no yellow "demo" warning).
5. Run the tests: `python manage.py test`. They should all pass before you change anything.

## Step 2: Work on your own branch

```
git checkout -b haan/checks
```

Commit as you go:
```
git add checks/
git commit -m "Short note about what you did"
git push -u origin haan/checks
```

When version 1 works, open a pull request: go to the repo on GitHub, click **Compare & pull request**, then **Create pull request**. Text Connor and one of you merges it.

Before starting new work, get the latest `main`:
```
git checkout main
git pull
git checkout -b haan/compare
```

Rules:
1. Only edit files inside `checks/` and `compare/`.
2. If you need something outside them (a new field on `Town`, a package in `requirements.txt`), text Connor first.
3. Read data with the helper functions below. Don't write to Connor's tables.
4. Run `python manage.py test` before every pull request.

## Step 3: Fair Rent Check, version 1 (due Nov 16)

Matches wireframe page 3: form on the left, result on the right.

**Files to create or fill in, all inside `checks/`:**

| File | What goes in it |
|---|---|
| `models.py` | A `RentCheck` model (see below). Then run `python manage.py makemigrations checks` and `python manage.py migrate`. Commit the new file in `checks/migrations/`. |
| `forms.py` (new) | A `ModelForm` for `RentCheck` with town, bedrooms, monthly_rent, per_person, utilities_included. Reject rent under 100 or over 10,000 with a clear message. |
| `views.py` | One view: on GET show the empty form. On POST, if valid, work out the rating (below), save the `RentCheck`, and show the result. |
| `templates/checks/index.html` | Two columns like the wireframe. Use `{% include "includes/form.html" %}` to draw the form with its errors. |
| `admin.py` | Register `RentCheck` so you can see saved checks at /admin. |
| `tests.py` (new) | Tests for: rent too low or too high, each rating (low, fair, high), and the "unknown" case. |

**Model to start from:**
```python
from django.conf import settings
from django.db import models

from towns.models import BEDROOM_CHOICES


class RentCheck(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    town = models.ForeignKey("towns.Town", on_delete=models.CASCADE, related_name="rent_checks")
    bedrooms = models.PositiveSmallIntegerField(choices=BEDROOM_CHOICES)
    monthly_rent = models.PositiveIntegerField()
    per_person = models.BooleanField(default=False)
    utilities_included = models.BooleanField(default=False)
    typical_rent = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    expected_low = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    expected_high = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    rating = models.CharField(max_length=10)  # "low", "fair", "high", or "unknown"
    created_at = models.DateTimeField(auto_now_add=True)
```

**Version 1 rating (no AI yet):**
1. If `per_person` is checked, multiply the rent by the bedrooms to get the whole-unit rent.
2. Get `stats.typical_rent(town, bedrooms)`.
3. If that's `None`, the rating is "unknown". Show "Not enough data for this town and size yet."
4. Otherwise: under 90% of typical is "low", over 110% is "high", anything else is "fair".
5. Show the rating, the typical rent, and the percent difference, like "8% above typical ($1,320 vs $1,220)".
6. Under the result, add a link: "Paid a lease here? Share it" pointing to `/leases/new/?town=<town slug>`.

To try it, look up a town's typical rent on its town page, then enter a rent above, near, and below it.

## Step 4: Finish Fair Rent Check (due Dec 8)

- [ ] **Similar places:** show up to 5 current `Listing` rows in the same town and size, closest price first. These fill in after Connor runs `fetch_rentcast`. If there are none, show the lease report totals instead.
- [ ] **Paste a listing (optional):** add a text box that calls Connor's `read_listing()` and fills in the form for the user.
- [ ] **AI price model** (the main AI feature, see `docs/FIRST_DRAFT.md` section 3a):
  1. Text Connor to add `scikit-learn` and `joblib` to `requirements.txt`.
  2. Make a command, `checks/management/commands/train_rent_model.py`, that builds a training table from `Listing` rows (bedrooms, bathrooms, square_feet, zip_code, price) plus lease reports (`unit_rent`), and trains two `HistGradientBoostingRegressor(loss="quantile")` models (quantile 0.25 and 0.75) for the low and high ends.
  3. Save them with `joblib` to `checks/rent_model.joblib`. Model files are in `.gitignore`, so anyone can rebuild it with the command.
  4. In the view, use the model's low and high instead of the 90%/110% rule. If the model file is missing or errors, fall back to the version 1 rule and say so on the page.
  5. Keep a few listings out of training and check how often their real price lands inside the range. That number goes in our evaluation table.
- [ ] **Tests:** the fallback when there's no model file, and that low is always below high.

## Step 5: Compare Towns (due Dec 8)

Matches wireframe page 4: up to 4 towns, a chart on top, a table below, a CSV button. Work on a new branch: `haan/compare`.

- [ ] A GET form to pick up to 4 towns (checkboxes or 4 dropdowns). Picking more than 4 shows an error.
- [ ] A table with one row per town: typical rent, yearly change, students, and what students reported paying. Use `stats.town_summary` and `reported_summary`.
- [ ] Sorting: clicking a column header sorts by it (`?towns=a,b&sort=typical_rent`).
- [ ] A line chart of rent over time for each town (`stats.rent_series`). See `towns/templates/towns/town_detail.html` for a working Chart.js example.
- [ ] CSV download at `/compare/csv/?towns=a,b,c` using Python's `csv` module and `HttpResponse(content_type="text/csv")`.
- [ ] Tests: no towns picked, 5 towns (error), and the CSV has the right header and rows.

No model is needed here.

## What you can use from Connor's part

```python
from towns.models import Town, Listing, BEDROOM_CHOICES
from towns import stats
from leases.stats import reported_summary
from reader.ai import read_listing

stats.typical_rent(town, bedrooms=2)        # typical monthly rent, or None
stats.yearly_change(town, bedrooms=2)       # % change vs a year earlier, or None
stats.yearly_change_dollars(town, 2)        # $ change vs a year earlier, or None
stats.rent_series(town, bedrooms=2)         # [{"month": "2025-08", "rent": 1250.0}, ...]
stats.enrollment_series(town)               # [{"year": 2024, "students": 35000, "source": "ipeds"}, ...]
stats.town_summary(town, bedrooms=2)        # dict with name, slug, typical_rent, yearly_change_pct,
                                            #   students, source_label, is_demo, size_fallback
stats.source_comparison(town, bedrooms=2)   # latest rent from each data source
stats.listing_summary(town, bedrooms=2)     # {"count", "median_price", "rows": cheapest 8 listings}
reported_summary(town, bedrooms=2)          # {"count", "enough", "median_unit_rent", ...}

Listing.objects.filter(town=town, bedrooms=2)   # address, zip_code, property_type, bedrooms,
                                                # bathrooms, square_feet, price, days_on_market

result = read_listing(pasted_text)          # result["fields"] has monthly_rent, bedrooms, ...
                                            # result["town"] is a Town or None
```

- `bedrooms=None` means all sizes. If a size has no data, the stats use all sizes and `town_summary` sets `size_fallback=True`.
- Lease reports (`town.lease_reports`) have `bedrooms`, `unit_rent` (whole-unit rent, already converted from per bed), `property_type`, `lease_months`, `furnished`, `square_feet`, and `walk_minutes`. Skip any with `flagged=True`, since those are likely typos.
- JSON versions: `/api/towns/` and `/api/towns/<slug>/?bedrooms=2`.

## Page layout

Your pages extend the shared layout:
```django
{% extends "base.html" %}
{% block title %}Fair Rent Check{% endblock %}
{% block content %} ... {% endblock %}
```
- Forms: `{% include "includes/form.html" %}` draws any Django form with its error messages.
- Cards and tables: use the CSS classes `card`, `table`, `stats`, and `stat` so your pages match the rest of the site.
- Charts: put `{% load static %}<script src="{% static 'js/chart.umd.min.js' %}"></script>` in `{% block scripts %}`.

Questions or something broken? Text Connor.
