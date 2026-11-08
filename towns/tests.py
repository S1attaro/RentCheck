from datetime import date

from django.test import TestCase
from django.urls import reverse

from . import stats
from .models import EnrollmentPoint, RentPoint, Town


class TownTestBase(TestCase):
    def setUp(self):
        self.town = Town.objects.create(name="Testville", state="IL", university="Test U", slug="testville")
        # 13 months of all-unit rent: 1000 rising by 10 each month.
        for i in range(13):
            month = date(2025 + (i // 12), i % 12 + 1, 1)
            RentPoint.objects.create(town=self.town, month=month, rent=1000 + 10 * i, source="demo")
        RentPoint.objects.create(town=self.town, month=date(2026, 1, 1), bedrooms=2, rent=1500, source="demo")
        EnrollmentPoint.objects.create(town=self.town, year=2025, students=40000, source="demo")


class StatsTests(TownTestBase):
    def test_typical_rent_is_median_of_last_12_months(self):
        # Last 12 values are 1010..1120, median is 1065.
        self.assertEqual(stats.typical_rent(self.town), 1065)

    def test_bedroom_specific_numbers_used_when_present(self):
        self.assertEqual(stats.typical_rent(self.town, bedrooms=2), 1500)

    def test_falls_back_to_all_units_when_size_missing(self):
        self.assertEqual(stats.typical_rent(self.town, bedrooms=4), 1065)

    def test_yearly_change(self):
        # 1000 in Jan 2025 -> 1120 in Jan 2026 = 12%
        self.assertEqual(stats.yearly_change(self.town), 12.0)

    def test_real_data_beats_demo(self):
        RentPoint.objects.create(town=self.town, month=date(2026, 1, 1), rent=900, source="zillow")
        self.assertEqual(stats.best_source(self.town), "zillow")
        self.assertEqual(stats.typical_rent(self.town), 900)

    def test_town_with_no_data(self):
        empty = Town.objects.create(name="Empty", state="IL", university="X", slug="empty")
        self.assertIsNone(stats.typical_rent(empty))
        self.assertIsNone(stats.yearly_change(empty))


class PageAndApiTests(TownTestBase):
    def test_search(self):
        response = self.client.get(reverse("towns:list"), {"q": "test u"})
        self.assertContains(response, "Testville")
        response = self.client.get(reverse("towns:list"), {"q": "nowhere"})
        self.assertNotContains(response, "Testville")

    def test_detail_page(self):
        response = self.client.get(self.town.get_absolute_url())
        self.assertContains(response, "Testville")
        self.assertContains(response, "demo placeholders")

    def test_bad_bedrooms_param(self):
        self.assertEqual(self.client.get(self.town.get_absolute_url(), {"bedrooms": "abc"}).status_code, 404)

    def test_api_detail(self):
        data = self.client.get(reverse("api:town-detail", args=["testville"])).json()
        self.assertEqual(data["typical_rent"], 1065)
        self.assertEqual(len(data["rent"]), 13)
        self.assertEqual(data["enrollment"], [{"year": 2025, "students": 40000, "source": "demo"}])

    def test_api_errors_are_json(self):
        self.assertEqual(self.client.get(reverse("api:town-detail", args=["nope"])).status_code, 404)
        response = self.client.get(reverse("api:town-detail", args=["testville"]), {"bedrooms": "9"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())


class SourcePriorityTests(TestCase):
    def setUp(self):
        self.town = Town.objects.create(name="Mixville", state="IL", university="Mix U", slug="mixville")
        for month in (date(2025, 1, 1), date(2026, 1, 1)):
            RentPoint.objects.create(town=self.town, month=month, rent=500, source="demo")
            RentPoint.objects.create(town=self.town, month=month, bedrooms=2, rent=600, source="demo")

    def test_demo_ignored_once_real_data_exists(self):
        RentPoint.objects.create(town=self.town, month=date(2024, 7, 1), bedrooms=None, rent=1000, source="census")
        RentPoint.objects.create(town=self.town, month=date(2024, 7, 1), bedrooms=2, rent=1100, source="census")
        self.assertEqual(stats.best_source(self.town), "census")
        self.assertEqual(stats.typical_rent(self.town, bedrooms=2), 1100)

    def test_zillow_for_all_sizes_census_for_one_size(self):
        RentPoint.objects.create(town=self.town, month=date(2024, 7, 1), bedrooms=2, rent=1100, source="census")
        RentPoint.objects.create(town=self.town, month=date(2024, 7, 1), bedrooms=None, rent=1000, source="census")
        RentPoint.objects.create(town=self.town, month=date(2026, 9, 1), bedrooms=None, rent=1300, source="zillow")
        self.assertEqual(stats.best_source(self.town), "zillow")
        self.assertEqual(stats.best_source(self.town, bedrooms=2), "census")

    def test_size_fallback_is_reported(self):
        RentPoint.objects.create(town=self.town, month=date(2024, 7, 1), bedrooms=None, rent=1000, source="census")
        summary = stats.town_summary(self.town, bedrooms=3)
        self.assertTrue(summary["size_fallback"])
        self.assertEqual(summary["typical_rent"], 1000)

    def test_yearly_points_use_latest_year_only(self):
        RentPoint.objects.create(town=self.town, month=date(2023, 7, 1), rent=900, source="census")
        RentPoint.objects.create(town=self.town, month=date(2024, 7, 1), rent=990, source="census")
        self.assertEqual(stats.typical_rent(self.town), 990)
        self.assertEqual(stats.yearly_change(self.town), 10.0)
        self.assertEqual(stats.yearly_change_dollars(self.town), 90)
