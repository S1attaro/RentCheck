"""Pull official enrollment and off-campus living cost from College Scorecard.

    python manage.py fetch_scorecard
    python manage.py fetch_scorecard --start 2015 --end 2023

One call per school. Saves:
  - undergrad enrollment by year (EnrollmentPoint, source "ipeds")
  - the school's latest enrollment and its own estimate of off-campus room and board (on Town)
Sign up: https://collegescorecard.ed.gov/data/api-documentation/
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from towns.clients import ApiError, get_json, pick
from towns.models import DataImport, EnrollmentPoint, Town

BASE_URL = "https://api.data.gov/ed/collegescorecard/v1/schools"


def to_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class Command(BaseCommand):
    help = "Fetch enrollment and off-campus cost estimates from College Scorecard."

    def add_arguments(self, parser):
        parser.add_argument("--start", type=int, default=2015)
        parser.add_argument("--end", type=int, default=2023)
        parser.add_argument("--towns", default="")

    def handle(self, start, end, towns, **options):
        if not settings.SCORECARD_API_KEY:
            raise CommandError(
                "Set SCORECARD_API_KEY in .env (sign up at https://collegescorecard.ed.gov/data/api-documentation/)"
            )

        town_qs = Town.objects.exclude(scorecard_id="")
        if towns:
            town_qs = town_qs.filter(slug__in=[s.strip() for s in towns.split(",")])

        years = list(range(start, end + 1))
        fields = ["id", "school.name", "latest.student.size", "latest.cost.roomboard.offcampus"]
        fields += [f"{y}.student.size" for y in years]

        saved = 0
        failures = []
        for town in town_qs:
            params = {"id": town.scorecard_id, "fields": ",".join(fields), "api_key": settings.SCORECARD_API_KEY}
            try:
                data = get_json("scorecard", BASE_URL, params=params)
            except ApiError as e:
                failures.append(f"{town}: {e}")
                continue

            results = data.get("results") or []
            if not results:
                self.stdout.write(self.style.WARNING(f"{town}: no school with id {town.scorecard_id}"))
                continue
            school = results[0]

            town.school_size = to_int(pick(school, "latest.student.size"))
            town.school_offcampus_cost = to_int(pick(school, "latest.cost.roomboard.offcampus"))
            town.save(update_fields=["school_size", "school_offcampus_cost"])

            for year in years:
                size = to_int(pick(school, f"{year}.student.size"))
                if size:
                    EnrollmentPoint.objects.update_or_create(
                        town=town, year=year, source="ipeds", defaults={"students": size}
                    )
                    saved += 1
            # Print the name so a wrong ID in towns.csv is easy to spot.
            self.stdout.write(f"{town}: matched '{pick(school, 'school.name')}'")

        DataImport.objects.create(source="ipeds", rows=saved, detail=f"College Scorecard, {len(failures)} failed calls")
        for f in failures:
            self.stdout.write(self.style.WARNING(f"Failed: {f}"))
        self.stdout.write(self.style.SUCCESS(f"Saved {saved} enrollment rows."))
