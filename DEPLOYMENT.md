# Deploying Stock Insights for free

This walks through hosting the app for a small number of daily users (2-3)
at no cost: **Supabase** (Postgres), **Render** (backend API, free web
service), **Vercel** (frontend), and **GitHub Actions** (the daily
morning data refresh). Total cost: $0/month, with the tradeoffs that come
with free tiers -- called out inline below.

Read this end to end once before starting -- a couple of steps (CORS,
GitHub Actions secrets) need values you only get from a *later* step, so
you'll do two short passes over the hosting dashboards.

## 0. Prerequisite: this project isn't a git repo yet

Everything below assumes the code is pushed to a GitHub repo (Render,
Vercel, and GitHub Actions all deploy/run from one). If you haven't done
this yet:

```bash
cd "Stock Insight"          # the folder containing backend/ and frontend/
git init
git add .
git commit -m "Initial commit"
```

Then create an empty repo on GitHub (github.com -> New repository -- don't
initialize it with a README) and push:

```bash
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```

**Public vs. private repo:** GitHub Actions' scheduled workflows (used for
the daily refresh, step 5) are unlimited/free on public repos, and come
with a generous free monthly minutes budget on private repos too -- either
works here, but if you want to be certain the daily job never has any
usage-based cost, a public repo is the simplest guarantee. There's nothing
sensitive in this codebase (no secrets are committed -- connection strings
and keys all live in `.env` files, which `.gitignore` already excludes).

## 1. Supabase: the database

1. Create a free account at supabase.com and a new project (pick any
   region close to you; note the database password you set -- you'll need
   it in the connection string).
2. Once the project is up: **Project Settings -> Database -> Connection
   string -> URI**, and switch to the **"Connection pooling"** tab (not
   "Direct connection"). Copy that string -- it looks like:
   ```
   postgresql://postgres.xxxxxxxxxxxx:[YOUR-PASSWORD]@aws-0-xx-xxxx-1.pooler.supabase.com:6543/postgres
   ```
   Use the **pooler** (port 6543), not the direct connection (port 5432):
   Supabase's free tier caps direct connections low, and the pooler is what
   keeps a low-traffic backend + the daily GitHub Actions job from ever
   competing for that limit.
3. Fill in your actual password, and change the scheme from `postgresql://`
   to `postgresql+psycopg2://` so SQLAlchemy uses the right driver. This
   full string is your `DATABASE_URL` for every step below.
4. **Create the tables once**, from your machine, before deploying anything:
   ```bash
   cd backend
   source .venv/bin/activate
   DATABASE_URL="postgresql+psycopg2://...your string..." python -m app.db.init_db
   ```
   You should see `Database tables created.` -- check the Supabase
   dashboard's Table Editor to confirm `stocks`, `computed_metrics`, etc.
   now exist. (The backend also runs this automatically on every startup,
   so this step is optional/redundant, but doing it once yourself up front
   means you can verify it worked before anything else depends on it.)

**Free-tier gotcha:** Supabase pauses free projects after 7 days of
*complete* inactivity (no API/DB traffic at all). The daily refresh job
(step 5) hits the database every morning, which counts as activity and
should keep it from ever pausing -- but if you ever disable that workflow
for more than a week, check the Supabase dashboard for a "paused" banner
and click "Restore" if so.

## 2. Render: the backend API

1. Create a free account at render.com and connect your GitHub account.
2. **New -> Web Service**, select your repo.
3. Configure:
   - **Root Directory:** `backend`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** Free
   - **Health Check Path:** `/health`
4. Add environment variables (Render dashboard -> your service ->
   Environment):
   - `DATABASE_URL` -- the full Supabase pooler string from step 1
   - `CORS_ORIGINS` -- leave as `http://localhost:4000` for now; you'll come
     back and update this in step 4 once you have your Vercel URL
   - `APP_ENV` = `production`
   - `PYTHON_VERSION` = `3.10.14` -- **important:** without this, Render
     defaults to whatever its newest Python is, which has no prebuilt wheel
     for `pandas==2.2.2` and fails trying to compile it from source (a
     Cython/GCC incompatibility, surfaces as a `meson`/`ninja` build error).
     A `.python-version` file committed in `backend/` should also pin this
     automatically, but setting it explicitly here too is the belt-and-suspenders
     fix if you already hit that build failure.
5. Deploy. Once it's live, note the URL Render gives you (something like
   `https://stock-insights-backend.onrender.com`) -- you'll need it for
   step 3. Sanity check it: `https://<your-render-url>/health` should
   return `{"status": "ok"}`, and `/docs` should show the Swagger UI.

(A `render.yaml` exists in `backend/` if you'd rather use Render's
Blueprint/infra-as-code flow instead of the manual steps above -- the
manual dashboard steps are documented here since they're the more
foolproof path regardless of how your repo is laid out.)

