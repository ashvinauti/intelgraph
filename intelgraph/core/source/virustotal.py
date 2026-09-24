from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC
from typing import Any

import structlog

VT_BASE = "https://www.virustotal.com/api/v3"

logger = structlog.get_logger(__name__)


@dataclass
class VtReport:
    indicator: str
    indicator_type: str  # "ip" or "domain"
    malicious_votes: int
    suspicious_votes: int
    harmless_votes: int
    total_engines: int
    reputation: int
    last_analysis_date: str

    @property
    def malicious_ratio(self) -> float:
        """Ratio of malicious votes to total engines (0.0-1.0)."""
        if self.total_engines == 0:
            return 0.0
        return self.malicious_votes / self.total_engines

    def to_evidence_content(self) -> str:
        return (
            f"VirusTotal {self.indicator_type} {self.indicator}: "
            f"malicious={self.malicious_votes}, suspicious={self.suspicious_votes}, "
            f"harmless={self.harmless_votes}, total={self.total_engines}, "
            f"reputation={self.reputation}, last_analysis={self.last_analysis_date}."
        )


class VirusTotalClient:
    """VirusTotal v3 API client — free tier (4 req/min)."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("VIRUSTOTAL_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "VIRUSTOTAL_API_KEY not set. Set the VIRUSTOTAL_API_KEY environment variable."
            )

    def _request(self, endpoint: str) -> dict[str, Any]:
        url = f"{VT_BASE}{endpoint}"
        req = urllib.request.Request(url)
        req.add_header("x-apikey", self._api_key)
        req.add_header("Accept", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                logger.info("VirusTotal: no data for indicator", endpoint=endpoint)
                return {}
            raise

    def _parse_report(self, data: dict[str, Any], indicator: str, itype: str) -> VtReport | None:
        attrs = data.get("data", {}).get("attributes", {})
        if not attrs:
            return None
        stats = attrs.get("last_analysis_stats", {})
        reputation = attrs.get("reputation", 0)
        last_analysis = attrs.get("last_analysis_date", "")
        if isinstance(last_analysis, (int, float)):
            from datetime import datetime

            last_analysis = datetime.fromtimestamp(last_analysis, tz=UTC).isoformat()

        malicious = stats.get("malicious", 0)
        suspicious = stats.get("suspicious", 0)
        harmless = stats.get("harmless", 0)
        total = malicious + suspicious + harmless

        return VtReport(
            indicator=indicator,
            indicator_type=itype,
            malicious_votes=malicious,
            suspicious_votes=suspicious,
            harmless_votes=harmless,
            total_engines=total,
            reputation=reputation,
            last_analysis_date=str(last_analysis),
        )

    def get_ip_report(self, ip: str) -> VtReport | None:
        """Query VirusTotal for an IP address.  Sleeps 0.25s after each call."""
        data = self._request(f"/ip_addresses/{ip}")
        time.sleep(0.25)
        return self._parse_report(data, ip, "ip")

    def get_domain_report(self, domain: str) -> VtReport | None:
        """Query VirusTotal for a domain.  Sleeps 0.25s after each call."""
        data = self._request(f"/domains/{domain}")
        time.sleep(0.25)
        return self._parse_report(data, domain, "domain")
