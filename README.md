# Tranco Fetcher

This project reads domains from `tranco_W4XN9.csv`, fetches website content with Scrapling Stealth Mode, and stores the results in `tranco.websites` using the same document shape already used by `phishing_db.website_content`.

## What It Does

- Loads `MONGO_CONNECTION_STRING` from `.env`
- Creates `tranco.websites` if it does not exist yet
- Creates a unique index on `url`
- Skips domains that already exist in `tranco.websites`
- Continuously fetches unfetched Tranco domains in batches with Scrapling's `StealthySession` until none remain
- Looks up RDAP metadata for each domain and falls back to WHOIS when RDAP is unavailable
- Pins browser locale/timezone and `Accept-Language` to reduce locale drift from the collector environment
- Tries multiple hostname variants for each domain:
  - `https://www.domain`
  - `https://domain`
- For domains without a subdomain, `www.` is tried first by default
- Uses a fast HTTP preflight before opening the browser, so redirects like `google.com -> www.google.com` are resolved early
- Falls back to Scrapling Stealth Mode when preflight returns HTTP `403`, since bot protection can block the plain HTTP probe
- Continues to the next variant when a candidate is unreachable or returns other HTTP `4xx`/`5xx` responses during preflight
- Stores documents shaped like:
  - `url`
  - `title`
  - `html`
  - `error`
  - `fetched_at`
  - `metadata`
  - `rdap`

## Local Environment

The project uses a dedicated virtual environment at `.venv`.

```bash
python3 -m virtualenv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
scrapling install
```

## Configuration

The project reads these settings from `.env` or the container environment:

- `MONGO_CONNECTION_STRING`
- `TRANCO_BATCH_SIZE` default: `10`
- `TRANCO_CSV_PATH` default: `tranco_W4XN9.csv`
- `TRANCO_REQUEST_TIMEOUT_MS` default: `5000`
- `TRANCO_REQUEST_WAIT_MS` default: `3000`
- `TRANCO_PREFLIGHT_TIMEOUT_SECONDS` default: `5`
- `TRANCO_HEADLESS` default: `true`
- `TRANCO_NETWORK_IDLE` default: `true`
- `TRANCO_DISABLE_RESOURCES` default: `false`
- `TRANCO_SOLVE_CLOUDFLARE` default: `true`
- `TRANCO_BROWSER_LOCALE` default: `en-US`
- `TRANCO_BROWSER_TIMEZONE_ID` default: `UTC`
- `TRANCO_ACCEPT_LANGUAGE` default: `en-US,en;q=0.9`
- `TRANCO_DRY_RUN` default: `false`

## Run Locally

```bash
source .venv/bin/activate
PYTHONPATH=src python -m tranco_fetcher --dry-run
PYTHONPATH=src python -m tranco_fetcher
```

`--dry-run` still lists only the next batch. A normal run keeps processing batch after batch until no unfetched domains remain.

## Run With Docker Compose

```bash
docker compose up --build
```

## Research Note

This workflow is intended for academic research. Review your institutional requirements, the target websites' terms, and applicable law before large-scale collection.
