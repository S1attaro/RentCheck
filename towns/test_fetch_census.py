"""Tests for fetch_census using a fake API response in the Census format."""

from datetime import date
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from towns.clients import ApiError
from towns.management.commands import fetch_census
from towns.models import DataImport, EnrollmentPoint, RentPoint, Town

HEADER = ["NAME", *fetch_census.RENT_VARS, fetch_census.RENTERS_VAR, *fetch_census.STUDENT_VARS, "state", "place"]


def census_row(name, rents, renters, undergrad, grad):
    return [name, *[str(r) for r in rents], str(renters), str(undergrad), str(grad), "17", "00000"]


FAKE_RESPONSE = [
    HEADER,
    # all, studio, 1, 2, 3, 4, 5+
    census_row("Champaign city, Illinois", [1000, 700, 850, 1100, 1400, 1800, 2100], 30000, 25000, 5000),
    census_row("Urbana city, Illinois", [900, 650, 800, 1000, 1300, -666666666, 2000], 10000, 8000, 2000),
    census_row("Springfield city, Illinois", [950, 600, 800, 1000, 1200, 1500, 1700], 40000, 3000, 1000),
]


class FetchCensusTests(TestCase):
    def setUp(self):
        self.town = Town.objects.create(
            name="Urbana-Champaign", state="IL", university="UIUC", slug="urbana-champaign",
            census_places="Champaign city,Urbana city",
        )

    def run_command(self, fake):
        out = StringIO()
        with patch.object(fetch_census, "get_json", fake):
            call_command("fetch_census", "--start", "2024", "--end", "2024", stdout=out)
        return out.getvalue()

    def test_combines_places_weighted_by_renters(self):
        self.run_command(lambda *a, **k: FAKE_RESPONSE)
        two_bed = RentPoint.objects.get(town=self.town, bedrooms=2, source="census")
        # (1100 * 30000 + 1000 * 10000) / 40000 = 1075
        self.assertEqual(float(two_bed.rent), 1075.0)
        self.assertEqual(two_bed.month, date(2024, 7, 1))

    def test_missing_value_uses_other_place_only(self):
        self.run_command(lambda *a, **k: FAKE_RESPONSE)
        four_bed = RentPoint.objects.get(town=self.town, bedrooms=4, source="census")
        self.assertEqual(float(four_bed.rent), 1800.0)

    def test_students_added_together(self):
        self.run_command(lambda *a, **k: FAKE_RESPONSE)
        self.assertEqual(EnrollmentPoint.objects.get(town=self.town, year=2024, source="census").students, 40000)

    def test_rerun_does_not_duplicate(self):
        self.run_command(lambda *a, **k: FAKE_RESPONSE)
        self.run_command(lambda *a, **k: FAKE_RESPONSE)
        self.assertEqual(RentPoint.objects.filter(source="census").count(), 7)
        self.assertEqual(DataImport.objects.filter(source="census").count(), 2)

    def test_keeps_university_enrollment_alongside(self):
        EnrollmentPoint.objects.create(town=self.town, year=2024, students=56000, source="ipeds")
        self.run_command(lambda *a, **k: FAKE_RESPONSE)
        self.assertEqual(EnrollmentPoint.objects.get(town=self.town, year=2024, source="ipeds").students, 56000)
        self.assertEqual(EnrollmentPoint.objects.get(town=self.town, year=2024, source="census").students, 40000)

    def test_api_failure_is_reported_not_crashing(self):
        def fail(*a, **k):
            raise ApiError("census returned HTTP 500")

        out = self.run_command(fail)
        self.assertIn("Failed", out)
        self.assertFalse(RentPoint.objects.exists())
