"""Import real rent numbers from the Zillow Observed Rent Index (ZORI).

1. Go to https://www.zillow.com/research/data/
2. Under "Rentals", pick "ZORI (Smoothed): All Homes Plus Multifamily" and geography "City".
3. Download the CSV and run:
       python manage.py import_zori path/to/City_zori_uc_sfrcondomfr_sm_month.csv

Each town's zillow_names lists the city names to match. If a town has more than one
(like Champaign and Urbana), the rents are averaged for each month.
"""

import csv
from collections import defaultdict
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from towns.models import DataImport, RentPoint, Town


def parse_month(column):
    """Zillow columns look like 2024-08-31. Returns date(2024, 8, 1) or None."""
    try:
        year, month, _ = column.split("-")
        return date(int(year), int(month), 1)
    except ValueError:
        return None


class Command(BaseCommand):
    help = "Import Zillow ZORI city-level rents for every town."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--since", default="2018-01", help="Earliest month to keep, YYYY-MM")

    def handle(self, csv_path, since, **options):
        since_year, since_month = map(int, since.split("-"))
        since_date = date(since_year, since_month, 1)

        try:
            f = open(csv_path, newline="", encoding="utf-8")
        except OSError as e:
            raise CommandError(f"Could not open {csv_path}: {e}")

        with f:
            reader = csv.DictReader(f)
            month_columns = [(c, parse_month(c)) for c in reader.fieldnames if parse_month(c)]
            # (city, state) -> row
            rows = {(r["RegionName"], r["State"]): r for r in reader}

        total = 0
        for town in Town.objects.all():
            names = [n.strip() for n in town.zillow_names.split(",") if n.strip()]
            matched = [rows[(n, town.state)] for n in names if (n, town.state) in rows]
            if not matched:
                self.stdout.write(self.style.WARNING(f"No Zillow match for {town} (tried {names})"))
                continue

            by_month = defaultdict(list)
            for row in matched:
                for column, month in month_columns:
                    if month >= since_date and row[column]:
                        by_month[month].append(float(row[column]))

            RentPoint.objects.filter(town=town, source="zillow").delete()
            RentPoint.objects.bulk_create(
                RentPoint(town=town, month=m, bedrooms=None, rent=round(sum(v) / len(v), 2), source="zillow")
                for m, v in sorted(by_month.items())
            )
            total += len(by_month)
            self.stdout.write(f"{town}: {len(by_month)} months from {len(matched)} Zillow cities")

        DataImport.objects.create(source="zillow", rows=total, detail=f"ZORI city file, since {since}")

        self.stdout.write(self.style.SUCCESS("Done. Real Zillow data now takes priority over demo data."))
