# P2-A3 First Draft: RentCheck

INFO 490, Fall 2026, Team 19. Connor Slattery (cslat), Haaneol Kang (haaneol2).

## 1. Updated product scope

**Startup.** RentCheck: "Is your college rent fair?"

**Problem.** Students sign leases months ahead, often for the first time, and the asking price is usually the only number they see. Sites like Zillow report rent for a whole city, which doesn't help much in a town where most renters are students. What tenants actually pay is rarely public. A place that is $150 a month too high costs $1,800 over a one-year lease.

**Target users.** College students looking for off-campus housing, mainly in Big Ten type college towns (Urbana-Champaign, Bloomington, Madison, Ann Arbor, Iowa City, State College, West Lafayette). Parents helping pay rent are a second group.

**Core value.** A fair price to compare against before signing: rent trends for the town and unit size, enrollment next to it, and what students really paid.

**Three core features**
1. **Town page.** Rent over time by unit size next to enrollment, plus typical rent, change vs. a year ago, and what students reported paying.
2. **Fair Rent Check (AI feature).** Enter a listing and get a low / fair / high rating with an expected price range and similar places.
3. **Past lease reports.** Logged-in students share what they paid and what the listing said. Only town-level medians are shown, and only after 3 or more reports.

Compare Towns (up to 4 towns, chart, sortable table, CSV) stays as a fourth, smaller feature.

**Changes from P2-A2**
- Home page: the wireframe had a map marked "(?)". We replaced it with a table of college towns showing typical rent and yearly change. It's more useful for comparing and doesn't need a map API.
- Lease form: added a "rent was per person (per bed)" checkbox. A lot of student housing is priced per bed, and mixing the two would wreck the averages.
- Privacy rule: lease report numbers stay hidden until a town and size has 3 or more reports, so one student's lease can't be picked out.
- Data: all four sources from P2-A2 are now hooked up through their free APIs: Census (rent by bedroom count, 2015-2024), HUD Fair Market Rents (by bedroom, county or campus ZIP), RentCast (current asking rents and active listings), and Zillow (optional file). We added College Scorecard for official enrollment and each school's own off-campus cost estimate. The town page shows all sources side by side because they measure different things.
- Students: the town page shows both students enrolled at the school (College Scorecard) and college students living in town (Census), since the second is the group actually renting there.
- Towns: 13 college towns instead of a few, listed in `data/towns.csv`.
- Lease form: also collects property type, lease length, furnished, square feet, and walk time to campus. These are the features the fair rent model needs to find similar places.

## 2. What works now

Repo: Django project `rentcheck` with five apps (`core`, `towns`, `leases`, `checks`, `compare`).

- **Models (7, with relationships):** `Town`; `RentPoint`, `EnrollmentPoint`, `Listing` (each FK to Town); `LeaseReport` (FK to Town and User); `ApiCall` and `DataImport` (logs of outside API calls and data refreshes).
- **Database-backed workflow:** Sign up → Share a past lease (form with validation) → saved to `LeaseReport` → shows up in My Leases (edit, delete) → counts toward the town page's "what students reported paying" once 3 reports exist.
- **Views and templates:** function-based views (home, town list, town detail, API) and class-based views (lease create, list, update, delete). All pages extend `base.html`; shared includes for forms and the town table.
- **Auth:** sign up, log in, log out. Lease pages require login. Users can only see and change their own reports; anyone else gets a 404.
- **API:** internal JSON API at `/api/towns/` and `/api/towns/<slug>/`. The town page charts load their data from it.
- **Data features:** town search, rent stats (median, yearly change), Chart.js charts.
- **External APIs (4):** `fetch_census`, `fetch_hud`, `fetch_scorecard`, and `fetch_rentcast` pull from the Census, HUD, College Scorecard, and RentCast APIs and save to the database. `refresh_data` runs all that have keys. All calls go through one client (`towns/clients.py`) that logs every call without keys. RentCast's free plan is 50 calls a month, so the app plans 2 calls per town, has a `--dry-run`, and refuses to pass a set limit.
- **Data features:** town search; a town page with rent over time from every source on one chart, a side-by-side source table, students enrolled vs. living in town, the school's own off-campus cost, and current listings; rent stats (median, yearly change).
- **Data quality:** demo data is ignored once real data exists; lease reports far from the town's typical rent are flagged and left out of medians; per-bed rents are converted to whole-unit rents before comparing.
- **Tests:** 41 tests, all passing. They cover stats and source priority; each API command against fake responses in that API's documented format (including missing values, API failures, missing keys, and the RentCast monthly limit); that keys never get logged; search; the JSON API; form validation; outlier flagging; login; and per-user access.
- **Note:** the live API runs happen on our own machines (the development sandbox could not reach them). The commands print what they saved and what failed.

