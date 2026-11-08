# RentCheck

**Is your college rent fair?** RentCheck tracks rent in college towns over time, shows it next to enrollment, and collects what students actually paid on past leases so the next student has something to compare against before signing.

INFO 490, Fall 2026, Team 19: Connor Slattery (cslat), Haaneol Kang (haaneol2).

## Features

| Feature | Status (first draft) | Owner |
|---|---|---|
| Town search and town page: rent trend by unit size next to enrollment | Working | Connor |
| Past lease form: logged-in students share what they paid (create, edit, delete) | Working | Connor |
| JSON API: `/api/towns/` and `/api/towns/<slug>/` | Working | Connor |
| Fair Rent Check: enter a listing, get low / fair / high with similar places (AI feature) | In progress | Haan |
| Compare Towns: up to 4 towns, chart, sortable table, CSV | In progress | Haan |

## Setup

Requires Python 3.11 or newer.

```bash
git clone <repo-url>
cd rentcheck
python -m venv .venv
.venv\Scripts\activate            # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # Mac/Linux: cp .env.example .env
python manage.py migrate
python manage.py seed_demo        # towns + placeholder numbers
python manage.py refresh_data     # real data from every API with a key in .env (Census needs none)
python manage.py createsuperuser  # optional, for /admin
python manage.py runserver
```

Open http://127.0.0.1:8000.

## Environment variables

Set in `.env` (never commit it). See `.env.example`.

| Name | What it does |
|---|---|
| `DJANGO_SECRET_KEY` | Django secret key. Required in production. |
| `DJANGO_DEBUG` | `True` for local work, `False` when deployed. |
| `DJANGO_ALLOWED_HOSTS` | Comma separated hosts, e.g. `127.0.0.1,localhost` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | The deployed site's URL, e.g. `https://name.pythonanywhere.com` |
| `RENTCAST_API_KEY` | RentCast key. `RENTCAST_MONTHLY_LIMIT` caps calls (default 45). |
| `HUD_API_TOKEN` | HUD Fair Market Rent API token. |
| `SCORECARD_API_KEY` | College Scorecard (api.data.gov) key. |
| `CENSUS_API_KEY` | Optional. Only needed if you hit the Census API's limit. |
| `GROQ_API_KEY` | For the AI features (not used yet). |

## Data

All free. Keys go in `.env` (see `.env.example`).

| Source | What we use | Sign up | Command |
|---|---|---|---|
| **Census Bureau, ACS 5-year** (B25031, B25003, B14001) | Median rent by bedroom count, 2015-2024; college students living in town | No key needed (optional key: https://api.census.gov/data/key_signup.html) | `fetch_census` |
| **HUD Fair Market Rents** | Rent by bedroom count for the county, or the campus ZIPs where HUD has ZIP-level numbers | https://www.huduser.gov/hudapi/public/register (pick Fair Market Rent) | `fetch_hud --years 2021-2027` |
| **College Scorecard** (Dept. of Education) | Official undergrad enrollment by year; the school's own off-campus room and board estimate | https://collegescorecard.ed.gov/data/api-documentation/ | `fetch_scorecard` |
| **RentCast** | Current median asking rent by bedroom (12 months of history) and up to 500 active listings per town | https://app.rentcast.io/app/api (free: 50 calls/month) | `fetch_rentcast` |
| **Zillow ZORI** (optional file) | Monthly typical asking rent, all sizes | Download the City ZORI CSV from https://www.zillow.com/research/data/ | `import_zori <file>` |
| **Students** | What they paid vs. the listed price, unit details | - | The past lease form |

Run everything that has a key:

```bash
python manage.py refresh_data                  # Census, HUD, Scorecard, RentCast
python manage.py refresh_data --skip-rentcast  # save RentCast's monthly calls
python manage.py fetch_rentcast --dry-run      # see how many RentCast calls a run would use
```

**RentCast limit.** The free plan is 50 calls a month. `fetch_rentcast` uses 2 calls per town (26 for all 13) and refuses to go past `RENTCAST_MONTHLY_LIMIT` (default 45). So run it about once a month. Every outside API call is logged in the `ApiCall` table (visible in /admin) without keys.

The towns we track are in `data/towns.csv`: names for each source, county, campus ZIPs, and the school's IPEDS ID. To add a town, add a row and run `python manage.py load_towns`. `fetch_scorecard` prints the school name it matched so a wrong ID is easy to spot.

`seed_demo` fills every town with **demo** numbers so the site works offline. Demo numbers are ignored as soon as a town has real data, and pages show a yellow warning while they're in use.

**How the numbers are picked** (`towns/stats.py`): the headline "typical rent" comes from the first source that has data in this order: Zillow, RentCast, Census, HUD. The town page also shows every source side by side, since they measure different things (asking rent vs. what renters pay vs. a government floor).

**Data quality:** lease reports under 40% or over 2.5x the town's typical rent are saved but left out of medians. Town medians stay hidden until 3 or more students report.

## How to use it

1. Search a town or school in the top bar, or pick one from the home page table.
2. On the town page, switch unit size to see rent for that size.
3. Sign up, then go to **My Leases** to share a past lease. You can edit or delete your own reports. Others only see a town's median, and only once 3 or more students have reported.

## API

```
GET /api/towns/?q=illinois
GET /api/towns/urbana-champaign/?bedrooms=2
```

Returns typical rent, change vs. a year ago, rent over time for each source, students by year, current listing count and median, and the lease report summary. Errors come back as JSON with a 400 or 404 status.

## Hosting

PythonAnywhere free tier. Steps are in `DEPLOY.md`.

## Tests

```bash
python manage.py test
```

## Project layout

```
rentcheck/   settings and root URLs
core/        home page, sign up
towns/       Town, RentPoint, EnrollmentPoint, Listing, ApiCall, DataImport models,
             town page, JSON API, API clients (clients.py), fetch_* commands
leases/      LeaseReport model, past lease form (login required)
checks/      Fair Rent Check (Haan)
compare/     Compare Towns (Haan)
templates/   base.html and shared includes
static/      CSS and Chart.js
data/        towns.csv (towns we track), enrollment template
docs/        first draft write-up (scope, AI plan, roadmap)
```

## AI

See `docs/FIRST_DRAFT.md` section 3 for the AI plan. A full `README_AI.md` comes with the final submission.
