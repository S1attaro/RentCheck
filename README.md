# RentCheck

**Is your college rent fair?** RentCheck shows how rent has changed in college towns, next to how many students live there. Students can also share what they actually paid on past leases, so the next student has something to compare against.

INFO 490, Fall 2026, Team 19: Connor Slattery (cslat), Haaneol Kang (haaneol2).

## Features

| Feature | Status | Owner |
|---|---|---|
| Town search and town pages (rent over time, enrollment) | Working | Connor |
| Past lease form (add, edit, delete your own) | Working | Connor |
| JSON API for towns | Working | Connor |
| Fair Rent Check (AI feature) | In progress | Haan |
| Compare Towns (chart, table, CSV) | In progress | Haan |

## Setup

You need Python 3.11 or newer.

```bash
git clone https://github.com/S1attaro/RentCheck.git
cd RentCheck
python -m venv .venv
.venv\Scripts\activate            # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # Mac/Linux: cp .env.example .env
python manage.py migrate
python manage.py seed_demo        # adds the towns with placeholder numbers
python manage.py refresh_data     # pulls real data (see "Data" below)
python manage.py runserver
```

Then open http://127.0.0.1:8000.

To use the admin page at /admin, run `python manage.py createsuperuser` first.

## Environment variables

These go in the `.env` file. Never commit `.env`, since it has API keys. `.env.example` shows the format.

| Name | What it's for |
|---|---|
| `DJANGO_SECRET_KEY` | Django's secret key. Needed when deployed. |
| `DJANGO_DEBUG` | `True` on your computer, `False` when deployed. |
| `DJANGO_ALLOWED_HOSTS` | Which sites can serve the app, like `127.0.0.1,localhost`. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | The deployed site's URL. |
| `HUD_API_TOKEN` | HUD rent data. |
| `SCORECARD_API_KEY` | College Scorecard enrollment data (from api.data.gov). |
| `RENTCAST_API_KEY` | RentCast listings. |
| `CENSUS_API_KEY` | Optional. Census works without it. |
| `GROQ_API_KEY` | For the AI feature (not used yet). |

## Data

All sources are free.

| Source | What we get | Sign up |
|---|---|---|
| Census Bureau | Rent by bedroom count (2015 to 2024) and college students living in each town | No key needed. Optional key: https://api.census.gov/data/key_signup.html |
| HUD | The government's fair rent by bedroom count for each county | https://www.huduser.gov/hudapi/public/register |
| College Scorecard | Enrollment at each school, and the school's own estimate of off-campus housing cost | https://collegescorecard.ed.gov/data/api-documentation/ |
| RentCast | Current listings and asking rents near campus | https://app.rentcast.io/app/api |
| Zillow (optional) | Monthly asking rents, as a downloaded file | https://www.zillow.com/research/data/ |
| Students | What they paid on past leases | The lease form on the site |

`python manage.py refresh_data` pulls from every source that has a key in `.env`.

A few things to know:
- **RentCast** only allows 50 free calls a month. A full run uses 26. The app stops before it goes over, and `python manage.py fetch_rentcast --dry-run` shows how many calls a run would use.
- **Towns** are listed in `data/towns.csv`. To add one, add a row and run `python manage.py load_towns`.
- **Placeholder numbers** from `seed_demo` are only used until real data is loaded. Pages show a yellow warning while they're in use.
- **Lease reports** that look like typos (way above or below the town's typical rent) are saved but left out of the averages. Town averages stay hidden until at least 3 students report.

## How to use it

1. Search for a town or school, or pick one from the home page.
2. On a town page, change the unit size to see rent for that size.
3. Sign up, then go to **My Leases** to share a past lease. Only you can see your own reports.

## API

```
GET /api/towns/?q=illinois
GET /api/towns/urbana-champaign/?bedrooms=2
```

Returns the town's typical rent, how much it changed in a year, rent over time from each source, enrollment, and the lease report totals.

## Hosting

We plan to host on PythonAnywhere's free plan. Steps are in `DEPLOY.md`.

## Tests

```bash
python manage.py test
```

## Project layout

```
rentcheck/   settings and main URLs
core/        home page and sign up
towns/       town data, town pages, the JSON API, and the data commands
leases/      the past lease form
checks/      Fair Rent Check (Haan)
compare/     Compare Towns (Haan)
templates/   shared page layout
static/      CSS and the chart library
data/        the list of towns we track
docs/        first draft write-up
```

## AI

The AI plan is in `docs/FIRST_DRAFT.md`, section 3. A full `README_AI.md` comes with the final submission.