**Free-tier tradeoff:** this service spins down after ~15 minutes with no
requests, and the first request after a gap takes ~30-50 seconds to wake
back up. For 2-3 daily users this is a minor "the first load today is
slow" annoyance, not a real problem -- and it doesn't affect the daily
refresh job at all, since that talks to Supabase directly (step 5), not
through this backend.

## 3. Vercel: the frontend

1. Create a free account at vercel.com, connect GitHub, **Add New ->
   Project**, select the same repo.
2. Configure:
   - **Root Directory:** `frontend`
   - Framework Preset: Next.js (should auto-detect)
3. Environment variable: `BACKEND_URL` = your Render URL from step 2
   (e.g. `https://stock-insights-backend.onrender.com`, **no trailing
   slash**).
4. Deploy. Note the URL Vercel gives you (e.g.
   `https://your-app.vercel.app`).

## 4. Go back and fix CORS

Now that you have your Vercel URL: Render dashboard -> your backend service
-> Environment -> update `CORS_ORIGINS` to your Vercel URL (e.g.
`https://your-app.vercel.app`, no trailing slash; comma-separate multiple
origins if needed). Save -- Render redeploys automatically. Without this
step, the frontend loads but every API call fails in the browser console
with a CORS error.

Open your Vercel URL and confirm the dashboard loads real data (it'll be
empty/503 on movers/sectors/momentum until the first refresh runs -- see
step 5).

## 5. GitHub Actions: the daily refresh

The workflow file `.github/workflows/daily-refresh.yml` is already in the
repo (from this session's changes) -- it just needs one secret to run:

1. GitHub repo -> **Settings -> Secrets and variables -> Actions -> New
   repository secret**.
2. Name: `DATABASE_URL`. Value: the same Supabase pooler string from step 1.
3. Optional -- **AI Pick of the Day**: add a second secret named
   `ANTHROPIC_API_KEY` (get one at console.anthropic.com) if you want the
   daily AI-generated stock pick feature (see README). This step of the
   workflow is best-effort: skip this secret and it just logs a warning and
   exits cleanly, without blocking or failing the core movers/momentum
   refresh above. Not needed on Render -- the API endpoint only reads
   whatever this job last wrote, it never calls Anthropic itself.
4. That's it -- the schedule (`0 11 * * *` UTC, ~7am US Eastern) is already
   committed. Adjust the cron line in the workflow file if you want a
   different time; see the comment next to it for the UTC math.
4. **Test it now, don't wait for tomorrow morning:** GitHub repo ->
   **Actions** tab -> "Daily market data refresh" -> **Run workflow**
   (this is the `workflow_dispatch` trigger). Watch it run -- for the full
   NYSE+NASDAQ universe this will take a while (the whole point of running
   it as a background job, not something you wait on). If you'd rather
   verify quickly first, you can temporarily test locally against Supabase
   with a small ticker list:
   ```bash
   cd backend
   DATABASE_URL="...supabase string..." python -m scripts.refresh_cache AAPL MSFT
   ```
5. **If the full-universe run doesn't reliably finish** within the job's
   6-hour ceiling (it's tuned to avoid this, but yfinance/Stooq throttling
   is inherently variable): edit the workflow's last line to
   `python -m scripts.refresh_cache --sp500` instead. This narrows every
   daily refresh to the ~500 S&P 500 constituents rather than the full
   ~6,000-9,000 ticker universe -- movers/sectors/momentum/tickers would
   then only cover S&P 500 stocks. This is a real scope tradeoff (full
   market vs. S&P 500 only), not just a performance knob, so it's left as a
   manual choice rather than something this workflow decides on its own.

Once a refresh completes, reload your Vercel URL -- the dashboard and
momentum screeners should now show real data, and `as_of` timestamps
should reflect the run that just finished.

## Summary of what runs where

| Piece | Host | Cost | Notes |
|---|---|---|---|
| Postgres database | Supabase | Free | 500MB, pauses after 7 days total inactivity |
| Backend API | Render | Free | Spins down after ~15 min idle, ~30-50s cold start |
| Frontend | Vercel | Free | No idle spin-down for the frontend itself |
| Daily refresh job | GitHub Actions | Free | Runs against Supabase directly, independent of Render's uptime |

## Ongoing: keeping it running

- The daily GitHub Actions run is what keeps `computed_metrics` (and
  therefore the Supabase project's activity, and therefore its
  not-paused status) current -- no other maintenance needed.
- If you push new code, Render and Vercel both auto-redeploy from the
  connected branch by default.
- If you ever change the DB schema (add a column to `ComputedMetrics`,
  etc.) -- see the README's "If you already ran this app before this
  update" section. On Supabase you can't just delete the file the way you
  can with local SQLite; you'd instead need to either drop/recreate the
  affected table via the Supabase SQL editor, or (better, once this
  matters) set up Alembic migrations instead of `create_all`.
