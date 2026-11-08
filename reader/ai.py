"""Listing Reader: pull the details out of a pasted rental listing.

Steps:
  1. Trim the pasted page: drop menus, junk lines, and "nearby listings" sections.
  2. Remove phone numbers and emails, then keep the first MAX_CHARS characters.
  3. Send that to the Groq AI model and get JSON back.
  4. Check every value. A number has to appear in the listing or it is thrown out.
  5. Fill any gaps with the backup parser and match the town.
  6. Find extras (pets, parking, amenities) with plain text matching.

If Groq is down, out of calls, or has no key, the backup parser (plain text matching)
does the whole job, so the page always works.
"""

import json
import logging
import re
import time

from django.conf import settings

from towns.clients import ApiError, post_json
from towns.models import Town

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
MAX_PASTE = 50000  # how much someone can paste (a whole page is fine)
MAX_CHARS = 3000   # how much we send to the AI (less text = faster answer)

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """You read rental listings and pull out the details.
Reply with one JSON object and nothing else. Use exactly these keys:
city, state, bedrooms, bathrooms, monthly_rent, max_rent, rent_is_per_bed, utilities_included, square_feet, furnished

Rules:
- Only describe the main listing. Ignore any nearby, similar, or recommended listings.
- If one specific unit is described (like "Unit 1107-A22, 2 beds, 1 bath, $1,080, 850 sqft"), use that unit's details.
- monthly_rent: the monthly rent in dollars as a number, like 1200. If a range is given, use the lowest price.
- max_rent: the highest price if a range is given, otherwise null.
- bedrooms: a whole number. A studio is 0.
- rent_is_per_bed: true if the price is per person, per bed, or per room. Otherwise false.
- utilities_included and furnished: true or false.
- state: the 2 letter code, like IL.
- If the listing doesn't say something, use null. Don't guess."""


# ---------- cleaning ----------

