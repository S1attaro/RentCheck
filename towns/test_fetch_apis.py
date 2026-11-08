"""Tests for the RentCast, HUD, and College Scorecard commands.

The fake responses follow each API's documented format. No real calls are made.
"""

import io
import json
from datetime import date
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from towns import clients
from towns.management.commands import fetch_hud, fetch_rentcast, fetch_scorecard
from towns.models import ApiCall, EnrollmentPoint, Listing, RentPoint, Town


def make_town(**extra):
    defaults = dict(
        name="Urbana-Champaign", state="IL", university="UIUC", slug="urbana-champaign",
        zillow_names="Champaign,Urbana", county="Champaign County", zip_codes="61820,61801", scorecard_id="145637",
    )
    defaults.update(extra)
    return Town.objects.create(**defaults)


def run(command, *args):
    out = StringIO()
    call_command(command, *args, stdout=out)
    return out.getvalue()


# ---------- shared client ----------

class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class ClientTests(TestCase):
    def test_logs_call_without_secret(self):
        body = FakeResponse(json.dumps({"ok": 1}).encode())
        with patch("towns.clients.urlopen", return_value=body):
            data = clients.get_json("scorecard", "https://example.com/x", params={"id": "1", "api_key": "SECRET"})
        self.assertEqual(data, {"ok": 1})
        call = ApiCall.objects.get()
        self.assertTrue(call.ok)
        self.assertNotIn("SECRET", call.url)

    def test_pick_flat_and_nested(self):
        self.assertEqual(clients.pick({"latest.student.size": 5}, "latest.student.size"), 5)
        self.assertEqual(clients.pick({"latest": {"student": {"size": 6}}}, "latest.student.size"), 6)
        self.assertIsNone(clients.pick({}, "latest.student.size"))


# ---------- RentCast ----------

MARKET = {
    "id": "61820",
    "zipCode": "61820",
    "rentalData": {
        "lastUpdatedDate": "2026-11-01T00:00:00.000Z",
        "averageRent": 1250, "medianRent": 1200,
        "dataByBedrooms": [{"bedrooms": 1, "medianRent": 950}, {"bedrooms": 2, "medianRent": 1300}],
        "history": {
            "2026-10": {"date": "2026-10-01T00:00:00.000Z", "medianRent": 1180,
                        "dataByBedrooms": [{"bedrooms": 2, "averageRent": 1280}]},
        },
    },
}

LISTINGS = [
    {"id": "a1", "formattedAddress": "1 Green St, Champaign, IL 61820", "zipCode": "61820", "propertyType": "Apartment",
     "bedrooms": 2, "bathrooms": 1, "squareFootage": 800, "price": 1250, "listedDate": "2026-10-20T00:00:00.000Z",
     "daysOnMarket": 19, "status": "Active", "latitude": 40.11, "longitude": -88.23},
    {"id": "a2", "formattedAddress": "2 John St, Champaign, IL 61820", "bedrooms": 6, "price": 4200},
    {"id": "a3", "formattedAddress": "No price", "bedrooms": 1},
]


def fake_rentcast(service, url, params=None, headers=None):
    ApiCall.objects.create(service=service, url=url, ok=True)
    return MARKET if url.endswith("/markets") else LISTINGS


@override_settings(RENTCAST_API_KEY="test", RENTCAST_MONTHLY_LIMIT=45)
class RentCastTests(TestCase):
    def setUp(self):
        self.town = make_town()

    def test_market_stats_saved_by_bedroom_and_month(self):
        with patch.object(fetch_rentcast, "get_json", fake_rentcast):
            run("fetch_rentcast")
        nov = RentPoint.objects.filter(town=self.town, source="rentcast", month=date(2026, 11, 1))
        self.assertEqual(float(nov.get(bedrooms=None).rent), 1200)
        self.assertEqual(float(nov.get(bedrooms=2).rent), 1300)
        oct_two = RentPoint.objects.get(town=self.town, source="rentcast", month=date(2026, 10, 1), bedrooms=2)
        self.assertEqual(float(oct_two.rent), 1280)  # falls back to averageRent

    def test_listings_saved_and_cleaned(self):
        Listing.objects.create(town=self.town, external_id="old", address="Gone", price=900)
        with patch.object(fetch_rentcast, "get_json", fake_rentcast):
            run("fetch_rentcast")
        self.assertEqual(set(Listing.objects.values_list("external_id", flat=True)), {"a1", "a2"})
        self.assertEqual(Listing.objects.get(external_id="a2").bedrooms, 5)  # 6 beds stored as 5+
        self.assertEqual(Listing.objects.get(external_id="a1").listed_date, date(2026, 10, 20))

    @override_settings(RENTCAST_MONTHLY_LIMIT=1)
    def test_stops_at_monthly_limit(self):
        with patch.object(fetch_rentcast, "get_json", fake_rentcast) as fake:
            out = run("fetch_rentcast")
        self.assertIn("limit reached", out)
        self.assertEqual(ApiCall.objects.filter(service="rentcast").count(), 1)

    def test_dry_run_makes_no_calls(self):
        out = run("fetch_rentcast", "--dry-run")
        self.assertIn("Plan: 2 calls", out)
        self.assertFalse(ApiCall.objects.exists())

    @override_settings(RENTCAST_API_KEY="")
    def test_missing_key(self):
        with self.assertRaises(CommandError):
            run("fetch_rentcast")


