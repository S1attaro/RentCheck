# Deploying RentCheck on PythonAnywhere (free)

Why PythonAnywhere:
- Free, and SQLite works because the disk is kept between restarts. Render's free plan wipes local files, so we'd need their free Postgres, which is deleted after 30 days.
- Free accounts can only reach allowlisted sites. `api.census.gov`, `api.rentcast.io`, and `api.groq.com` are on the list. HUD and College Scorecard may not be, so run those on your own computer and copy the data up (step 3b).
- Limits to know: one web app, 512 MB disk, and the free app expires after a month unless you log in and click "Run until 1 month from today" on the Web tab. New free accounts don't get scheduled tasks, so run data refreshes by hand.

Deploy in the last week of November so it stays up through grading.

## Steps

1. Sign up at https://www.pythonanywhere.com (Beginner, free). Your site will be `https://<username>.pythonanywhere.com`.
2. Open a **Bash console** and run:
   ```bash
   git clone https://github.com/<you>/<repo>.git rentcheck
   cd rentcheck
   mkvirtualenv rentcheck --python=python3.12
   pip install -r requirements.txt
   cp .env.example .env
   nano .env
   ```
   Fill in `.env`:
   ```
   DJANGO_SECRET_KEY=<run: python -c "import secrets; print(secrets.token_urlsafe(50))">
   DJANGO_DEBUG=False
   DJANGO_ALLOWED_HOSTS=<username>.pythonanywhere.com
   DJANGO_CSRF_TRUSTED_ORIGINS=https://<username>.pythonanywhere.com
   RENTCAST_API_KEY=...
   HUD_API_TOKEN=...
   SCORECARD_API_KEY=...
   ```
3. Set up the database, data, and static files:
   ```bash
   python manage.py migrate
   python manage.py seed_demo          # towns + placeholder numbers
   python manage.py refresh_data       # real data (if HUD or Scorecard fail here, see 3b)
   python manage.py collectstatic --noinput
   python manage.py createsuperuser
   ```
3b. **If an API is blocked on PythonAnywhere**, fetch on your computer and upload the data:
   ```bash
   # on your computer, after refresh_data works there
   python manage.py dumpdata towns --exclude towns.ApiCall --indent 1 -o data/town_data.json
   # upload data/town_data.json in the Files tab, then in the PythonAnywhere console
   python manage.py loaddata data/town_data.json
   ```
4. **Web tab** → Add a new web app → **Manual configuration** → Python 3.12.
   - **Virtualenv:** `/home/<username>/.virtualenvs/rentcheck`
   - **Source code:** `/home/<username>/rentcheck`
   - **Static files:** URL `/static/` → Directory `/home/<username>/rentcheck/staticfiles`
   - **Force HTTPS:** on
5. Click the **WSGI configuration file** link and replace everything with:
   ```python
   import os, sys
   path = "/home/<username>/rentcheck"
   if path not in sys.path:
       sys.path.insert(0, path)
   os.environ["DJANGO_SETTINGS_MODULE"] = "rentcheck.settings"
   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```
   (`settings.py` loads `.env` itself.)
6. Click **Reload**. Open the site.

## Updating after a push

```bash
cd ~/rentcheck && git pull
workon rentcheck
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```
Then **Reload** on the Web tab.

## If something breaks

The Web tab has links to the **error log** and **server log**. Most first-deploy problems are a typo in `ALLOWED_HOSTS`, a missing `.env`, or forgetting `collectstatic`.
