from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

OTX_BASE = "https://otx.alienvault.com"


@dataclass
class OtxPulse:
    pulse_id: str
    name: str
    description: str
    author: str
    created: str
    modified: str
    tags: list[str]
    indicators: list[dict[str, Any]]
    malware_families: list[str]
    tlp: str

    def to_source_dict(self) -> dict[str, Any]:
        indicators_text = "; ".join(
            f"{i.get('type', '?')}:{i.get('indicator', '')}" for i in self.indicators[:50]
        )
        tags_text = ", ".join(self.tags)
        text = (
            f"OTX Pulse: {self.name}. "
            f"Description: {self.description}. "
            f"TLP: {self.tlp}. "
            f"Tags: {tags_text}. "
            f"Malware: {', '.join(self.malware_families)}. "
            f"Indicators: {indicators_text}."
        )
        return {
            "id": f"otx_{self.pulse_id}",
            "name": f"OTX Pulse: {self.name}",
            "text": text,
            "value": 75,
        }


class OtxClient:
    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("OTX_API_KEY", "")
        if not self._api_key:
            raise ValueError("OTX_API_KEY not set. Set the OTX_API_KEY environment variable.")

    def _request(self, path: str) -> dict[str, Any]:
        url = f"{OTX_BASE}{path}"
        req = urllib.request.Request(url)
        req.add_header("X-OTX-API-KEY", self._api_key)
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_pulses(self, page: int = 1, limit: int = 20) -> list[OtxPulse]:
        data = self._request(f"/api/v1/pulses/subscribed?page={page}&limit={limit}")
        pulses_raw = []
        if "results" in data:
            pulses_raw = data["results"]
        elif "pulses" in data:
            pulses_raw = data["pulses"]
        else:
            pulses_raw = [data]

        pulses: list[OtxPulse] = []
        for p in pulses_raw[:limit]:
            pulses.append(
                OtxPulse(
                    pulse_id=p.get("id", ""),
                    name=p.get("name", ""),
                    description=p.get("description", ""),
                    author=p.get("author", {}).get("username", ""),
                    created=p.get("created", ""),
                    modified=p.get("modified", ""),
                    tags=[t.lower() for t in p.get("tags", [])],
                    indicators=p.get("indicators", [])[:50],
                    malware_families=[m.lower() for m in p.get("malware_families", [])],
                    tlp=p.get("tlp", ""),
                )
            )
        return pulses

    def get_pulses_all(
        self, max_pages: int = 5, limit: int = 20, delay: float = 0.5
    ) -> list[OtxPulse]:
        all_pulses: list[OtxPulse] = []
        for page in range(1, max_pages + 1):
            try:
                pulses = self.get_pulses(page=page, limit=limit)
                if not pulses:
                    break
                all_pulses.extend(pulses)
                if page < max_pages:
                    time.sleep(delay)
            except Exception as exc:
                import structlog

                structlog.get_logger(__name__).warning(
                    "OTX page fetch failed", page=page, error=str(exc)
                )
                break
        return all_pulses

    def extract_iocs(
        self,
        pulses: list[OtxPulse],
    ) -> dict[str, list[dict[str, Any]]]:
        iocs: dict[str, list[dict[str, Any]]] = {
            "IPv4": [],
            "domain": [],
            "URL": [],
            "MD5": [],
            "SHA1": [],
            "SHA256": [],
            "email": [],
            "hostname": [],
            "CVE": [],
        }
        for pulse in pulses:
            for ind in pulse.indicators:
                itype = ind.get("type", "")
                value = ind.get("indicator", "")
                if not value:
                    continue
                entry = {
                    "indicator": value,
                    "type": itype,
                    "pulse_id": pulse.pulse_id,
                    "pulse_name": pulse.name,
                    "tags": pulse.tags,
                    "malware": pulse.malware_families,
                }
                if itype in iocs:
                    iocs[itype].append(entry)
                else:
                    iocs.setdefault("other", []).append(entry)
        return iocs

    @staticmethod
    def find_common_iocs(
        urlhaus_iocs: list[dict[str, Any]],
        otx_iocs: list[dict[str, Any]],
        ioc_key: str = "indicator",
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        otx_set = {i[ioc_key].strip().lower() for i in otx_iocs if i.get(ioc_key)}
        common: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for u in urlhaus_iocs:
            val = u.get(ioc_key, "").strip().lower()
            if val and val in otx_set:
                match = next(o for o in otx_iocs if o.get(ioc_key, "").strip().lower() == val)
                common.append((u, match))
        return common


def fetch_urlhaus_iocs(csv_path: str) -> dict[str, list[dict[str, Any]]]:
    import csv

    iocs: dict[str, list[dict[str, Any]]] = {
        "IPv4": [],
        "domain": [],
        "URL": [],
    }
    with open(csv_path) as f:
        lines = [line for line in f if not line.startswith("#")]
    for r in csv.reader(lines):
        url = r[2] if len(r) > 2 else ""
        ip = r[3] if len(r) > 3 else ""
        domain_col = r[5] if len(r) > 5 else ""

        if url:
            iocs["URL"].append({"indicator": url, "source": "urlhaus"})
        if ip:
            iocs["IPv4"].append({"indicator": ip, "source": "urlhaus"})
        if domain_col:
            iocs["domain"].append({"indicator": domain_col, "source": "urlhaus"})

        # Extract domain from URL
        if url:
            from urllib.parse import urlparse

            try:
                hostname = urlparse(url).hostname or ""
                if hostname and hostname not in (ip, ""):
                    iocs["domain"].append({"indicator": hostname, "source": "urlhaus_hostname"})
            except Exception:
                pass
    return iocs