PHONE = re.compile(r"(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


# Lines worth keeping when someone pastes a whole web page.
USEFUL_LINE = re.compile(
    r"\$|\d\s*-?\s*(bd|beds?|br|bedrooms?|ba|baths?|bathrooms?)\b|sq\.?\s?ft|sqft|square feet|studio|"
    r"utilit|furnish|per (person|bed|room)|lease|deposit|available|rent",
    re.I,
)


# Sections of a listing page that are about other places. Skipped until a useful section starts again.
SKIP_SECTION = re.compile(
    r"^(nearby (apartments|homes|rentals|places|schools|cities)|similar (apartments|homes|rentals|listings)|"
    r"other (units|listings) nearby|you may also like|recommended|frequently asked questions|getting around|"
    r"living in |areas of interest|highlights$|neighborhood:|travel times|more school details)",
    re.I,
)
# Whole-line headings only, so a line like "Fees may apply" under a nearby listing doesn't count.
KEEP_SECTION = re.compile(
    r"^(cost calculator|monthly costs|facts, features.*|unit features|policies|lease terms|"
    r"fees( and charges)?|utilities( included)?|pet policy|back to listing|about the unit|floorplan|"
    r"floor plan.*|unit [a-z0-9-]+)$",
    re.I,
)


def drop_other_listings(lines):
    """Remove sections like "Nearby apartments" so the AI doesn't mix in another building's details."""
    kept, skipping = [], False
    for line in lines:
        if SKIP_SECTION.match(line):
            skipping = True
            continue
        if KEEP_SECTION.match(line):
            skipping = False
        if not skipping:
            kept.append(line)
    return kept


def trim_page(text):
    """Drop menu items and other short junk lines from a pasted web page.

    Keeps lines with prices, beds, baths, size, utilities, and any real sentence (6+ words).
    If it's still too long, keep the part around the first price.
    """
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    if len(text) <= MAX_CHARS and len(lines) < 40:
        return text.strip()
    lines = drop_other_listings(lines)
    useful = [line for line in lines if USEFUL_LINE.search(line) or len(line.split()) >= 6]
    trimmed = "\n".join(useful) or text
    if len(trimmed) > MAX_CHARS:
        first_price = max(trimmed.find("$"), 0)
        start = max(first_price - 500, 0)
        trimmed = trimmed[start:start + MAX_CHARS]
    return trimmed


def clean_text(text):
    """Trim page junk, cut to MAX_CHARS, and remove phone numbers and emails before anything leaves the server."""
    text = trim_page((text or "")[:MAX_PASTE])[:MAX_CHARS]
    text = EMAIL.sub("[email removed]", text)
    text = PHONE.sub("[phone removed]", text)
    return text


# ---------- backup parser (no AI) ----------

def backup_extract(text):
    """Find the common patterns with plain text matching. Used when Groq isn't available."""
    lower = text.lower()
    out = {}

    rent = re.search(r"\$\s?(\d{1,2},?\d{3}|\d{3,4})(?:\.00)?", text)
    if rent:
        out["monthly_rent"] = int(rent.group(1).replace(",", ""))
    price_range = re.search(r"\$\s?([\d,]{3,6})\s*(?:-|to|\u2013)\s*\$\s?([\d,]{3,6})", text)
    if price_range:
        out["monthly_rent"] = int(price_range.group(1).replace(",", ""))
        out["max_rent"] = int(price_range.group(2).replace(",", ""))

    if re.search(r"\bstudio\b", lower):
        out["bedrooms"] = 0
    beds = re.search(r"(\d)\s*-?\s*(?:bed(?:room)?s?|br|bd)\b", lower)
    if beds:
        out["bedrooms"] = int(beds.group(1))

    baths = re.search(r"(?<![\d.])(\d(?:\.\d)?)\s*-?\s*(?:bath(?:room)?s?|ba)\b", lower)
    if baths:
        out["bathrooms"] = float(baths.group(1))

    sqft = re.search(r"(\d{1,2},?\d{3}|\d{3})\s*(?:sq\.?\s?ft|sqft|sf|square feet)", lower)
    if sqft:
        out["square_feet"] = int(sqft.group(1).replace(",", ""))

    out["rent_is_per_bed"] = bool(re.search(r"per (person|bed|room|tenant)|/\s?(person|bed|room)|by the bed", lower))

    if re.search(r"utilities (are )?not included|plus utilities|\+ ?utilities|tenant pays (all )?utilities", lower):
        out["utilities_included"] = False
    elif re.search(r"utilities (are )?included|all utilities|utilities paid|includes (all )?utilities", lower):
        out["utilities_included"] = True

    if re.search(r"\bunfurnished\b", lower):
        out["furnished"] = False
    elif re.search(r"\bfurnished\b", lower):
        out["furnished"] = True
    return out


# ---------- extra details (no AI, so nothing can be made up) ----------

AMENITIES = [
    ("dishwasher", "Dishwasher"),
    ("air condition", "Air conditioning"),
    ("central air", "Air conditioning"),
    ("in-unit laundry", "Laundry in unit"),
    ("washer/dryer in unit", "Laundry in unit"),
    ("in unit washer", "Laundry in unit"),
    ("laundry on site", "Laundry on site"),
    ("on-site laundry", "Laundry on site"),
    ("fitness center", "Fitness center"),
    ("gym", "Gym"),
    ("pool", "Pool"),
    ("balcony", "Balcony"),
    ("patio", "Patio"),
    ("bike", "Bike storage"),
    ("package", "Package service"),
    ("on-site maintenance", "On-site maintenance"),
    ("study room", "Study room"),
    ("elevator", "Elevator"),
]


def line_after(lines, heading):
    """The first line after a heading like "Lease terms" or "Parking"."""
    for i, line in enumerate(lines[:-1]):
        if line.lower() == heading:
            return lines[i + 1]
    return None


def extra_details(text):
    """Pets, units, lease length, parking, and amenities, found by plain text matching."""
    lines = drop_other_listings([line.strip() for line in (text or "").splitlines() if line.strip()])
    page = "\n".join(lines)
    lower = page.lower()
    out = {}

    if re.search(r"no pets|pets not allowed", lower):
        out["pets"] = "Not allowed"
    elif re.search(r"pet[- ]friendly|pets allowed|dogs\s*status:\s*allowed|cats\s*status:\s*allowed|dogs allowed|cats allowed", lower):
        out["pets"] = "Allowed"

    units = re.search(r"(\d+) units? available", lower)
    if units:
        out["units_available"] = int(units.group(1))

    lease = line_after(lines, "lease terms") or line_after(lines, "lease length")
    if lease and len(lease) <= 40:
        out["lease_terms"] = lease
    else:
        months = re.search(r"(\d{1,2})[- ]month lease", lower)
        if months:
            out["lease_terms"] = f"{months.group(1)} months"

    parking = line_after(lines, "parking")
    if parking and len(parking) <= 40:
        out["parking"] = parking
    elif re.search(r"garage|off-street parking|parking included|covered parking", lower):
        out["parking"] = "Available"

    found = []
    for key, label in AMENITIES:
        if re.search(r"\b" + re.escape(key), lower) and label not in found:
            found.append(label)
    if found:
        out["amenities"] = found[:8]
    return out


# ---------- Groq ----------

def parse_model_json(content):
    """The model should return pure JSON, but pull out the {...} part if it adds anything around it."""
    try:
        return json.loads(content)
    except (TypeError, json.JSONDecodeError):
        match = re.search(r"\{.*\}", content or "", re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return None


def groq_extract(text):
    """Ask the LLM for the details. Returns a dict, or raises ApiError."""
    body = {
        "model": settings.GROQ_MODEL,
        "temperature": 0,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}],
        "response_format": {"type": "json_object"},
    }
    if "gpt-oss" in settings.GROQ_MODEL:
        body["reasoning_effort"] = "low"  # this is an easy task, so keep the model's thinking short (faster)
    headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}"}
    try:
        data = post_json("groq", GROQ_URL, body, headers=headers)
    except ApiError as e:
        if e.status != 400:
            raise
        # Some models don't support these options. Try once more without them.
        body.pop("response_format", None)
        body.pop("reasoning_effort", None)
        data = post_json("groq", GROQ_URL, body, headers=headers)

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ApiError("groq returned an unexpected response")
    parsed = parse_model_json(content)
    if not isinstance(parsed, dict):
        raise ApiError("groq did not return JSON")
    return parsed


