"""Rent numbers for a town.

Other apps (checks, compare) should get their numbers from here
instead of querying RentPoint directly. That keeps the math in one place.

Which data gets used for the headline number:
- Real data always beats demo data. Demo is only used for towns with no real data.
- Order: Zillow (monthly, all sizes), RentCast (current listings), Census (what renters pay),
  HUD (a floor). The first one that has the size you asked for wins.
- If no source has that size, fall back to all sizes and say so.
source_comparison() shows every source side by side.
"""

from datetime import date
from statistics import median

from .models import SOURCE_CHOICES, SOURCE_NOTES, YEARLY_SOURCES, RentPoint

REAL_SOURCES = ["zillow", "rentcast", "census", "hud"]
ENROLLMENT_PRIORITY = ["ipeds", "census", "demo"]
SOURCE_LABELS = dict(SOURCE_CHOICES)


def _sources_present(town):
    """Sources this town has data for, best first. Demo only if there is no real data."""
    present = set(town.rent_points.values_list("source", flat=True).distinct())
    return [s for s in REAL_SOURCES if s in present] or (["demo"] if "demo" in present else [])


def _size_points(town, source, bedrooms=None):
    """(points, all_sizes) for one source. Falls back to all sizes if that unit size is missing."""
    points = town.rent_points.filter(source=source)
    if bedrooms is not None:
        exact = points.filter(bedrooms=bedrooms)
        if exact.exists():
            return exact, False
        return points.filter(bedrooms__isnull=True), True
    return points.filter(bedrooms__isnull=True), False


def _pick(town, bedrooms=None):
    """Return (source, bedrooms_used) for this town, or (None, None) if there is no data."""
    candidates = _sources_present(town)
    if bedrooms is not None:
        for source in candidates:
            if town.rent_points.filter(source=source, bedrooms=bedrooms).exists():
                return source, bedrooms
    for source in candidates:
        if town.rent_points.filter(source=source, bedrooms__isnull=True).exists():
            return source, None
    return None, None


def _points(town, bedrooms=None):
    source, used = _pick(town, bedrooms)
    if source is None:
        return RentPoint.objects.none()
    if used is None:
        return town.rent_points.filter(source=source, bedrooms__isnull=True)
    return town.rent_points.filter(source=source, bedrooms=used)


def as_of_label(month, source):
    """Readable date: "2024" for yearly sources, "Nov 2026" for monthly ones."""
    if source == "hud":
        return f"{month.year + 1} (Oct {month.year} to Sep {month.year + 1})"
    if source in YEARLY_SOURCES:
        return str(month.year)
    return month.strftime("%b %Y")


