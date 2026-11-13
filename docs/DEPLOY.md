# Deploying the live demo

The repo builds into **one container** (`Dockerfile`): FastAPI serves the API and the built
React app from the same origin, runs migrations on start, and can seed an empty database.
All data is synthetic, so a public demo is safe to publish, but read "Before you go public".

> I could not deploy this for you (it needs your accounts), so these steps are untested
> against a real host. The image itself is built and run locally as part of development:
> `make image`.

## What you need

- A Postgres database **with PostGIS**. [Neon](https://neon.tech) has a free tier and
  supports PostGIS (the first migration runs `CREATE EXTENSION IF NOT EXISTS postgis`; the
  database owner role must be allowed to do that).
- A container host. `fly.toml` is set up for [Fly.io](https://fly.io); Render or any Docker
  host works with the same environment variables.

## Environment variables

| Variable | Required | Notes |
|----------|----------|-------|
| `DATABASE_URL` | yes | SQLAlchemy URL with the driver: `postgresql+psycopg://USER:PASS@HOST/DB?sslmode=require`. Neon gives `postgresql://...`; add `+psycopg`. |
| `SECRET_KEY` | yes | Signs login tokens. The app refuses to start in production without it. `python -c "import secrets; print(secrets.token_hex(32))"` |
| `APP_ENV` | set by image | `production` |
| `DEMO_MODE` | demo only | `true` creates four demo accounts and shows them on the login form |
| `DEMO_PASSWORD` | demo only | Shared password for the demo accounts (shown publicly in demo mode) |
| `SEED_ON_EMPTY` | demo only | `true` loads the synthetic dataset on first boot |
| `PORT` | no | Defaults to 8000 |

## Fly.io

```bash
fly launch --no-deploy --copy-config      # pick a unique app name, keep fly.toml
fly secrets set DATABASE_URL='postgresql+psycopg://...' \
                SECRET_KEY="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
                DEMO_PASSWORD='choose-something-for-the-demo'
fly deploy
```

First boot migrates and seeds (this can take about a minute on a cold database).
Check `https://<app>.fly.dev/api/health`.

## Before you go public

- **Demo credentials are public on purpose.** Anyone can log in as `admin` and change or
  delete data. For a portfolio demo that is usually fine, but reset when needed: connect to
  the database, `TRUNCATE hazards, tasks, clearance_records, qa_inspections, audit_log
  RESTART IDENTITY CASCADE`, and restart the app (it reseeds an empty database).
  If you would rather not expose write access, set `DEMO_MODE=false`, create accounts with
  `POST /api/users`, and the public can still browse (reads are anonymous).
- **Login throttling** (5 failures per username and address in 5 minutes, then HTTP 429) is
  in-memory per process. With more than one instance, add throttling at the proxy too.
- **Content Security Policy**: the built frontend is served with a strict CSP that allows only
  the OpenStreetMap tile server and the AWS terrain tiles. Add any new tile or API host to
  `backend/app/security_headers.py`.
- **Field reports must be served over HTTPS** (Fly does this): browsers only give GPS
  positions to secure pages.
- **Seed location.** The synthetic hazards sit on real mountainous terrain in central Norway
  (so the 3D view has relief), and the basemap shows real place names. Karvonia is fictional;
  adjust `SHIFT_LON/SHIFT_LAT` in `backend/app/seed.py` if you want elsewhere.
- **Basemap and terrain tiles** come from OpenStreetMap's public servers and the AWS terrain tiles,
  both fine for a demo; use a tile provider before real traffic.

## CI

`.github/workflows/ci.yml` runs lint and the backend tests against PostGIS with a **90%
coverage floor**, builds the frontend, and builds the Docker image. After pushing to GitHub,
replace `OWNER/REPO` in the README badge.
