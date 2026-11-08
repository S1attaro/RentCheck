# P2-A3 First Draft: RentCheck

INFO 490, Fall 2026, Team 19. Connor Slattery (cslat), Haaneol Kang (haaneol2).

## 1. Updated product scope

**Startup.** RentCheck: "Is your college rent fair?"

**Problem.** Students sign leases months ahead, often for the first time. The asking price is usually the only number they see. Sites like Zillow show rent for a whole city, which doesn't help much in a town where most renters are students. What tenants actually pay is rarely public. A place that is $150 a month too high costs $1,800 over a one-year lease.

**Target users.** College students looking for off-campus housing in college towns like Urbana-Champaign, Bloomington, Madison, and Ann Arbor. Parents who help pay rent are a second group.

**Core value.** A fair price to compare against before signing.

**Three core features**
1. **Town page.** Rent over time by unit size, shown next to enrollment.
2. **Fair Rent Check (AI feature).** Enter a listing and get a low, fair, or high rating with similar places.
3. **Past lease reports.** Logged-in students share what they paid. Others only see town totals, and only after 3 or more reports.

Compare Towns (up to 4 towns, chart, table, CSV) stays as a fourth, smaller feature.

**Changes from P2-A2**
- **Home page.** The wireframe had a map marked "(?)". We replaced it with a table of towns and their typical rent. It's easier to compare and doesn't need a map API.
- **Data.** All four sources from P2-A2 are now in the app. Census, HUD, and RentCast come in through their free APIs. Zillow is a free file we download and import. We also added College Scorecard for official enrollment.
- **Enrollment.** The town page shows two numbers: students enrolled at the school, and college students living in town. The second one is the group actually renting.
- **Towns.** We track 13 college towns instead of a few.
- **Lease form.** It now asks if the rent was per bed, since a lot of student housing is priced that way. It also asks for property type, lease length, and a few optional details. The AI model will use these.
- **Listing Reader.** A new page where you paste a listing and AI pulls out the details. It was added as a working AI prototype (section 3b).

## 2. What works now

The repo is a Django project with six apps: `core`, `towns`, `leases`, `reader`, `checks`, and `compare`.

