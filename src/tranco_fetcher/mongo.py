from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database


def normalize_domain(value: str) -> str:
    candidate = value.strip().lower()
    if not candidate:
        return ""

    if "://" in candidate:
        candidate = urlparse(candidate).hostname or candidate

    candidate = candidate.strip(".")
    if candidate.startswith("www."):
        candidate = candidate[4:]
    return candidate


@dataclass(frozen=True, slots=True)
class TrancoTarget:
    rank: int
    domain: str


class TrancoRepository:
    def __init__(self, mongo_connection_string: str, db_name: str, collection_name: str) -> None:
        self.client = MongoClient(mongo_connection_string, tz_aware=True)
        self.db: Database = self.client[db_name]
        self.collection: Collection = self.db[collection_name]
        self.collection_name = collection_name

    def ensure_ready(self) -> None:
        if self.collection_name not in self.db.list_collection_names():
            self.db.create_collection(self.collection_name)
        self.collection.create_index([("url", ASCENDING)], unique=True)
        self.collection.create_index([("fetched_at", ASCENDING)])

    def fetched_domains(self) -> set[str]:
        domains: set[str] = set()
        for document in self.collection.find({}, {"url": 1, "metadata.requested_from": 1}):
            metadata = document.get("metadata") or {}
            requested_from = metadata.get("requested_from")
            if requested_from:
                normalized = normalize_domain(requested_from)
                if normalized:
                    domains.add(normalized)

            url = document.get("url")
            if url:
                normalized = normalize_domain(url)
                if normalized:
                    domains.add(normalized)
        return domains

    def next_batch_from_csv(self, csv_path: Path, limit: int) -> list[TrancoTarget]:
        fetched = self.fetched_domains()
        results: list[TrancoTarget] = []

        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            for row in reader:
                if len(row) < 2:
                    continue

                try:
                    rank = int(row[0].strip())
                except ValueError:
                    continue

                domain = normalize_domain(row[1])
                if not domain or domain in fetched:
                    continue

                results.append(TrancoTarget(rank=rank, domain=domain))
                if len(results) >= limit:
                    break

        return results

    def upsert_document(self, document: dict[str, Any]) -> None:
        self.collection.replace_one({"url": document["url"]}, document, upsert=True)

    def close(self) -> None:
        self.client.close()
