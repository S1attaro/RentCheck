"""Import real enrollment numbers from a CSV.

Fill in data/enrollment_template.csv with columns: town_slug,year,students
(fall enrollment from NCES IPEDS or the university's own fact book), then run:
    python manage.py import_enrollment data/enrollment.csv
"""

import csv

from django.core.management.base import BaseCommand, CommandError

from towns.models import DataImport, EnrollmentPoint, Town


class Command(BaseCommand):
    help = "Import enrollment by town and year from a CSV (town_slug,year,students)."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")

    def handle(self, csv_path, **options):
        towns = {t.slug: t for t in Town.objects.all()}
        count = 0
        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                for line_no, row in enumerate(csv.DictReader(f), start=2):
                    town = towns.get(row.get("town_slug", "").strip())
                    if town is None:
                        self.stdout.write(self.style.WARNING(f"Line {line_no}: unknown town_slug, skipped"))
                        continue
                    try:
                        year, students = int(row["year"]), int(row["students"])
                    except (KeyError, ValueError):
                        self.stdout.write(self.style.WARNING(f"Line {line_no}: bad year or students, skipped"))
                        continue
                    EnrollmentPoint.objects.update_or_create(
                        town=town, year=year, source="ipeds", defaults={"students": students}
                    )
                    count += 1
        except OSError as e:
            raise CommandError(f"Could not open {csv_path}: {e}")

        DataImport.objects.create(source="ipeds", rows=count, detail=str(csv_path))
        self.stdout.write(self.style.SUCCESS(f"Imported {count} enrollment rows."))
