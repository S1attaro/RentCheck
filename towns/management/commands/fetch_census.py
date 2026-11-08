"""Pull real rent and student numbers from the Census Bureau API.

    python manage.py fetch_census                  # 2015-2024, all towns
    python manage.py fetch_census --start 2020 --towns madison,ann-arbor

Uses the American Community Survey 5-year estimates for each town's Census places:
  B25031  Median gross rent by bedrooms (studio through 5+)
  B25003  Renter-occupied units (used to weight towns made of 2+ cities)
  B14001  Undergrad + grad students living in the town

No key needed for light use. Set CENSUS_API_KEY in .env if you hit the limit
(free key: https://api.census.gov/data/key_signup.html).
"""

from collections import defaultdict
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from towns.clients import ApiError, get_json
from towns.models import DataImport, EnrollmentPoint, RentPoint, Town

API_URL = "https://api.census.gov/data/{year}/acs/acs5"

# Census variable -> bedrooms (None = all sizes)
RENT_VARS = {
    "B25031_001E": None,
    "B25031_002E": 0,
    "B25031_003E": 1,
    "B25031_004E": 2,
    "B25031_005E": 3,
    "B25031_006E": 4,
    "B25031_007E": 5,
}
RENTERS_VAR = "B25003_003E"
STUDENT_VARS = ["B14001_008E", "B14001_009E"]  # undergrad, grad/professional
ALL_VARS = ["NAME", *RENT_VARS, RENTERS_VAR, *STUDENT_VARS]

STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08", "CT": "09", "DE": "10",
    "DC": "11", "FL": "12", "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18", "IA": "19",
    "KS": "20", "KY": "21", "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33", "NJ": "34", "NM": "35",
    "NY": "36", "NC": "37", "ND": "38", "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
    "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56",
}


def to_number(value):
    """Census uses negative codes like -666666666 for 'no estimate'."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def parse_rows(data):
    """The API returns a header row then data rows. Turn them into dicts keyed by place name."""
    if not data or len(data) < 2:
        return {}
    header, *rows = data
    places = {}
    for row in rows:
        record = dict(zip(header, row))
        place_name = record["NAME"].split(",")[0].strip()  # "Champaign city, Illinois" -> "Champaign city"
        places[place_name] = record
    return places


def combine_places(records):
    """Merge one or more Census places into one town.

    Rents: average weighted by number of renter households.
    Students: added together.
    """
    rents = {}
    for var, bedrooms in RENT_VARS.items():
        total, weight = 0.0, 0.0
        for r in records:
            rent, renters = to_number(r.get(var)), to_number(r.get(RENTERS_VAR)) or 1
            if rent is not None:
                total += rent * renters
                weight += renters
        if weight:
            rents[bedrooms] = round(total / weight, 2)

    student_counts = [to_number(r.get(v)) for r in records for v in STUDENT_VARS]
    students = int(sum(s for s in student_counts if s is not None)) if any(s is not None for s in student_counts) else None
    return rents, students


class Command(BaseCommand):
    help = "Fetch rent by bedrooms and student population from the Census ACS API."

    def add_arguments(self, parser):
        parser.add_argument("--start", type=int, default=2015)
        parser.add_argument("--end", type=int, default=2024, help="Latest ACS 5-year release to request")
        parser.add_argument("--towns", default="", help="Comma separated slugs. Default: all towns")

    def handle(self, start, end, towns, **options):
        town_qs = Town.objects.exclude(census_places="")
        if towns:
            town_qs = town_qs.filter(slug__in=[s.strip() for s in towns.split(",")])
        if not town_qs.exists():
            raise CommandError("No towns to fetch. Run `python manage.py load_towns` first.")

        towns_by_state = defaultdict(list)
        for town in town_qs:
            if town.state not in STATE_FIPS:
                self.stdout.write(self.style.WARNING(f"Unknown state {town.state} for {town}, skipped"))
                continue
            towns_by_state[town.state].append(town)

        api_key = settings.CENSUS_API_KEY
        rent_rows = enrollment_rows = 0
        failures = []

        for year in range(start, end + 1):
            for state, state_towns in towns_by_state.items():
                params = {"get": ",".join(ALL_VARS), "for": "place:*", "in": f"state:{STATE_FIPS[state]}"}
                if api_key:
                    params["key"] = api_key

                try:
                    places = parse_rows(get_json("census", API_URL.format(year=year), params=params))
                except ApiError as e:
                    failures.append(f"{year} {state}: {e}")
                    continue

                for town in state_towns:
                    names = [n.strip() for n in town.census_places.split(",") if n.strip()]
                    records = [places[n] for n in names if n in places]
                    missing = [n for n in names if n not in places]
                    if missing:
                        self.stdout.write(self.style.WARNING(f"{year} {town}: no Census place named {missing}"))
                    if not records:
                        continue

                    rents, students = combine_places(records)
                    month = date(year, 7, 1)  # 5-year estimates have no month; use mid-year
                    for bedrooms, rent in rents.items():
                        RentPoint.objects.update_or_create(
                            town=town, month=month, bedrooms=bedrooms, source="census", defaults={"rent": rent}
                        )
                        rent_rows += 1

                    if students is not None:
                        EnrollmentPoint.objects.update_or_create(
                            town=town, year=year, source="census", defaults={"students": students}
                        )
                        enrollment_rows += 1

            self.stdout.write(f"{year}: done")

        DataImport.objects.create(
            source="census",
            rows=rent_rows + enrollment_rows,
            detail=f"ACS 5-year {start}-{end}, {town_qs.count()} towns, {len(failures)} failed requests",
        )
        for f in failures:
            self.stdout.write(self.style.WARNING(f"Failed: {f}"))
        self.stdout.write(self.style.SUCCESS(f"Saved {rent_rows} rent rows and {enrollment_rows} student rows."))