- **Models.** 7 models. `RentPoint`, `EnrollmentPoint`, and `Listing` each link to `Town`. `LeaseReport` links to `Town` and to the user.
- **Main workflow.** A student signs up, fills out the past lease form, and saves it. It shows up on their My Leases page, where they can edit or delete it. Once a town has 3 reports, the town page shows the median.
- **Views and templates.** Function-based views for the town pages and API. Class-based views for the lease pages. Every page extends `base.html`.
- **Login.** Sign up, log in, and log out work. Lease pages need a login. Users can only see and change their own reports.
- **Internal API.** `/api/towns/` and `/api/towns/<slug>/` return JSON. The town page charts load from it.
- **Outside APIs.** Commands pull data from Census, HUD, College Scorecard, and RentCast and save it to the database. One command, `refresh_data`, runs them all. RentCast's free plan is 50 calls a month, so the app stops before it hits the limit.
- **Data features.** Town search, rent charts from every source, a table comparing the sources, and enrollment charts.
- **Data quality.** Demo numbers are only used until real data is loaded. Lease reports that look like typos (way off the town's typical rent) are kept but left out of the averages.
- **Listing Reader (AI prototype).** Working. See section 3b.
- **Tests.** 68 tests, all passing.
- **Live data.** We ran Census, HUD, and College Scorecard for all 13 towns on Nov 8. All 13 schools matched. RentCast is set up and waiting on its key.

Fair Rent Check and Compare Towns have their pages and links set up. Haan is building them.

## 3. AI plan

The AI has two parts. The Listing Reader works now. The rent range model is next.

### 3a. Rent range model (main feature)

**What it does.** Predicts a fair price range for a listing. Then it rates the asking price low, fair, or high.

**Input.** Town, bedrooms, bathrooms, square feet, ZIP code, and whether the rent is per bed. Users fill these in on the form, or paste a listing and let the Listing Reader fill them in.

**Output.** A low and high price, a rating, and the 5 most similar places.

**Model.** A gradient boosting model from scikit-learn. We train two versions: one predicts the low end of the range and one predicts the high end. It learns from current listings, rent by town and bedroom count, and the leases students submit.

**Why this model.** Our data is a small table. This model runs on a normal CPU in milliseconds, costs nothing to host, and is easy to explain. A range is more honest than one "fair price." An LLM isn't a good fit for predicting a number from a table.

**How it works in Django.** The user fills out the form. The view checks the input. It adds the town's typical rent from our database. The model predicts the range. The result is saved and shown with similar places.

**If something goes wrong.** If the model fails, the app uses a simple rule instead (within 10% of typical rent counts as fair) and says so on the page. If a town has no data, it says "not enough data" instead of guessing.

**How we'll test it.** We'll hold back some recent listings and leases and check how often the real price lands inside the predicted range. We'll compare it to the simple 10% rule. The final submission will have the 5-test table.

### 3b. Listing Reader (working prototype)

**What it does.** The user pastes a listing's text from Apartments.com, Facebook, Zillow, or a landlord email. An LLM pulls out the town, bedrooms, bathrooms, rent, square feet, and whether it's per bed, furnished, or has utilities included. Then the page compares the rent to the town's typical rent for that size. It's at `/read-listing/`, and there's a JSON version at `/read-listing/api/` that the Fair Rent Check can use later.

**Model.** `openai/gpt-oss-20b` through the Groq API, which we used in Project 1. We planned on Llama 3.1 8B, but Groq shut that model down in August 2026 and lists gpt-oss-20b as the replacement. It's fast and cheap, and pulling details out of short text is an easy job for it. The model name is a setting, so it's easy to swap.

**How it works.**
1. The user pastes the whole page. Links alone are rejected with a message asking for the text.
2. Menus, short junk lines, and sections like "Nearby apartments" are removed, so other buildings' details don't get mixed in.
3. Phone numbers and emails are removed, and the first 3,000 characters are sent to Groq with instructions to reply in JSON.
4. Every value is checked. Numbers have to be in a normal range, and the rent and square feet have to actually appear in the listing, so a made-up number gets thrown out.
5. Anything the AI missed is filled in by a basic reader that uses plain text matching. The town is matched to one of our 13 towns.
6. Extras like pets, parking, lease length, and amenities are found with plain text matching, so the AI can't make them up.

**If something goes wrong.** If Groq is down, out of calls, or there's no key, the basic reader does the whole job and the page says so. If the reply isn't clean JSON, we pull the JSON out of it. Each visitor can use it 20 times an hour so nobody burns through our API calls. Nothing pasted is saved.

**Status.** Working. Tested live on a real Zillow listing on Nov 8 (correct rent range, beds, bath, and size, in about 0.3 seconds), and with 22 tests using fake Groq replies. We still need to run the 5 real listing tests for the final evaluation table.

### What's built so far

- **Listing Reader:** working (section 3b).
- **Rent range model:** the data it needs is in place. That includes rent by town and size from four sources, enrollment, current listings (once RentCast is on), and the details from the lease form.

## 4. Roadmap

| Task | Current status | Responsible member | Expected completion |
|---|---|---|---|
| Django core features | Town page, search, login, and lease form done. Fair Rent Check version 1 next, then Compare Towns. | Connor (town page, leases), Haan (Fair Rent Check, Compare Towns) | Fair Rent Check v1: Nov 16. Compare Towns: Nov 23 |
| Database and APIs | Models, internal API, and outside API commands done. Census, HUD, and Scorecard loaded. RentCast next. | Connor (data, API), Haan (`RentCheck` table for saved checks) | Nov 16 |
| AI integration | Listing Reader prototype working. Rent range model planned. | Haan (rent model), Connor (listing reader) | Nov 30 |
| Evaluation and testing | 68 tests pass. AI testing, failure cases, and one improvement still to do. | Both | Dec 4 |
| Deployment | Settings and setup guide done (`DEPLOY.md`). Deploy to PythonAnywhere. | Connor | Nov 30 |
| Documentation | README done. AI docs, cost comparison, and scaling notes to do. | Both | Dec 7 |
