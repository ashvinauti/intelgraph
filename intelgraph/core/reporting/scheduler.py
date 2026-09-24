from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Callable
from typing import Any

from intelgraph.core.reporting.reporters import generate_report

logger = logging.getLogger(__name__)

REPORT_DIR = os.environ.get("INTELGRAPH_REPORT_DIR", "/tmp/intelgraph/reports")


class ReportScheduler:
    """Simple scheduler that generates reports at fixed intervals using threading.Timer."""

    def __init__(self, state_path: str = ""):
        self._reports: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._running = False
        self._data_provider: Callable[[], dict[str, Any]] | None = None
        self._state_path = state_path or os.path.join(REPORT_DIR, "report_index.json")
        os.makedirs(REPORT_DIR, exist_ok=True)
        self._load()

    # ------------------------------------------------------------------
    # Report storage
    # ------------------------------------------------------------------

    def save_report(self, report: Any) -> None:
        """Save a report's metadata and write its HTML to disk."""
        rpt_id = report.report_id
        file_path = os.path.join(REPORT_DIR, f"{rpt_id}.html")
        try:
            with open(file_path, "w") as f:
                f.write(report.html_content)
        except Exception as e:
            logger.error("Failed to write report file %s: %s", file_path, e)
            return

        meta = report.to_dict()
        meta["file_path"] = file_path
        meta.pop("html_content", None)
        with self._lock:
            self._reports[rpt_id] = meta
            self._save()

    def list_reports(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(r)
                for r in sorted(
                    self._reports.values(), key=lambda r: r.get("generated_at", ""), reverse=True
                )
            ]

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._reports.get(report_id)

    def get_report_html(self, report_id: str) -> str | None:
        meta = self.get_report(report_id)
        if not meta:
            return None
        file_path = meta.get("file_path", "")
        if not file_path or not os.path.exists(file_path):
            return None
        try:
            with open(file_path) as f:
                return f.read()
        except Exception as e:
            logger.error("Failed to read report %s: %s", report_id, e)
            return None

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def set_data_provider(self, provider: Callable[[], dict[str, Any]]) -> None:
        """Set a callback that returns pipeline result data dict."""
        self._data_provider = provider

    def start(self, interval_seconds: int = 86400) -> None:
        """Start periodic report generation. Default: daily (86400s)."""
        if self._running:
            return
        self._running = True
        self._interval = interval_seconds
        self._schedule_next()

    def stop(self) -> None:
        self._running = False
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _schedule_next(self) -> None:
        if not self._running:
            return
        self._timer = threading.Timer(self._interval, self._generate_scheduled)
        self._timer.daemon = True
        self._timer.start()

    def _generate_scheduled(self) -> None:
        try:
            if self._data_provider:
                data = self._data_provider()
                if data:
                    report = generate_report("threat_summary", data)
                    self.save_report(report)
                    logger.info("Scheduled threat summary report generated: %s", report.report_id)

                    exec_report = generate_report("executive_summary", data)
                    self.save_report(exec_report)
                    logger.info(
                        "Scheduled executive summary report generated: %s", exec_report.report_id
                    )
        except Exception as e:
            logger.error("Scheduled report generation error: %s", e)
        self._schedule_next()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._state_path), exist_ok=True)
            with open(self._state_path, "w") as f:
                json.dump({"reports": list(self._reports.values())}, f, default=str)
        except Exception as e:
            logger.error("Failed to save report index: %s", e)

    def _load(self) -> None:
        try:
            if not os.path.exists(self._state_path):
                return
            with open(self._state_path) as f:
                data = json.load(f)
            for r in data.get("reports", []):
                self._reports[r["report_id"]] = r
        except Exception as e:
            logger.error("Failed to load report index: %s", e)
