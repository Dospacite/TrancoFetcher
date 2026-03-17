from __future__ import annotations

import socket
import re
from functools import lru_cache
from typing import Any

import requests
import tldextract

BOOTSTRAP_URL = "https://data.iana.org/rdap/dns.json"
EXTRACT = tldextract.TLDExtract(suffix_list_urls=None)
WHOIS_IANA_SERVER = "whois.iana.org"
WHOIS_PORT = 43
WHOIS_SERVER_RE = re.compile(r"(?im)^(?:whois|refer):\s*(\S+)\s*$")


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


def _error_payload(error: str, *, lookup_source: str = "rdap", rdap_error: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "rdap_status": "error",
        "error": error,
    }
    if lookup_source != "rdap":
        payload["lookup_source"] = lookup_source
    if rdap_error is not None:
        payload["rdap_error"] = rdap_error
    return payload


def _ascii_domain(domain: str) -> str:
    return domain.strip().rstrip(".").encode("idna").decode("ascii")


def _lookup_rdap_http(domain: str, timeout_seconds: int) -> dict[str, Any]:
    try:
        base_url = _rdap_base_for_domain(domain)
    except (requests.RequestException, ValueError) as exc:
        return _error_payload(f"RDAP bootstrap lookup failed: {exc}")

    if not base_url:
        return _error_payload("No RDAP bootstrap server found")

    try:
        response = requests.get(
            f"{base_url}/domain/{domain}",
            headers={"Accept": "application/rdap+json"},
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        return _error_payload(str(exc))

    if response.status_code >= 400:
        return _error_payload(f"HTTP {response.status_code}")

    try:
        payload = response.json()
    except ValueError as exc:
        return _error_payload(f"Invalid JSON: {exc}")

    return payload if isinstance(payload, dict) else _error_payload("Unexpected RDAP payload")


def _whois_query(server: str, query: str, timeout_seconds: int) -> str:
    with socket.create_connection((server, WHOIS_PORT), timeout=timeout_seconds) as connection:
        connection.settimeout(timeout_seconds)
        connection.sendall(f"{query}\r\n".encode("utf-8"))

        chunks: list[bytes] = []
        while True:
            chunk = connection.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)

    return b"".join(chunks).decode("utf-8", errors="replace")


def _whois_server_for_domain(domain: str, timeout_seconds: int) -> str | None:
    extracted = EXTRACT(domain)
    if not extracted.suffix:
        return None

    response = _whois_query(WHOIS_IANA_SERVER, extracted.suffix.lower(), timeout_seconds)
    match = WHOIS_SERVER_RE.search(response)
    return match.group(1).strip() if match else None


def _whois_query_for_server(domain: str, server: str) -> str:
    ascii_domain = _ascii_domain(domain)
    if "verisign-grs.com" in server.lower():
        return f"={ascii_domain}"
    return ascii_domain


def _lookup_whois(domain: str, timeout_seconds: int, rdap_error: str) -> dict[str, Any]:
    try:
        whois_server = _whois_server_for_domain(domain, timeout_seconds)
    except OSError as exc:
        return _error_payload(f"WHOIS bootstrap lookup failed: {exc}", lookup_source="whois", rdap_error=rdap_error)

    if not whois_server:
        return _error_payload("No WHOIS server found", lookup_source="whois", rdap_error=rdap_error)

    query = _whois_query_for_server(domain, whois_server)
    try:
        raw_response = _whois_query(whois_server, query, timeout_seconds)
    except OSError as exc:
        return _error_payload(f"WHOIS lookup failed: {exc}", lookup_source="whois", rdap_error=rdap_error)

    return {
        "rdap_status": "fallback",
        "lookup_source": "whois",
        "query": _ascii_domain(domain),
        "whois_server": whois_server,
        "raw": raw_response,
        "rdap_error": rdap_error,
    }


def lookup_rdap(domain: str, timeout_seconds: int = 30) -> dict[str, Any]:
    rdap_payload = _lookup_rdap_http(domain, timeout_seconds)
    if rdap_payload.get("rdap_status") != "error":
        return rdap_payload

    return _lookup_whois(domain, timeout_seconds, rdap_payload["error"])
