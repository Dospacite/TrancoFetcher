from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

import requests
from scrapling.fetchers import StealthySession
import tldextract
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning

from .config import Settings
from .mongo import TrancoTarget
from .rdap import lookup_rdap

LOGGER = logging.getLogger(__name__)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
EXTRACT = tldextract.TLDExtract(suffix_list_urls=None)
disable_warnings(InsecureRequestWarning)


class WebsiteScraper:
    def __init__(self, settings: Settings, session: StealthySession) -> None:
        self.settings = settings
        self.session = session

    def scrape_target(self, target: TrancoTarget) -> dict[str, Any]:
        rdap = lookup_rdap(target.domain)
        attempts = self._candidate_urls(target.domain)

        last_document: dict[str, Any] | None = None
        for requested_url in attempts:
            preflight = self._preflight_url(requested_url)
            if preflight["skip"]:
                LOGGER.warning(
                    "Preflight rejected %s with status=%s error=%s",
                    requested_url,
                    preflight.get("status_code"),
                    preflight.get("error"),
                )
                last_document = self._preflight_error_document(requested_url, rdap, preflight)
                continue

            document = self._scrape_url(
                requested_url=preflight["final_url"],
                rdap=rdap,
                requested_from=requested_url,
            )
            last_document = document
            if self._is_usable_document(document):
                return document
            LOGGER.warning("Fetch failed for %s, trying next candidate if available.", requested_url)

        assert last_document is not None
        return last_document

    def _scrape_url(
        self,
        requested_url: str,
        rdap: dict[str, Any],
        requested_from: str | None = None,
    ) -> dict[str, Any]:
        started = perf_counter()
        try:
            response = self.session.fetch(
                requested_url,
                timeout=self.settings.request_timeout_ms,
                wait=self.settings.request_wait_ms,
                network_idle=self.settings.network_idle,
            )
        except Exception as exc:
            document: dict[str, Any] = {
                "url": requested_url,
                "error": None,
                "metadata": {
                    "url": requested_url,
                    "requested_from": requested_from or requested_url,
                    "error": str(exc),
                },
                "rdap": rdap,
            }
            return document

        finished_at = datetime.now(timezone.utc)
        body = response.body.decode(response.encoding or "utf-8", errors="replace")
        redirect_history = [
            {
                "status_code": item.status,
                "url": item.url,
                "headers": dict(item.headers),
                "timestamp": finished_at,
            }
            for item in response.history
        ]

        document = {
            "url": requested_url,
            "title": self._extract_title(body),
            "html": body,
            "error": None,
            "fetched_at": finished_at,
            "metadata": {
                "url": requested_url,
                "requested_from": requested_from or requested_url,
                "status_code": response.status,
                "headers": dict(response.headers),
                "encoding": response.encoding,
                "elapsed_ms": round((perf_counter() - started) * 1000, 3),
                "final_url": response.url,
                "redirect_count": len(response.history),
                "redirect_history": redirect_history,
                "content_length": len(response.body),
                "timestamp": finished_at,
            },
            "rdap": rdap,
        }

        return document

    def _candidate_urls(self, domain: str) -> list[str]:
        extracted = EXTRACT(domain)
        hostnames = [domain]

        # Some apex domains only serve content on the www host.
        if extracted.suffix and extracted.subdomain == "":
            hostnames = [f"www.{domain}", domain]

        urls: list[str] = []
        for hostname in hostnames:
            urls.append(f"https://{hostname}")
            if self.settings.allow_http_fallback:
                urls.append(f"http://{hostname}")
        return urls

    @staticmethod
    def _is_usable_document(document: dict[str, Any]) -> bool:
        metadata = document.get("metadata", {})
        status_code = metadata.get("status_code")
        if not isinstance(status_code, int):
            return False
        return status_code < 400

    def _preflight_url(self, url: str) -> dict[str, Any]:
        try:
            response = requests.get(
                url,
                allow_redirects=True,
                timeout=self.settings.preflight_timeout_seconds,
                headers={"User-Agent": "Mozilla/5.0"},
            )
        except requests.exceptions.SSLError:
            try:
                response = requests.get(
                    url,
                    allow_redirects=True,
                    timeout=self.settings.preflight_timeout_seconds,
                    headers={"User-Agent": "Mozilla/5.0"},
                    verify=False,
                )
            except requests.RequestException as exc:
                return {
                    "final_url": url,
                    "error": str(exc),
                    "skip": False,
                }
            return {
                "final_url": response.url or url,
                "status_code": response.status_code,
                "skip": response.status_code >= 400,
                "insecure": True,
            }
        except requests.RequestException as exc:
            return {
                "final_url": url,
                "error": str(exc),
                "skip": False,
            }

        return {
            "final_url": response.url or url,
            "status_code": response.status_code,
            "skip": response.status_code >= 400,
        }

    @staticmethod
    def _preflight_error_document(requested_url: str, rdap: dict[str, Any], preflight: dict[str, Any]) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "url": requested_url,
        }
        if "final_url" in preflight:
            metadata["final_url"] = preflight["final_url"]
        if "status_code" in preflight:
            metadata["status_code"] = preflight["status_code"]
        if "error" in preflight:
            metadata["error"] = preflight["error"]

        return {
            "url": requested_url,
            "error": None,
            "metadata": metadata,
            "rdap": rdap,
        }

    @staticmethod
    def _extract_title(body: str) -> str:
        match = TITLE_RE.search(body)
        if not match:
            return ""
        return html.unescape(" ".join(match.group(1).split()))
