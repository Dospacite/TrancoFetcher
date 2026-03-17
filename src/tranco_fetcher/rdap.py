from __future__ import annotations

from functools import lru_cache
from typing import Any

import requests
import tldextract

BOOTSTRAP_URL = "https://data.iana.org/rdap/dns.json"
EXTRACT = tldextract.TLDExtract(suffix_list_urls=None)


@lru_cache(maxsize=1)
def _bootstrap_map() -> dict[str, str]:
    response = requests.get(BOOTSTRAP_URL, timeout=30)
    response.raise_for_status()
    payload = response.json()

    mapping: dict[str, str] = {}
    for suffixes, servers in payload.get("services", []):
        if not servers:
            continue
        server = servers[0].rstrip("/")
        for suffix in suffixes:
            mapping[suffix.lower()] = server
    return mapping


def _rdap_base_for_domain(domain: str) -> str | None:
    extracted = EXTRACT(domain)
    if not extracted.suffix:
        return None

    suffix = extracted.suffix.lower()
    mapping = _bootstrap_map()
    return mapping.get(suffix)


def lookup_rdap(domain: str, timeout_seconds: int = 30) -> dict[str, Any]:
    base_url = _rdap_base_for_domain(domain)
    if not base_url:
        return {"rdap_status": "error", "error": "No RDAP bootstrap server found"}

    try:
        response = requests.get(
            f"{base_url}/domain/{domain}",
            headers={"Accept": "application/rdap+json"},
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        return {"rdap_status": "error", "error": str(exc)}

    if response.status_code >= 400:
        return {"rdap_status": "error", "error": f"HTTP {response.status_code}"}

    try:
        payload = response.json()
    except ValueError as exc:
        return {"rdap_status": "error", "error": f"Invalid JSON: {exc}"}

    return payload if isinstance(payload, dict) else {"rdap_status": "error", "error": "Unexpected RDAP payload"}