# ---------- HUD ----------

STATE_DATA = {"data": {"year": "2027", "counties": [
    {"county_name": "Cook County", "fips_code": "1703199999"},
    {"county_name": "Champaign County", "fips_code": "1701999999"},
]}}

COUNTY_DATA = {"data": {"county_name": "Champaign County", "year": "2027", "smallarea_status": "0",
                        "basicdata": {"Efficiency": 800, "One-Bedroom": 900, "Two-Bedroom": 1100,
                                      "Three-Bedroom": 1450, "Four-Bedroom": 1600, "year": "2027"}}}

ZIP_DATA = {"data": {"year": "2027", "smallarea_status": "1", "basicdata": [
    {"zip_code": "MSA level", "Efficiency": 800, "One-Bedroom": 900, "Two-Bedroom": 1100},
    {"zip_code": "61820", "efficiency": 850, "One-Bedroom": 950, "Two-Bedroom": 1200},
    {"zip_code": "61801", "efficiency": 750, "One-Bedroom": 850, "Two-Bedroom": 1000},
    {"zip_code": "61874", "efficiency": 999, "One-Bedroom": 999, "Two-Bedroom": 999},
]}}


@override_settings(HUD_API_TOKEN="test")
class HudTests(TestCase):
    def setUp(self):
        self.town = make_town()

    def run_with(self, fmr_data):
        def fake(service, url, params=None, headers=None):
            self.assertEqual(headers["Authorization"], "Bearer test")
            return STATE_DATA if "/statedata/" in url else fmr_data

        with patch.object(fetch_hud, "get_json", fake):
            return run("fetch_hud")

    def test_county_rents(self):
        self.run_with(COUNTY_DATA)
        point = RentPoint.objects.get(town=self.town, source="hud", bedrooms=2)
        self.assertEqual(float(point.rent), 1100)
        self.assertEqual(point.month, date(2026, 10, 1))  # FY2027 starts Oct 2026

    def test_small_area_uses_campus_zips(self):
        out = self.run_with(ZIP_DATA)
        self.assertIn("campus ZIPs", out)
        self.assertEqual(float(RentPoint.objects.get(source="hud", bedrooms=2).rent), 1100)  # (1200 + 1000) / 2
        self.assertEqual(float(RentPoint.objects.get(source="hud", bedrooms=0).rent), 800)

    def test_unknown_county(self):
        self.town.county = "Nowhere County"
        self.town.save()
        out = self.run_with(COUNTY_DATA)
        self.assertIn("no HUD county", out)
        self.assertFalse(RentPoint.objects.exists())


# ---------- College Scorecard ----------

SCORECARD = {"metadata": {"total": 1, "page": 0, "per_page": 20}, "results": [{
    "id": 145637, "school.name": "University of Illinois Urbana-Champaign",
    "latest.student.size": 37000, "latest.cost.roomboard.offcampus": 12600,
    "2022.student.size": 35000, "2023.student.size": 36000,
}]}


@override_settings(SCORECARD_API_KEY="test")
class ScorecardTests(TestCase):
    def setUp(self):
        self.town = make_town()

    def test_saves_enrollment_and_cost(self):
        with patch.object(fetch_scorecard, "get_json", lambda *a, **k: SCORECARD):
            out = run("fetch_scorecard", "--start", "2021", "--end", "2023")
        self.assertIn("University of Illinois Urbana-Champaign", out)
        self.town.refresh_from_db()
        self.assertEqual(self.town.school_size, 37000)
        self.assertEqual(self.town.school_offcampus_cost, 12600)
        self.assertEqual(
            list(EnrollmentPoint.objects.filter(source="ipeds").values_list("year", "students")),
            [(2022, 35000), (2023, 36000)],
        )

    def test_no_results(self):
        with patch.object(fetch_scorecard, "get_json", lambda *a, **k: {"results": []}):
            out = run("fetch_scorecard")
        self.assertIn("no school with id", out)
