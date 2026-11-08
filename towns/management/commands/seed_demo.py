"""Load the towns from data/towns.csv plus DEMO rent and enrollment numbers.

The demo numbers are made up so the site works before real data is fetched.
They are saved with source="demo", labeled on every page, and ignored as soon
as a town has real data (run `python manage.py fetch_census`).
"""

import zlib
from datetime import date

from django.core.management.base import BaseCommand

from towns.models import EnrollmentPoint, RentPoint, Town

from .load_towns import load_towns

BEDROOM_FACTOR = {0: 0.72, 1: 0.85, 2: 1.05, 3: 1.35, 4: 1.65, 5: 1.95}


def months(start, end):
    y, m = start
    while (y, m) <= end:
        yield date(y, m, 1)
        m += 1
        if m == 13:
            y, m = y + 1, 1


class Command(BaseCommand):
    help = "Load towns and fill them with DEMO (not real) numbers."

    def handle(self, *args, **options):
        town_count = load_towns()
        RentPoint.objects.filter(source="demo").delete()
        EnrollmentPoint.objects.filter(source="demo").delete()

        for town in Town.objects.all():
            # Same made-up numbers every run, different for each town.
            seed = zlib.crc32(town.slug.encode())
            base = 950 + seed % 700
            growth = 0.03 + (seed % 30) / 1000

            points = []
            for k, month in enumerate(months((2021, 1), (2026, 9))):
                season = 1.02 if month.month in (8, 9) else 1.0
                all_units = base * (1 + growth) ** (k / 12) * season
                points.append(RentPoint(town=town, month=month, rent=round(all_units, 2), source="demo"))
                for beds, factor in BEDROOM_FACTOR.items():
                    points.append(
                        RentPoint(town=town, month=month, bedrooms=beds, rent=round(all_units * factor, 2), source="demo")
                    )
            RentPoint.objects.bulk_create(points)

            students = 20000 + seed % 25000
            for year in range(2015, 2025):
                if not EnrollmentPoint.objects.filter(town=town, year=year).exists():
                    EnrollmentPoint.objects.create(town=town, year=year, students=students, source="demo")
                students = int(students * 1.015)

        self.stdout.write(self.style.SUCCESS(f"Loaded {town_count} towns with DEMO numbers."))
