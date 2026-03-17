from __future__ import annotations

import argparse
import logging
from dataclasses import replace
from pathlib import Path

from scrapling.fetchers import StealthySession

from .config import Settings
from .mongo import TrancoRepository
from .scraper import WebsiteScraper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch Tranco domains into MongoDB with Scrapling Stealth Mode.")
    parser.add_argument("--batch-size", type=int, help="Override TRANCO_BATCH_SIZE for this run.")
    parser.add_argument("--dry-run", action="store_true", help="List the next batch without fetching or writing.")
    return parser


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def main() -> None:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args()

    settings = Settings.from_env(project_root=Path.cwd())
    if args.batch_size:
        settings = replace(settings, batch_size=args.batch_size)
    if args.dry_run:
        settings = replace(settings, dry_run=True)

    logger = logging.getLogger("tranco_fetcher")

    if not settings.tranco_csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {settings.tranco_csv_path}")

    repository = TrancoRepository(
        mongo_connection_string=settings.mongo_connection_string,
        db_name=settings.mongo_db_name,
        collection_name=settings.mongo_collection_name,
    )

    try:
        repository.ensure_ready()
        targets = repository.next_batch_from_csv(settings.tranco_csv_path, settings.batch_size)
        logger.info(
            "Selected %s unfetched domains from %s into %s.%s",
            len(targets),
            settings.tranco_csv_path.name,
            settings.mongo_db_name,
            settings.mongo_collection_name,
        )

        if settings.dry_run:
            for target in targets:
                logger.info("Dry run target rank=%s domain=%s", target.rank, target.domain)
            return

        if not targets:
            logger.info("No unfetched domains remain.")
            return

        with StealthySession(
            headless=settings.headless,
            network_idle=settings.network_idle,
            disable_resources=settings.disable_resources,
            solve_cloudflare=settings.solve_cloudflare,
            timeout=settings.request_timeout_ms,
            wait=settings.request_wait_ms,
            google_search=False,
            retries=1,
        ) as session:
            scraper = WebsiteScraper(settings=settings, session=session)
            batch_number = 1
            while targets:
                logger.info("Processing batch %s with %s domains", batch_number, len(targets))
                for target in targets:
                    document = scraper.scrape_target(target)
                    repository.upsert_document(document)
                    logger.info("Stored rank=%s domain=%s url=%s", target.rank, target.domain, document["url"])

                targets = repository.next_batch_from_csv(settings.tranco_csv_path, settings.batch_size)
                if targets:
                    logger.info(
                        "Selected %s additional unfetched domains from %s for batch %s",
                        len(targets),
                        settings.tranco_csv_path.name,
                        batch_number + 1,
                    )
                batch_number += 1

            logger.info("No unfetched domains remain.")
    finally:
        repository.close()


if __name__ == "__main__":
    main()
