# CarbonTrack V2 — complete rebuild package

Flask + SQLAlchemy + PostgreSQL/Neon + Jinja + vanilla JS + Chart.js. This package keeps the existing model/table structure so it can be deployed against the existing CarbonTrack database without a destructive reset. It adds a premium 3D-inspired responsive interface, visible logout controls, stronger startup/health checks, safer device enrollment and telemetry handling, and corrected goal-period progress.

## Features
- Registration, login, POST-only logout, password hashing, CSRF protection and rate limits
- User profile and regional emission-factor selection
- Manual activity logging, factor-based carbon calculation and activity history
- Device enrollment, one-time bearer tokens (stored as SHA-256 hashes), revocation and authenticated telemetry
- Windows/Linux/macOS-compatible endpoint agent (CPU/memory observations; not falsely represented as electricity measurement)
- Dashboard, seven-/30-day analytics and clearly labelled directional trend projection
- Goals and progress, achievement milestone, PDF and CSV reports
- Admin factor registry and institution-level aggregate view
- Responsive mobile navigation, 3D-inspired cards/orbit hero, reduced-motion support
- `/health` verifies a live database query; SQLAlchemy pool pre-ping/recycle enabled

## Deploy safely

### Existing Render service + existing Neon database (recommended first)
1. Do not delete or reset either existing resource.
2. Back up the Neon database before switching application code.
3. Replace the repository contents with this package (or use the provided branch/commit when a write-enabled GitHub workflow is available).
4. Keep the existing Render service connected to the same repository and branch. Set build command `pip install -r requirements.txt` and start command `gunicorn wsgi:app --workers 2 --threads 4 --timeout 60`.
5. Keep the existing `DATABASE_URL` and `SECRET_KEY` values in Render. Keep `COOKIE_SECURE=true` and `RATELIMIT_STORAGE_URI=memory://` for a small single-instance deployment.
6. Deploy only after reviewing the changed files. Check `/health`, sign in, add one activity, test device enrollment, revoke test device, export PDF/CSV, and log out.

### New Render service + new Neon database
1. Create a new Neon project and database. Copy the pooled PostgreSQL connection string; never paste it into chat or source control.
2. Create a new Render Web Service connected to the same GitHub repository and the branch containing this build.
3. Build: `pip install -r requirements.txt`.
4. Start: `gunicorn wsgi:app --workers 2 --threads 4 --timeout 60`.
5. Health check path: `/health`.
6. Set `DATABASE_URL` to the new Neon pooled connection string; set `SECRET_KEY` using Render's Generate option; set `COOKIE_SECURE=true` and `RATELIMIT_STORAGE_URI=memory://`.
7. Deploy. The application runs additive `db.create_all()` on startup to create missing tables and a starter factor. It does not drop or alter existing tables. No `AUTO_CREATE_DB` flag or manual CREATE TABLE SQL is required.

## Database compatibility and limits
The models intentionally retain the existing table and column definitions. `db.create_all()` creates missing tables but does not migrate existing table structures. If a later release changes a model schema, create and review a Flask-Migrate migration before deploying. Back up the database first. Never point a clean test build at a production database without a backup and review.

## Environment variables
- `DATABASE_URL`: Neon PostgreSQL connection URL (required in production)
- `SECRET_KEY`: long random secret (required in production)
- `COOKIE_SECURE=true`: secure session cookies over HTTPS
- `RATELIMIT_STORAGE_URI=memory://`: process-local limiter for small deployments; use Redis for multi-instance production

## Carbon methodology
`carbon_kg = energy_kwh × active_region_factor_kg_per_kwh`. The included 0.70 kg/kWh Karnataka starter factor is a placeholder, not an official current disclosure factor. Configure the correct factor, source, version and reporting period before formal reporting. Historical records retain the carbon value calculated at entry time.

## Security and operational boundaries
Baseline protections are included but this is not a completed penetration/security audit. Before public production use, configure shared Redis rate limiting, review CSP, run dependency and penetration tests, and validate backups/restore. Generic CPU/RAM telemetry is not direct electricity measurement. Arbitrary code execution/sandboxing is intentionally not enabled in the Flask process; it needs a separately hardened worker/container with strict resource and network isolation.

## Local run
`python -m venv .venv`, activate it, `pip install -r requirements.txt`, set `SECRET_KEY` and optionally `DATABASE_URL`, then `python run.py`. For local development only, SQLite is used if `DATABASE_URL` is omitted.