Fair Rent Check and Compare Towns are wired in (URLs, nav, placeholder pages) and are being built by Haan.

## 3. AI plan

The AI feature lives inside Fair Rent Check. It has two parts.

### 3a. Expected rent model (main feature)

**What it does.** Predicts a fair price range for a listing, then rates the asking price low, fair, or high.

**Input.** Town, bedrooms, per person or whole unit, utilities included, month. Later: square feet and distance to campus if RentCast listings are added.

**Output.** Expected low and high (25th and 75th percentile), a rating, and the 5 most similar known places.

**Model.** Gradient boosted trees with quantile loss (scikit-learn `HistGradientBoostingRegressor(loss="quantile")`), one model for the 25th and one for the 75th percentile. Training data: current RentCast listings with bedrooms, bathrooms, square feet, property type, and ZIP (`Listing`); rent by bedroom count from Census, HUD, and RentCast (`RentPoint`); and student lease reports with property type, lease length, furnished, size, and walk time (`LeaseReport`).

**Why this model.** Small tabular data, runs on a CPU in milliseconds, free to host, and easy to explain. A quantile range is more honest than a single "fair price" number. An LLM is a poor fit for predicting a number from a table.

**Workflow.**
User fills form → Django view validates it → features built from the form + `towns.stats` (typical rent, yearly change) → model predicts low/high → rating = where the price falls → saved as a `RentCheck` row → result page with range, rating, similar places.

**Validation and fallbacks.** If the model file is missing or errors, fall back to the simple rule (within 10% of typical rent = fair) and say so on the page. If a town has no data, return "unknown" instead of guessing. Predictions outside a sane range (under $100 or over 3x typical rent) are thrown out.

**How we'll test it.** Hold out the most recent months and some lease reports. Measure how often real prices land inside the predicted range (target about 50%) and mean absolute error of the midpoint. Compare against the simple 10% rule as a baseline. Five realistic listing tests go in the final evaluation table.

### 3b. Listing text parser (add-on)

**What it does.** The user pastes listing text (from Apartments.com, Facebook Marketplace, a landlord email). An LLM pulls out town, bedrooms, rent, per person or not, and utilities as JSON and fills in the check form.

**Model.** Llama 3.1 8B through the Groq API (we used Groq in Project 1). Fast and cheap, and pulling fields out of short text is a task small models do well.

**Validation.** The JSON goes through the same Django form as manual input, so bad or made-up values get caught. If the API fails or the key is missing, the user just fills the form by hand. Addresses and names are not saved.

**Status.** Planned, not started. The rent model comes first.

### Evidence so far

The data side the model needs is built and tested: the Census pipeline (`fetch_census`), rent series by town and size, typical rent and yearly change (`towns/stats.py`), and lease reports with per-person normalization and outlier flags (`leases/models.py`). The lease form already collects the model's features. Model training starts once enough real data is loaded.

## 4. Roadmap

| Task | Current status | Responsible member | Expected completion |
|---|---|---|---|
| Django core features | Town page, search, login, lease form (full CRUD) done. Fair Rent Check and Compare Towns pages are placeholders. | Connor (town page, leases); Haan (Fair Rent Check, Compare Towns) | Nov 23 |
| Database and APIs | 7 models + migrations, JSON API, Census/HUD/Scorecard/RentCast commands done. Run them live with our keys and check results. Add RentCheck model. | Connor (data, API); Haan (RentCheck model) | Nov 16 |
| AI integration | Planned (section 3). Rent model, then listing parser. | Haan (rent model); Connor (listing parser) | Nov 30 |
| Evaluation and testing | 41 unit tests pass. AI evaluation, 5 test table, failure analysis, one improvement still to do. | Both | Dec 4 |
| Deployment | Production settings and step-by-step guide (`DEPLOY.md`) done. Deploy to PythonAnywhere free tier (allows Census and Groq API calls, keeps SQLite between restarts). | Connor | Nov 30 |
| Documentation | README done. README_AI, cost comparison, scaling notes to do. | Both | Dec 7 |
