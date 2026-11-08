"""Run every data fetch that has a key set. Safe to run any time.

    python manage.py refresh_data
    python manage.py refresh_data --skip-rentcast    # save RentCast's 50 monthly calls
"""

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Fetch from Census, HUD, College Scorecard, and RentCast (skips any without a key)."

    def add_arguments(self, parser):
        parser.add_argument("--skip-rentcast", action="store_true")

    def handle(self, skip_rentcast, **options):
        steps = [
            ("Census", "fetch_census", True),  # works without a key
            ("HUD", "fetch_hud", bool(settings.HUD_API_TOKEN)),
            ("College Scorecard", "fetch_scorecard", bool(settings.SCORECARD_API_KEY)),
            ("RentCast", "fetch_rentcast", bool(settings.RENTCAST_API_KEY) and not skip_rentcast),
        ]
        for name, command, ready in steps:
            if not ready:
                self.stdout.write(self.style.WARNING(f"Skipping {name} (no key in .env or skipped)"))
                continue
            self.stdout.write(self.style.MIGRATE_HEADING(f"== {name} =="))
            try:
                call_command(command, stdout=self.stdout, stderr=self.stderr)
            except CommandError as e:
                self.stdout.write(self.style.ERROR(f"{name} failed: {e}"))
