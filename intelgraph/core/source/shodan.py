from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

import structlog

SHODAN_BASE = "https://api.shodan.io"

logger = structlog.get_logger(__name__)


@dataclass
class ShodanHostInfo:
    ip: str
    open_ports: list[int]
    services: list[str]
    org: str
    country: str
    last_update: str

    def to_evidence_content(self) -> str:
        parts = [f"Shodan host {self.ip}"]
        if self.org:
            parts.append(f"org={self.org}")
        if self.country:
            parts.append(f"country={self.country}")
        if self.open_ports:
            parts.append(f"open_ports={','.join(str(p) for p in self.open_ports)}")
        if self.services:
            parts.append(f"services={','.join(self.services)}")
        if self.last_update:
            parts.append(f"last_update={self.last_update}")
        return ". ".join(parts) + "."


class ShodanClient:
    """Shodan API client — free tier (1 req/min)."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("SHODAN_API_KEY", "")
        if not self._api_key:
            raise ValueError("SHODAN_API_KEY not set. Set the SHODAN_API_KEY environment variable.")

    def _request(self, ip: str) -> dict[str, Any]:
        url = f"{SHODAN_BASE}/shodan/host/{ip}?key={self._api_key}"
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.info("Shodan: no data for IP", ip=ip)
                return {}
            raise

    def get_host(self, ip: str) -> ShodanHostInfo | None:
        """Query Shodan for host information.  Sleeps 1s after each call
        to respect the free-tier rate limit (1 req/min)."""
        data = self._request(ip)
        time.sleep(1.0)
        if not data:
            return None

        ports: list[int] = []
        services: list[str] = []
        for item in data.get("data", []):
            port = item.get("port")
            if port and port not in ports:
                ports.append(port)
            product = item.get("product") or item.get("_shodan", {}).get("module", "")
            if product and product not in services:
                services.append(product)

        return ShodanHostInfo(
            ip=ip,
            open_ports=sorted(ports),
            services=services,
            org=data.get("org", "") or "",
            country=data.get("country_name", "") or "",
            last_update=data.get("last_update", "") or "",
        )
