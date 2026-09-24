from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class ReportType(Enum):
    THREAT_SUMMARY = "threat_summary"
    ENTITY_DETAIL = "entity_detail"
    EXECUTIVE_SUMMARY = "executive_summary"


class ReportFormat(Enum):
    HTML = "html"


@dataclass
class Report:
    report_id: str
    report_type: str
    format: str = "html"
    title: str = ""
    time_range_start: str = ""
    time_range_end: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    file_path: str = ""
    html_content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("html_content", None)
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> Report:
        return Report(**d)
