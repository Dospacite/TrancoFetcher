from __future__ import annotations

import hashlib
import html
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from scrapling.fetchers import StealthySession
import tldextract

from .config import Settings
from .mongo import TrancoTarget
from .rdap import lookup_rdap

LOGGER = logging.getLogger(__name__)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
EXTRACT = tldextract.TLDExtract(suffix_list_urls=None)


class WebsiteScraper:
    def __init__(self, settings: Settings, session: StealthySession) -> None:
        self.settings = settings
        self.session = session

    def scrape_target(self, target: TrancoTarget) -> dict[str, Any]:
        rdap = lookup_rdap(target.domain)
        attempts = self._candidate_urls(target.domain)

        last_document: dict[str, Any] | None = None
        for requested_url in attempts:
            document = self._scrape_url(requested_url=requested_url, domain=target.domain, rdap=rdap)
            last_document = document
            if self._is_usable_document(document):
                return document
            LOGGER.warning("Fetch failed for %s, trying next candidate if available.", requested_url)

        assert last_document is not None
        return last_document

    def _scrape_url(self, requested_url: str, domain: str, rdap: dict[str, Any]) -> dict[str, Any]:
        timestamp = datetime.now(timezone.utc)
        screenshot_relative = self._build_screenshot_path(domain=domain, requested_url=requested_url, timestamp=timestamp)
        screenshot_absolute = self.settings.project_root / screenshot_relative
        screenshot_holder: dict[str, str] = {}

        def capture_screenshot(page: Any) -> None:
            if not self.settings.screenshot_dir:
                return
            screenshot_absolute.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_absolute), full_page=True)
            screenshot_holder["path"] = screenshot_relative.as_posix()

        started = perf_counter()
        try:
            response = self.session.fetch(
                requested_url,
                page_action=capture_screenshot,
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
                    "error": str(exc),
                },
                "rdap": rdap,
            }
            if screenshot_holder.get("path"):
                document["screenshot_path"] = screenshot_holder["path"]
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

        if screenshot_holder.get("path"):
            document["screenshot_path"] = screenshot_holder["path"]

        return document

    def _candidate_urls(self, domain: str) -> list[str]:
        extracted = EXTRACT(domain)
        hostnames = [domain]

        # Some apex domains only serve content on the www host.
        if extracted.suffix and extracted.subdomain == "":
            hostnames.append(f"www.{domain}")

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

    def _build_screenshot_path(self, domain: str, requested_url: str, timestamp: datetime) -> Path:
        token = hashlib.sha1(requested_url.encode("utf-8")).hexdigest()[:8]
        filename = f"{self._safe_slug(domain)}_{token}_{timestamp.strftime('%Y%m%d_%H%M%S')}.png"
        return self.settings.screenshot_dir.relative_to(self.settings.project_root) / filename

    @staticmethod
    def _extract_title(body: str) -> str:
        match = TITLE_RE.search(body)
        if not match:
            return ""
        return html.unescape(" ".join(match.group(1).split()))

    @staticmethod
    def _safe_slug(value: str) -> str:
        return re.sub(r"[^a-zA-Z0-9.-]+", "_", value).strip("_") or "site"