def _months_back(day, months):
    total = day.year * 12 + day.month - 1 - months
    return date(total // 12, total % 12 + 1, 1)


def best_source(town, bedrooms=None):
    return _pick(town, bedrooms)[0]


def rent_series(town, bedrooms=None):
    """List of {"month": "YYYY-MM", "rent": float}, oldest first."""
    return [
        {"month": p.month.strftime("%Y-%m"), "rent": float(p.rent)}
        for p in _points(town, bedrooms).order_by("month")
    ]


def typical_rent(town, bedrooms=None):
    """Median rent over the 12 months up to the latest data point, or None if there is no data.

    For yearly sources (Census) this is just the latest year's number.
    """
    points = _points(town, bedrooms)
    latest = points.order_by("-month").first()
    if latest is None:
        return None
    rents = points.filter(month__gt=_months_back(latest.month, 12)).values_list("rent", flat=True)
    return round(median(float(r) for r in rents), 2)


def _change_pair(town, bedrooms=None):
    """(latest, year_ago, source) from the first source that has both points for this size."""
    sources = [_pick(town, bedrooms)[0]] + _sources_present(town)
    for source in dict.fromkeys(s for s in sources if s):
        points, _ = _size_points(town, source, bedrooms)
        latest = points.order_by("-month").first()
        if latest is None:
            continue
        year_ago = points.filter(month=_months_back(latest.month, 12)).first()
        if year_ago is not None:
            return latest, year_ago, source
    return None, None, None


def _pct(latest, year_ago):
    return round((float(latest.rent) - float(year_ago.rent)) / float(year_ago.rent) * 100, 1)


def _dollars(latest, year_ago):
    return round(float(latest.rent) - float(year_ago.rent))


def yearly_change(town, bedrooms=None):
    """Percent change over the latest 12 months of data, or None."""
    latest, year_ago, _ = _change_pair(town, bedrooms)
    return _pct(latest, year_ago) if latest else None


def yearly_change_dollars(town, bedrooms=None):
    """Dollar change over the latest 12 months of data, or None."""
    latest, year_ago, _ = _change_pair(town, bedrooms)
    return _dollars(latest, year_ago) if latest else None


def rent_by_source(town, bedrooms=None):
    """{"census": [{"month", "rent"}...], "hud": [...]} for every source with data, for the chart."""
    out = {}
    for source in _sources_present(town):
        points, _ = _size_points(town, source, bedrooms)
        if points.exists():
            out[source] = [{"month": p.month.strftime("%Y-%m"), "rent": float(p.rent)} for p in points.order_by("month")]
    return out


def source_comparison(town, bedrooms=None):
    """Latest number from each source, so users can see how they line up."""
    rows = []
    for source in _sources_present(town):
        points, fallback = _size_points(town, source, bedrooms)
        latest = points.order_by("-month").first()
        if latest is None:
            continue
        rows.append({
            "source": source,
            "label": SOURCE_LABELS[source],
            "note": SOURCE_NOTES.get(source, ""),
            "rent": float(latest.rent),
            "as_of": as_of_label(latest.month, source),
            "all_sizes": fallback,
        })
    return rows


def enrollment_series(town):
    """All student counts. Demo numbers are left out once any real count exists."""
    points = town.enrollment_points.all()
    if points.exclude(source="demo").exists():
        points = points.exclude(source="demo")
    return [{"year": e.year, "students": e.students, "source": e.source} for e in points]


def latest_students(town):
    """Latest student count, preferring the school's own number."""
    for source in ENROLLMENT_PRIORITY:
        point = town.enrollment_points.filter(source=source).order_by("-year").first()
        if point:
            return point
    return None


def listing_summary(town, bedrooms=None, limit=8):
    """Current RentCast listings in town. Rows sorted by price."""
    listings = town.listings.all()
    if bedrooms is not None:
        listings = listings.filter(bedrooms=bedrooms)
    prices = list(listings.values_list("price", flat=True))
    return {
        "count": len(prices),
        "median_price": median(prices) if prices else None,
        "rows": list(listings.order_by("price")[:limit]),
    }


def town_summary(town, bedrooms=None):
    """Everything a page or API needs about one town in one dict."""
    source, used = _pick(town, bedrooms)
    latest = _points(town, bedrooms).order_by("-month").first()
    enrollment = latest_students(town)
    change_latest, change_year_ago, change_source = _change_pair(town, bedrooms)
    return {
        "name": town.name,
        "state": town.state,
        "slug": town.slug,
        "university": town.university,
        "url": town.get_absolute_url(),
        "bedrooms": bedrooms,
        "bedrooms_used": used,
        "size_fallback": bedrooms is not None and used is None and source is not None,
        "source": source,
        "source_label": SOURCE_LABELS.get(source, "No data"),
        "source_note": SOURCE_NOTES.get(source, ""),
        "is_demo": source == "demo",
        "latest_month": as_of_label(latest.month, source) if latest else None,
        "typical_rent": typical_rent(town, bedrooms),
        "yearly_change_pct": _pct(change_latest, change_year_ago) if change_latest else None,
        "yearly_change_dollars": _dollars(change_latest, change_year_ago) if change_latest else None,
        "change_source_label": SOURCE_LABELS.get(change_source, ""),
        "students": enrollment.students if enrollment else None,
        "students_year": enrollment.year if enrollment else None,
        "students_source": enrollment.source if enrollment else None,
        "school_size": town.school_size,
        "school_offcampus_cost": town.school_offcampus_cost,
        "school_offcampus_monthly": round(town.school_offcampus_cost / 9) if town.school_offcampus_cost else None,
    }
