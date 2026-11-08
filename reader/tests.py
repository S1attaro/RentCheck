import json
from datetime import date
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from towns.clients import ApiError
from towns.models import RentPoint, Town

from . import ai

LISTING = """Spacious 2 bed / 1 bath apartment near campus in Champaign! 850 sq ft, furnished,
$1,350/month. Water included. Call (217) 555-0142 or email landlord@example.com."""


def groq_reply(payload):
    """Fake Groq response in the OpenAI chat format."""
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return {"choices": [{"message": {"content": content}}]}


GOOD = {"city": "Champaign", "state": "IL", "bedrooms": 2, "bathrooms": 1, "monthly_rent": 1350,
        "rent_is_per_bed": False, "utilities_included": False, "square_feet": 850, "furnished": True}


@override_settings(GROQ_API_KEY="test")
class ReaderTests(TestCase):
    def setUp(self):
        cache.clear()
        self.town = Town.objects.create(
            name="Urbana-Champaign", state="IL", university="UIUC", slug="urbana-champaign",
            zillow_names="Champaign,Urbana", census_places="Champaign city,Urbana city",
        )
        RentPoint.objects.create(town=self.town, month=date(2024, 7, 1), bedrooms=2, rent=1200, source="census")

    def test_ai_result_is_checked_and_town_matched(self):
        with patch.object(ai, "post_json", return_value=groq_reply(GOOD)):
            result = ai.read_listing(LISTING)
        self.assertEqual(result["method"], "ai")
        self.assertEqual(result["town"], self.town)
        self.assertEqual(result["fields"]["monthly_rent"], 1350)
        self.assertEqual(result["fields"]["bedrooms"], 2)
        self.assertTrue(result["fields"]["furnished"])

    def test_phone_and_email_removed_before_sending(self):
        with patch.object(ai, "post_json", return_value=groq_reply(GOOD)) as fake:
            ai.read_listing(LISTING)
        sent = fake.call_args[0][2]["messages"][1]["content"]
        self.assertNotIn("555-0142", sent)
        self.assertNotIn("landlord@example.com", sent)

    def test_made_up_rent_is_thrown_out(self):
        with patch.object(ai, "post_json", return_value=groq_reply({**GOOD, "monthly_rent": 999})):
            result = ai.read_listing(LISTING)
        # The AI's 999 isn't in the listing, so it's dropped and the backup finds $1,350.
        self.assertEqual(result["fields"]["monthly_rent"], 1350)
        self.assertTrue(any("isn't in the listing" in w for w in result["warnings"]))

    def test_json_wrapped_in_text_still_works(self):
        reply = groq_reply("Here you go:\n" + json.dumps(GOOD) + "\nDone.")
        with patch.object(ai, "post_json", return_value=reply):
            result = ai.read_listing(LISTING)
        self.assertEqual(result["method"], "ai")

    def test_groq_down_uses_backup(self):
        with patch.object(ai, "post_json", side_effect=ApiError("groq returned HTTP 503", status=503)):
            result = ai.read_listing(LISTING)
        self.assertEqual(result["method"], "backup")
        self.assertEqual(result["fields"]["monthly_rent"], 1350)
        self.assertEqual(result["fields"]["bedrooms"], 2)
        self.assertEqual(result["fields"]["square_feet"], 850)
        self.assertEqual(result["town"], self.town)

    def test_retries_without_json_mode_on_400(self):
        calls = []

        def fake(service, url, body, headers=None):
            calls.append("response_format" in body)
            if len(calls) == 1:
                raise ApiError("groq returned HTTP 400", status=400)
            return groq_reply(GOOD)

        with patch.object(ai, "post_json", fake):
            result = ai.read_listing(LISTING)
        self.assertEqual(calls, [True, False])
        self.assertEqual(result["method"], "ai")

    @override_settings(GROQ_API_KEY="")
    def test_no_key_uses_backup(self):
        result = ai.read_listing(LISTING)
        self.assertEqual(result["method"], "backup")

    def test_backup_handles_per_bed_and_studio(self):
        out = ai.backup_extract("Studio, $725 per person, utilities included")
        self.assertEqual(out["bedrooms"], 0)
        self.assertEqual(out["monthly_rent"], 725)
        self.assertTrue(out["rent_is_per_bed"])
        self.assertTrue(out["utilities_included"])

    def test_page_shows_comparison(self):
        with patch.object(ai, "post_json", return_value=groq_reply(GOOD)):
            response = self.client.post(reverse("reader:page"), {"text": LISTING})
        self.assertContains(response, "$1,350/month")
        self.assertContains(response, "12% above typical")  # 1350 vs 1200

    def test_empty_paste_shows_plain_error(self):
        response = self.client.post(reverse("reader:page"), {"text": ""})
        self.assertContains(response, "Paste the listing text first.")

    def test_api(self):
        with patch.object(ai, "post_json", return_value=groq_reply(GOOD)):
            response = self.client.post(reverse("reader:api"), json.dumps({"text": LISTING}), content_type="application/json")
        data = response.json()
        self.assertEqual(data["town"], "urbana-champaign")
        self.assertEqual(data["fields"]["monthly_rent"], 1350)
        self.assertEqual(data["comparison"]["diff_pct"], 12)

    def test_api_bad_input(self):
        response = self.client.post(reverse("reader:api"), "not json", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    @override_settings(GROQ_API_KEY="")
    def test_rate_limit(self):
        url = reverse("reader:api")
        body = json.dumps({"text": LISTING})
        for _ in range(20):
            self.client.post(url, body, content_type="application/json")
        response = self.client.post(url, body, content_type="application/json")
        self.assertEqual(response.status_code, 429)

    @override_settings(GROQ_API_KEY="")
    def test_sample_then_submit_reads_it(self):
        response = self.client.post(reverse("reader:page") + "?sample=1", {"text": LISTING})
        self.assertContains(response, "$1,350/month")

    def test_link_only_gets_helpful_message(self):
        response = self.client.post(reverse("reader:page"), {"text": "https://www.zillow.com/apartments/urbana-il/parkside/5YD4FP/"})
        self.assertContains(response, "Links are not valid.")
        response = self.client.post(reverse("reader:api"), json.dumps({"text": "https://example.com/x"}), content_type="application/json")
        self.assertEqual(response.status_code, 400)

    @override_settings(GROQ_API_KEY="")
    def test_whole_page_paste(self):
        menu = "\n".join(["Buy", "Rent", "Sell", "Get a mortgage", "Find an agent", "Skip main navigation"] * 200)
        page = menu + "\nParkside Apartments, Urbana, IL 61801\n2 bd | 1 ba | 900 sqft\n$1,295/mo\n" + menu
        self.assertGreater(len(page), 4000)
        response = self.client.post(reverse("reader:page"), {"text": page})
        self.assertNotContains(response, "too long")
        self.assertContains(response, "$1,295/month")
        result = ai.read_listing(page)
        self.assertEqual(result["fields"]["bedrooms"], 2)
        self.assertEqual(result["town"], self.town)
        self.assertLessEqual(len(result["cleaned_text"]), ai.MAX_CHARS)

    def test_nearby_listings_are_dropped(self):
        filler = "\n".join(["Buy", "Rent", "Sell", "Save", "Share"] * 20)
        page = (filler + "\nMaple Court, Urbana, IL 61801\n2 beds\n2 bed $1,080+\nCost calculator\n"
                "Monthly base rent\n$1,080 - $1,210\nNearby apartments for rent\n$1,695 - $1,795\n"
                "Fees may apply\n2 bd2 ba920 sqft\nSimilar apartments for rent\n$1,750\n2 bd1 ba850 sqft\n" + filler)
        cleaned = ai.clean_text(page)
        self.assertIn("1,210", cleaned)
        self.assertNotIn("920", cleaned)
        self.assertNotIn("1,795", cleaned)

    def test_rent_range(self):
        with patch.object(ai, "post_json", return_value=groq_reply({**GOOD, "monthly_rent": 1080, "max_rent": 1210})):
            result = ai.read_listing("Urbana, IL. 2 beds. Rent $1,080 - $1,210 a month.")
        self.assertEqual((result["fields"]["monthly_rent"], result["fields"]["max_rent"]), (1080, 1210))
        self.assertIsInstance(result["seconds"], float)

    def test_asks_for_short_thinking_and_drops_it_on_400(self):
        bodies = []

        def fake(service, url, body, headers=None):
            bodies.append(dict(body))
            if len(bodies) == 1:
                raise ApiError("groq returned HTTP 400", status=400)
            return groq_reply(GOOD)

        with self.settings(GROQ_MODEL="openai/gpt-oss-20b"), patch.object(ai, "post_json", fake):
            ai.read_listing(LISTING)
        self.assertEqual(bodies[0]["reasoning_effort"], "low")
        self.assertNotIn("reasoning_effort", bodies[1])
        self.assertNotIn("response_format", bodies[1])

    def test_extra_details(self):
        page = ("Maple Court\n2 beds\n$1,100\n3 units available\nPet-friendly\nUnit Features\nDishwasher\n"
                "Air Conditioning: Air Conditioner\nPolicies\nParking\nStreet\nLease terms\n12 months\n"
                "Nearby places\nGold's Gym\nCrystal Pool")
        x = ai.extra_details(page)
        self.assertEqual(x["pets"], "Allowed")
        self.assertEqual(x["units_available"], 3)
        self.assertEqual(x["lease_terms"], "12 months")
        self.assertEqual(x["parking"], "Street")
        self.assertEqual(x["amenities"], ["Dishwasher", "Air conditioning"])  # gym and pool were in "Nearby places"

    @override_settings(GROQ_API_KEY="")
    def test_page_shows_not_listed_and_extras(self):
        response = self.client.post(reverse("reader:page"), {"text": "Champaign 2 bed $1,200/month. Pets allowed. Dishwasher."})
        self.assertContains(response, "Not listed")
        self.assertContains(response, "Pets: Allowed")
        self.assertContains(response, "Dishwasher")

    def test_unit_section_after_skipped_sections_is_kept(self):
        filler = "\n".join(["Buy", "Rent", "Sell", "Save"] * 25)
        page = (filler + "\nMaple Court, Urbana, IL\n2 bed $1,080+\nFrequently asked questions\nWhat schools?\n"
                "Nearby cities\nAll Savoy Apartments\nBack to listing\nUnit 1107-A22\n2 beds, 1 bath | $1,080\n"
                "850 sqft\nLease terms\nLease length: 12 months")
        cleaned = ai.clean_text(page)
        self.assertIn("2 beds, 1 bath", cleaned)
        self.assertIn("850 sqft", cleaned)
        self.assertNotIn("Savoy", cleaned)