# ---------- checking the values ----------

def to_number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "yes"):
        return True
    if isinstance(value, str) and value.strip().lower() in ("false", "no"):
        return False
    return None


def number_in_text(number, text):
    """Make sure the model didn't make up a number: it has to appear in the listing."""
    n = int(number)
    digits = re.sub(r"[,\s]", "", text)
    return str(n) in digits


def match_town(city, state, text):
    """Match a city name (or the listing text) to one of our towns."""
    towns = list(Town.objects.all())

    def names(t):
        found = {t.name.lower(), t.university.lower()}
        found |= {n.strip().lower() for n in t.zillow_names.split(",") if n.strip()}
        found |= {n.replace(" city", "").replace(" borough", "").strip().lower()
                  for n in t.census_places.split(",") if n.strip()}
        return found

    if city:
        city_l = str(city).lower().strip()
        for t in towns:
            if (not state or str(state).upper() == t.state) and city_l in names(t):
                return t
    # Fall back to looking for any of our town names in the text itself.
    lower = text.lower()
    for t in towns:
        for n in sorted(names(t), key=len, reverse=True):
            if len(n) > 4 and re.search(r"\b" + re.escape(n) + r"\b", lower):
                return t
    return None


def check_values(raw, text):
    """Keep only values that make sense. Returns (fields, warnings)."""
    fields, warnings = {}, []

    rent = to_number(raw.get("monthly_rent"))
    if rent is not None:
        if not 100 <= rent <= 10000:
            warnings.append("The rent found was outside $100 to $10,000, so it was ignored.")
        elif not number_in_text(rent, text):
            warnings.append("The AI gave a rent that isn't in the listing, so it was ignored.")
        else:
            fields["monthly_rent"] = int(rent)

    max_rent = to_number(raw.get("max_rent"))
    if max_rent is not None and "monthly_rent" in fields:
        if fields["monthly_rent"] < max_rent <= 10000 and number_in_text(max_rent, text):
            fields["max_rent"] = int(max_rent)

    beds = to_number(raw.get("bedrooms"))
    if beds is not None and beds == int(beds) and 0 <= beds <= 10:
        fields["bedrooms"] = min(int(beds), 5)

    baths = to_number(raw.get("bathrooms"))
    if baths is not None and 0.5 <= baths <= 10:
        fields["bathrooms"] = baths

    sqft = to_number(raw.get("square_feet"))
    if sqft is not None:
        if 100 <= sqft <= 10000 and number_in_text(sqft, text):
            fields["square_feet"] = int(sqft)
        else:
            warnings.append("The square feet found didn't look right, so it was ignored.")

    for key in ("rent_is_per_bed", "utilities_included", "furnished"):
        value = to_bool(raw.get(key))
        if value is not None:
            fields[key] = value
    return fields, warnings


# ---------- main entry point ----------

def read_listing(text):
    """Read one listing.

    Returns {"fields", "town", "method", "warnings", "cleaned_text", "seconds", "extras"}.
    method is "ai" if Groq answered, or "backup" if the plain text parser did the work.
    """
    cleaned = clean_text(text)
    warnings = []
    method = "backup"
    raw = {}

    started = time.perf_counter()
    if settings.GROQ_API_KEY:
        try:
            raw = groq_extract(cleaned)
            method = "ai"
        except ApiError as e:
            log.warning("Groq failed: %s", e)
            warnings.append("The AI reader isn't working right now, so the basic reader was used.")
    else:
        warnings.append("No AI key is set, so the basic reader was used.")

    if method == "ai":
        fields, value_warnings = check_values(raw, cleaned)
        warnings += value_warnings
        # Fill anything the AI missed with the backup parser.
        backup, _ = check_values(backup_extract(cleaned), cleaned)
        filled = [k for k in backup if k not in fields]
        for k in filled:
            fields[k] = backup[k]
        if "monthly_rent" in filled:
            warnings.append("The AI missed the rent, so the basic reader filled it in.")
    else:
        fields, value_warnings = check_values(backup_extract(cleaned), cleaned)
        warnings += value_warnings

    town = match_town(raw.get("city"), raw.get("state"), cleaned)
    if town is None:
        town = match_town(None, None, (text or "")[:MAX_PASTE])
    if town is None:
        warnings.append("Couldn't tell which town this is. Pick it in the Town box and read it again.")
    if "monthly_rent" not in fields:
        warnings.append("Couldn't find the monthly rent. Check the listing for a price.")

    seconds = round(time.perf_counter() - started, 1)
    extras = extra_details(EMAIL.sub("", PHONE.sub("", (text or "")[:MAX_PASTE])))
    return {"fields": fields, "town": town, "method": method, "warnings": warnings,
            "cleaned_text": cleaned, "seconds": seconds, "extras": extras}
