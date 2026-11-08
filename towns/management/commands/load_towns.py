"""Create or update towns from data/towns.csv.

To track a new college town, add a row to the CSV and run this again.
"""

import csv

from django.conf import settings
from django.core.management.base import BaseCommand

from towns.models import Town

TOWNS_CSV = settings.BASE_DIR / "data" / "towns.csv"


def load_towns(path=TOWNS_CSV):
    count = 0
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            Town.objects.update_or_create(
                slug=row["slug"].strip(),
                defaults={
                    "name": row["name"].strip(),
                    "state": row["state"].strip().upper(),
                    "university": row["university"].strip(),
                    "zillow_names": row["zillow_names"].strip(),
                    "census_places": row["census_places"].strip(),
                    "county": row.get("county", "").strip(),
                    "zip_codes": row.get("zip_codes", "").strip(),
                    "scorecard_id": row.get("scorecard_id", "").strip(),
                },
            )
            count += 1
    return count


class Command(BaseCommand):
    help = "Create or update towns from data/towns.csv"

    def handle(self, *args, **options):
        count = load_towns()
        self.stdout.write(self.style.SUCCESS(f"Loaded {count} towns."))
