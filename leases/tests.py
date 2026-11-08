from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from towns.models import RentPoint, Town

from .models import LeaseReport
from .stats import reported_summary


class LeaseTests(TestCase):
    def setUp(self):
        self.town = Town.objects.create(name="Testville", state="IL", university="Test U", slug="testville")
        self.alice = User.objects.create_user("alice", password="pass-12345-x")
        self.bob = User.objects.create_user("bob", password="pass-12345-x")

    def form_data(self, **overrides):
        data = {
            "town": self.town.pk,
            "bedrooms": 2,
            "monthly_rent": 1200,
            "asking_rent": 1250,
            "lease_start": "2025-08",
            "lease_months": 12,
            "property_type": "apartment",
        }
        data.update(overrides)
        return data

    def make_report(self, user, rent=1200, **kwargs):
        return LeaseReport.objects.create(
            user=user, town=self.town, bedrooms=2, monthly_rent=rent, lease_start=date(2025, 8, 1), **kwargs
        )

    def test_login_required(self):
        response = self.client.get(reverse("leases:new"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('leases:new')}")

    def test_create_report(self):
        self.client.login(username="alice", password="pass-12345-x")
        response = self.client.post(reverse("leases:new"), self.form_data())
        self.assertRedirects(response, reverse("leases:mine"))
        report = LeaseReport.objects.get()
        self.assertEqual(report.user, self.alice)
        self.assertEqual(report.paid_vs_asking, -50)

    def test_rejects_bad_numbers(self):
        self.client.login(username="alice", password="pass-12345-x")
        response = self.client.post(reverse("leases:new"), self.form_data(monthly_rent=12000))
        self.assertEqual(response.status_code, 200)
        response = self.client.post(reverse("leases:new"), self.form_data(asking_rent=500))
        self.assertContains(response, "very different from the rent you paid")
        response = self.client.post(reverse("leases:new"), self.form_data(lease_start="2005-08"))
        self.assertContains(response, "2010 or later")
        self.assertEqual(LeaseReport.objects.count(), 0)

    def test_users_only_see_and_edit_their_own(self):
        report = self.make_report(self.alice)
        self.client.login(username="bob", password="pass-12345-x")
        self.assertNotContains(self.client.get(reverse("leases:mine")), "$1200")
        self.assertEqual(self.client.get(reverse("leases:edit", args=[report.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("leases:delete", args=[report.pk])).status_code, 404)
        self.assertTrue(LeaseReport.objects.filter(pk=report.pk).exists())

    def test_owner_can_update_and_delete(self):
        report = self.make_report(self.alice)
        self.client.login(username="alice", password="pass-12345-x")
        self.client.post(reverse("leases:edit", args=[report.pk]), self.form_data(monthly_rent=1300))
        report.refresh_from_db()
        self.assertEqual(report.monthly_rent, 1300)
        self.client.post(reverse("leases:delete", args=[report.pk]))
        self.assertFalse(LeaseReport.objects.exists())

    def test_summary_hidden_until_three_reports(self):
        self.make_report(self.alice, rent=1000)
        self.make_report(self.bob, rent=1100)
        self.assertFalse(reported_summary(self.town)["enough"])
        self.make_report(self.bob, rent=600, per_person=True)  # 600 x 2 beds = 1200 for the unit
        summary = reported_summary(self.town)
        self.assertTrue(summary["enough"])
        self.assertEqual(summary["median_unit_rent"], 1100)

    def test_outlier_is_saved_but_not_counted(self):
        RentPoint.objects.create(town=self.town, month=date(2025, 7, 1), bedrooms=2, rent=1200, source="census")
        self.client.login(username="alice", password="pass-12345-x")
        self.client.post(reverse("leases:new"), self.form_data(monthly_rent=9000, asking_rent=9000))
        report = LeaseReport.objects.get()
        self.assertTrue(report.flagged)
        for user, rent in [(self.alice, 1100), (self.bob, 1200), (self.bob, 1300)]:
            self.make_report(user, rent=rent)
        summary = reported_summary(self.town)
        self.assertEqual(summary["count"], 3)
        self.assertEqual(summary["median_unit_rent"], 1200)

    def test_per_bed_rent_is_not_flagged(self):
        # $600 per bed in a 2 bed = $1200 for the unit, right at typical.
        RentPoint.objects.create(town=self.town, month=date(2025, 7, 1), bedrooms=2, rent=1200, source="census")
        self.client.login(username="alice", password="pass-12345-x")
        self.client.post(reverse("leases:new"), self.form_data(monthly_rent=600, asking_rent=600, per_person="on"))
        self.assertFalse(LeaseReport.objects.get().flagged)

    def test_month_and_year_dropdowns(self):
        self.client.login(username="alice", password="pass-12345-x")
        data = self.form_data()
        del data["lease_start"]
        data.update({"lease_start_0": "8", "lease_start_1": "2025"})
        self.client.post(reverse("leases:new"), data)
        self.assertEqual(LeaseReport.objects.get().lease_start, date(2025, 8, 1))

    def test_missing_month_gives_plain_error(self):
        self.client.login(username="alice", password="pass-12345-x")
        data = self.form_data()
        del data["lease_start"]
        data.update({"lease_start_0": "", "lease_start_1": "2025"})
        response = self.client.post(reverse("leases:new"), data)
        self.assertContains(response, "Pick the month and the year your lease started.")
        self.assertFalse(LeaseReport.objects.exists())

    def test_edit_form_shows_saved_month(self):
        report = self.make_report(self.alice)
        self.client.login(username="alice", password="pass-12345-x")
        response = self.client.get(reverse("leases:edit", args=[report.pk]))
        self.assertContains(response, '<option value="8" selected>August</option>', html=True)

    def test_accepts_dollar_signs_and_commas(self):
        self.client.login(username="alice", password="pass-12345-x")
        self.client.post(reverse("leases:new"), self.form_data(monthly_rent="$1,200", asking_rent=" 1,250.00 "))
        report = LeaseReport.objects.get()
        self.assertEqual((report.monthly_rent, report.asking_rent), (1200, 1250))

    def test_month_kept_when_year_missing(self):
        self.client.login(username="alice", password="pass-12345-x")
        data = self.form_data()
        del data["lease_start"]
        data.update({"lease_start_0": "8", "lease_start_1": ""})
        response = self.client.post(reverse("leases:new"), data)
        self.assertContains(response, '<option value="8" selected>August</option>', html=True)
        self.assertContains(response, "Pick the month and the year your lease started.")
