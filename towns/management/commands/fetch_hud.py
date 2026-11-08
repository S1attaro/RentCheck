"""Pull HUD Fair Market Rents by bedroom count.

    python manage.py fetch_hud                       # latest year
    python manage.py fetch_hud --years 2021-2027

For each town it finds the county by name, then asks HUD for that county's rents.
If HUD has ZIP-level numbers (Small Area FMRs) for the town's campus ZIPs, it uses
the average of those ZIPs instead, which is closer to student housing.
Sign up: https://www.huduser.gov/hudapi/public/register (pick the Fair Market Rent API)
"""

from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from towns.clients import ApiError, get_json
from towns.models import DataImport, RentPoint, Town

BASE_URL = "https://www.huduser.gov/hudapi/public/fmr"
BEDROOM_FIELDS = {"efficiency": 0, "one-bedroom": 1, "two-bedroom": 2, "three-bedroom": 3, "four-bedroom": 4}


def rents_from(row):
    """{'Efficiency': 900, 'One-Bedroom': 1000, ...} -> {0: 900.0, 1: 1000.0, ...} (any letter case)."""
    out = {}
    for key, value in (row or {}).items():
        beds = BEDROOM_FIELDS.get(str(key).lower())
        try:
            if beds is not None and value not in (None, ""):
                out[beds] = float(value)
        except (TypeError, ValueError):
            pass
    return out


def find_county(state_data, county_name):
    counties = (state_data.get("data") or {}).get("counties") or []
    target = county_name.lower()
    for c in counties:
        if str(c.get("county_name", "")).lower().startswith(target):
            return c
    return None


def town_rents(fmr_data, zips):
    """Pick the town's rents from an fmr/data response. Returns (rents, year, used_zips)."""
    data = fmr_data.get("data") or {}
    year = data.get("year")
    basic = data.get("basicdata")

    if isinstance(basic, list):  # Small Area FMRs: one row per ZIP
        rows = [r for r in basic if str(r.get("zip_code")) in zips]
        if rows:
            per_zip = [rents_from(r) for r in rows]
            averaged = {}
            for beds in BEDROOM_FIELDS.values():
                values = [z[beds] for z in per_zip if beds in z]
                if values:
                    averaged[beds] = round(sum(values) / len(values), 2)
            return averaged, year, True
        msa_rows = [r for r in basic if str(r.get("zip_code", "")).lower().startswith("msa")]
        return (rents_from(msa_rows[0]) if msa_rows else {}), year, False

    return rents_from(basic if isinstance(basic, dict) else data), year, False


def parse_years(value):
    if not value:
        return [None]
    if "-" in value:
        start, end = value.split("-")
        return list(range(int(start), int(end) + 1))
    return [int(value)]


class Command(BaseCommand):
    help = "Fetch HUD Fair Market Rents (by bedroom count) for each town's county."

    def add_arguments(self, parser):
        parser.add_argument("--years", default="", help="e.g. 2027 or 2021-2027. Default: latest")
        parser.add_argument("--towns", default="")

    def handle(self, years, towns, **options):
        if not settings.HUD_API_TOKEN:
            raise CommandError("Set HUD_API_TOKEN in .env (sign up at https://www.huduser.gov/hudapi/public/register)")
        headers = {"Authorization": f"Bearer {settings.HUD_API_TOKEN}"}

        town_qs = Town.objects.exclude(county="")
        if towns:
            town_qs = town_qs.filter(slug__in=[s.strip() for s in towns.split(",")])

        state_cache = {}
        saved = 0
        failures = []

        for town in town_qs:
            if town.state not in state_cache:
                try:
                    state_cache[town.state] = get_json("hud", f"{BASE_URL}/statedata/{town.state}", headers=headers)
                except ApiError as e:
                    failures.append(f"{town.state} county list: {e}")
                    state_cache[town.state] = {}
            county = find_county(state_cache[town.state], town.county)
            if county is None or not county.get("fips_code"):
                self.stdout.write(self.style.WARNING(f"{town}: no HUD county named '{town.county}'"))
                continue

            for year in parse_years(years):
                params = {"year": year} if year else {}
                try:
                    data = get_json("hud", f"{BASE_URL}/data/{county['fips_code']}", params=params, headers=headers)
                except ApiError as e:
                    failures.append(f"{town} {year or 'latest'}: {e}")
                    continue

                rents, fiscal_year, by_zip = town_rents(data, town.zip_list)
                fiscal_year = int(fiscal_year or year or date.today().year)
                month = date(fiscal_year - 1, 10, 1)  # HUD fiscal years start Oct 1
                for beds, rent in rents.items():
                    RentPoint.objects.update_or_create(
                        town=town, month=month, bedrooms=beds, source="hud", defaults={"rent": rent}
                    )
                    saved += 1
                where = "campus ZIPs" if by_zip else "county"
                self.stdout.write(f"{town} FY{fiscal_year}: {len(rents)} sizes ({where})")

        DataImport.objects.create(source="hud", rows=saved, detail=f"Fair Market Rents, {len(failures)} failed calls")
        for f in failures:
            self.stdout.write(self.style.WARNING(f"Failed: {f}"))
        self.stdout.write(self.style.SUCCESS(f"Saved {saved} HUD rent points."))
