"""Pull current rent stats and listings from RentCast.

    python manage.py fetch_rentcast --dry-run      # show how many calls it would use
    python manage.py fetch_rentcast                # all towns
    python manage.py fetch_rentcast --towns madison --skip-listings

The free plan is 50 calls a month, so each town uses at most 2 calls:
  1. /v1/markets for the town's main ZIP: median asking rent by bedroom count, plus 12 months of history
  2. /v1/listings/rental/long-term for the town: up to 500 active listings
The command stops before going over RENTCAST_MONTHLY_LIMIT (default 45).
Sign up: https://app.rentcast.io/app/api
"""

from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from towns.clients import ApiError, get_json, rentcast_calls_left
from towns.models import DataImport, Listing, RentPoint, Town

BASE_URL = "https://api.rentcast.io/v1"


def parse_date(value):
    """'2025-08-26T00:00:00.000Z' -> date(2025, 8, 26)"""
    try:
        y, m, d = str(value)[:10].split("-")
        return date(int(y), int(m), int(d))
    except (TypeError, ValueError):
        return None


def rent_from(stats):
    return stats.get("medianRent") or stats.get("averageRent")


def market_points(rental_data):
    """Turn a RentCast rentalData block into {(month, bedrooms): rent}."""
    points = {}

    def add(month, block):
        if month is None or not isinstance(block, dict):
            return
        if rent_from(block):
            points[(month, None)] = rent_from(block)
        for row in block.get("dataByBedrooms") or []:
            beds = row.get("bedrooms")
            if beds is not None and rent_from(row):
                points[(month, min(int(beds), 5))] = rent_from(row)

    for key, entry in (rental_data.get("history") or {}).items():
        add(parse_date(f"{key}-01"), entry)
    updated = parse_date(rental_data.get("lastUpdatedDate"))
    add(updated.replace(day=1) if updated else None, rental_data)
    return points


def listing_rows(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("listings") or data.get("results") or []
    return []


class Command(BaseCommand):
    help = "Fetch RentCast market stats and current listings (uses up to 2 calls per town)."

    def add_arguments(self, parser):
        parser.add_argument("--towns", default="", help="Comma separated slugs. Default: all towns")
        parser.add_argument("--skip-markets", action="store_true")
        parser.add_argument("--skip-listings", action="store_true")
        parser.add_argument("--dry-run", action="store_true", help="Only print how many calls would be used")

    def handle(self, towns, skip_markets, skip_listings, dry_run, **options):
        town_qs = Town.objects.all()
        if towns:
            town_qs = town_qs.filter(slug__in=[s.strip() for s in towns.split(",")])

        planned = 0
        for town in town_qs:
            planned += (0 if skip_markets or not town.zip_list else 1) + (0 if skip_listings else 1)
        left = rentcast_calls_left()
        self.stdout.write(f"Plan: {planned} calls. Left this month: {left} of {settings.RENTCAST_MONTHLY_LIMIT}.")
        if dry_run:
            return
        if not settings.RENTCAST_API_KEY:
            raise CommandError("Set RENTCAST_API_KEY in .env (sign up at https://app.rentcast.io/app/api)")

        headers = {"X-Api-Key": settings.RENTCAST_API_KEY}
        rent_rows = listing_rows_saved = 0
        failures = []

        for town in town_qs:
            if not skip_markets and town.zip_list:
                if rentcast_calls_left() <= 0:
                    self.stdout.write(self.style.WARNING("Monthly RentCast limit reached. Stopping."))
                    break
                try:
                    data = get_json(
                        "rentcast", f"{BASE_URL}/markets",
                        params={"zipCode": town.zip_list[0], "dataType": "Rental", "historyRange": 12},
                        headers=headers,
                    )
                    for (month, beds), rent in market_points(data.get("rentalData") or {}).items():
                        RentPoint.objects.update_or_create(
                            town=town, month=month, bedrooms=beds, source="rentcast", defaults={"rent": round(rent, 2)}
                        )
                        rent_rows += 1
                except ApiError as e:
                    failures.append(f"{town} markets: {e}")

            if not skip_listings:
                if rentcast_calls_left() <= 0:
                    self.stdout.write(self.style.WARNING("Monthly RentCast limit reached. Stopping."))
                    break
                city = (town.zillow_names.split(",")[0] or town.name).strip()
                try:
                    data = get_json(
                        "rentcast", f"{BASE_URL}/listings/rental/long-term",
                        params={"city": city, "state": town.state, "status": "Active", "limit": 500},
                        headers=headers,
                    )
                except ApiError as e:
                    failures.append(f"{town} listings: {e}")
                    continue

                seen = []
                for row in listing_rows(data):
                    if not row.get("id") or not row.get("price"):
                        continue
                    beds = row.get("bedrooms")
                    Listing.objects.update_or_create(
                        external_id=row["id"],
                        defaults={
                            "town": town,
                            "address": (row.get("formattedAddress") or "")[:300],
                            "zip_code": row.get("zipCode") or "",
                            "property_type": row.get("propertyType") or "",
                            "bedrooms": min(int(beds), 5) if beds is not None else None,
                            "bathrooms": row.get("bathrooms"),
                            "square_feet": row.get("squareFootage"),
                            "price": int(row["price"]),
                            "listed_date": parse_date(row.get("listedDate")),
                            "days_on_market": row.get("daysOnMarket"),
                            "status": row.get("status") or "",
                            "latitude": row.get("latitude"),
                            "longitude": row.get("longitude"),
                        },
                    )
                    seen.append(row["id"])
                # Listings that are no longer active get removed.
                Listing.objects.filter(town=town).exclude(external_id__in=seen).delete()
                listing_rows_saved += len(seen)
                self.stdout.write(f"{town}: {len(seen)} listings")

        DataImport.objects.create(
            source="rentcast",
            rows=rent_rows + listing_rows_saved,
            detail=f"{rent_rows} rent points, {listing_rows_saved} listings, {len(failures)} failed calls",
        )
        for f in failures:
            self.stdout.write(self.style.WARNING(f"Failed: {f}"))
        self.stdout.write(self.style.SUCCESS(
            f"Saved {rent_rows} rent points and {listing_rows_saved} listings. Calls left this month: {rentcast_calls_left()}."
        ))
