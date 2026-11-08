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
- **Data.** All four sources from P2-A2 are now connected through free APIs: Census, HUD, RentCast, and Zillow. We also added College Scorecard for official enrollment.
- **Enrollment.** The town page shows two numbers: students enrolled at the school, and college students living in town. The second one is the group actually renting.
- **Towns.** We track 13 college towns instead of a few.
- **Lease form.** It now asks if the rent was per bed, since a lot of student housing is priced that way. It also asks for property type, lease length, and a few optional details. The AI model will use these.

## 2. What works now

The repo is a Django project with five apps: `core`, `towns`, `leases`, `checks`, and `compare`. There are 7 models. `RentPoint`, `EnrollmentPoint`, and `Listing` each link to `Town`, and `LeaseReport` links to both `Town` and the user.

The main workflow is the past lease form. A student signs up, fills out the form, and saves it. It shows up on their My Leases page, where they can edit or delete it. Lease pages need a login, and users can only see and change their own reports. Once a town has 3 reports, the town page shows the median.

The town pages use function-based views and the lease pages use class-based views. Every page extends `base.html`. We also have an internal JSON API at `/api/towns/`, and the town page charts load their data from it.

For outside data, we wrote commands that pull from Census, HUD, College Scorecard, and RentCast and save it to the database. `refresh_data` runs all of them. RentCast's free plan only allows 50 calls a month, so the app stops before it hits that. On Nov 8 we ran Census, HUD, and College Scorecard for all 13 towns, and all 13 schools matched. RentCast is set up and waiting on its key.

The town page has search, rent charts from each source, a table comparing the sources, and enrollment charts. Demo numbers are only used until real data is loaded. Lease reports that look like typos are kept but left out of the averages. There are 46 tests and they all pass.

Fair Rent Check and Compare Towns have their pages and links set up. Haan is building them.

## 3. AI plan

The AI feature is inside Fair Rent Check. It has two parts.

### 3a. Rent range model (main feature)

**What it does.** Predicts a fair price range for a listing. Then it rates the asking price low, fair, or high.

**Input.** Town, bedrooms, per bed or whole unit, utilities included, and month. Later: square feet and distance to campus.

**Output.** A low and high price, a rating, and the 5 most similar places.

**Model.** A gradient boosting model from scikit-learn. We train two versions: one predicts the low end of the range and one predicts the high end. It learns from current listings, rent by town and bedroom count, and the leases students submit.

**Why this model.** Our data is a small table. This model runs on a normal CPU in milliseconds, costs nothing to host, and is easy to explain. A range is more honest than one "fair price." An LLM isn't a good fit for predicting a number from a table.

**How it works in Django.** The user fills out the form. The view checks the input. It adds the town's typical rent from our database. The model predicts the range. The result is saved and shown with similar places.

**If something goes wrong.** If the model fails, the app uses a simple rule instead (within 10% of typical rent counts as fair) and says so on the page. If a town has no data, it says "not enough data" instead of guessing.

**How we'll test it.** We'll hold back some recent listings and leases and check how often the real price lands inside the predicted range. We'll compare it to the simple 10% rule. The final submission will have the 5-test table.

### 3b. Listing text reader (add-on)

**What it does.** The user pastes a listing's text. An LLM pulls out the town, bedrooms, rent, and utilities and fills in the form for them.

**Model.** Llama 3.1 8B through the Groq API, which we used in Project 1. It's fast, cheap, and good at pulling details out of short text.

**Safety.** The LLM's output goes through the same form checks as typed input, so bad values get caught. If Groq is down, the user just types it in. Addresses and names are never saved.

**Status.** Planned. The rent model comes first.

### What's built so far

The data the model needs is already in place. We have rent by town and size from four sources, enrollment, current listings (once RentCast is on), and the lease form collects the details the model will use.

## 4. Roadmap

| Task | Current status | Responsible member | Expected completion |
|---|---|---|---|
| Django core features | Town page, search, login, and lease form done. Fair Rent Check and Compare Towns pages are placeholders. | Connor (town page, leases), Haan (Fair Rent Check, Compare Towns) | Nov 23 |
| Database and APIs | Models, internal API, and outside API commands done. Census, HUD, and Scorecard loaded. RentCast next. | Connor (data, API), Haan (Fair Rent Check model) | Nov 16 |
| AI integration | Planned (section 3). Rent model first, then listing reader. | Haan (rent model), Connor (listing reader) | Nov 30 |
| Evaluation and testing | 46 tests pass. AI testing, failure cases, and one improvement still to do. | Both | Dec 4 |
| Deployment | Settings and setup guide done (`DEPLOY.md`). Deploy to PythonAnywhere. | Connor | Nov 30 |
| Documentation | README done. AI docs, cost comparison, and scaling notes to do. | Both | Dec 7 |
