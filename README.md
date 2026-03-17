# Tranco Fetcher

This project reads domains from `tranco_W4XN9.csv`, fetches website content with Scrapling Stealth Mode, and stores the results in `tranco.websites` using the same document shape already used by `phishing_db.website_content`.

## What It Does

- Loads `MONGO_CONNECTION_STRING` from `.env`
- Creates `tranco.websites` if it does not exist yet
- Creates a unique index on `url`
- Skips domains that already exist in `tranco.websites`
- Fetches the next batch of unfetched Tranco domains with Scrapling's `StealthySession`
- Tries multiple hostname variants for each domain:
  - `https://domain`
  - `http://domain`
  - `https://www.domain`
  - `http://www.domain`
- Continues to the next variant when a candidate is unreachable or returns HTTP `4xx`/`5xx`
- Stores documents shaped like:
  - `url`
  - `title`
  - `html`
  - `error`
  - `fetched_at`
  - `metadata`
  - `rdap`
  - `screenshot_path`

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
- `TRANCO_SCREENSHOT_DIR` default: `data/screenshots`
- `TRANCO_REQUEST_TIMEOUT_MS` default: `45000`
- `TRANCO_REQUEST_WAIT_MS` default: `1500`
- `TRANCO_HEADLESS` default: `true`
- `TRANCO_NETWORK_IDLE` default: `true`
- `TRANCO_DISABLE_RESOURCES` default: `false`
- `TRANCO_SOLVE_CLOUDFLARE` default: `true`
- `TRANCO_ALLOW_HTTP_FALLBACK` default: `true`
- `TRANCO_DRY_RUN` default: `false`

## Run Locally

```bash
source .venv/bin/activate
PYTHONPATH=src python -m tranco_fetcher --dry-run
PYTHONPATH=src python -m tranco_fetcher
```

## Run With Docker Compose

```bash
docker compose up --build
```

Screenshots are written to `data/screenshots/`.

## Research Note

This workflow is intended for academic research. Review your institutional requirements, the target websites' terms, and applicable law before large-scale collection.
