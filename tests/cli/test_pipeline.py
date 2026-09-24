from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from click.testing import CliRunner

from intelgraph.cli.pipeline import pipeline_run

SAMPLE_URLHAUS_CSV = (
    "# comment line\n"
    '1,2026-01-01,"http://evil-c2.example.com/payload.exe",online,malware_download,,,,,\n'
    '2,2026-01-01,"http://185.220.101.5/drop.bin",online,malware_download,,,,,\n'
)


def _fake_urlhaus_response():
    resp = MagicMock()
    resp.text = SAMPLE_URLHAUS_CSV
    resp.raise_for_status = MagicMock()
    return resp


def _fake_feed_response():
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    return resp


class TestPipelineRun:
    def test_no_feed_skips_otx_without_key(self, monkeypatch):
        monkeypatch.delenv("OTX_API_KEY", raising=False)
        with patch("intelgraph.cli.pipeline.httpx.get", return_value=_fake_urlhaus_response()):
            runner = CliRunner()
            result = runner.invoke(pipeline_run, ["--no-feed", "--urlhaus-limit", "10"])
        assert result.exit_code == 0, result.output
        assert "skipped (OTX_API_KEY not set)" in result.output
        assert '"sources": 1' in result.output

    def test_feeds_running_server(self, monkeypatch):
        monkeypatch.delenv("OTX_API_KEY", raising=False)
        with (
            patch("intelgraph.cli.pipeline.httpx.get", return_value=_fake_urlhaus_response()),
            patch(
                "intelgraph.cli.pipeline.httpx.post", return_value=_fake_feed_response()
            ) as mock_post,
        ):
            runner = CliRunner()
            result = runner.invoke(
                pipeline_run, ["--base-url", "http://localhost:9999", "--urlhaus-limit", "10"]
            )
        assert result.exit_code == 0, result.output
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://localhost:9999/dashboard/feed"
        payload = kwargs["json"]
        assert "result" in payload
        assert payload["sources"]["URLhaus"]["iocs"] == 2
        assert "Done. Open http://localhost:9999/ to view the dashboard." in result.output

    def test_skip_urlhaus_with_file_source(self, monkeypatch, tmp_path):
        monkeypatch.delenv("OTX_API_KEY", raising=False)
        sample = tmp_path / "synthetic.txt"
        sample.write_text("Malicious host at 203.0.113.44 (example.com) hosting invoice.exe")

        with (
            patch("intelgraph.cli.pipeline.httpx.get") as mock_get,
            patch(
                "intelgraph.cli.pipeline.httpx.post", return_value=_fake_feed_response()
            ) as mock_post,
        ):
            runner = CliRunner()
            result = runner.invoke(
                pipeline_run, ["--skip-urlhaus", "--file", str(sample)]
            )
        assert result.exit_code == 0, result.output
        mock_get.assert_not_called()
        assert "Skipping URLhaus (--skip-urlhaus)" in result.output
        assert f"Loaded 1 local file source(s): {sample}" in result.output
        payload = mock_post.call_args.kwargs["json"]
        assert "URLhaus" not in payload["sources"]
        assert payload["sources"]["Files"]["count"] == 1

    def test_urlhaus_csv_file_used_instead_of_live_fetch(self, monkeypatch, tmp_path):
        monkeypatch.delenv("OTX_API_KEY", raising=False)
        csv_path = tmp_path / "urlhaus_recent.csv"
        csv_path.write_text(SAMPLE_URLHAUS_CSV)

        with (
            patch("intelgraph.cli.pipeline.httpx.get") as mock_get,
            patch(
                "intelgraph.cli.pipeline.httpx.post", return_value=_fake_feed_response()
            ) as mock_post,
        ):
            runner = CliRunner()
            result = runner.invoke(
                pipeline_run, ["--urlhaus-csv", str(csv_path), "--urlhaus-limit", "10"]
            )
        assert result.exit_code == 0, result.output
        mock_get.assert_not_called()
        assert f"Loading URLhaus CSV from {csv_path}" in result.output
        payload = mock_post.call_args.kwargs["json"]
        assert payload["sources"]["URLhaus"]["iocs"] == 2

    def test_urlhaus_csv_conflicts_with_skip_urlhaus(self, tmp_path):
        csv_path = tmp_path / "urlhaus_recent.csv"
        csv_path.write_text(SAMPLE_URLHAUS_CSV)
        runner = CliRunner()
        result = runner.invoke(
            pipeline_run, ["--skip-urlhaus", "--urlhaus-csv", str(csv_path)]
        )
        assert result.exit_code != 0
        assert "conflict" in result.output

    def test_server_not_running_gives_friendly_error(self, monkeypatch):
        monkeypatch.delenv("OTX_API_KEY", raising=False)
        with (
            patch("intelgraph.cli.pipeline.httpx.get", return_value=_fake_urlhaus_response()),
            patch(
                "intelgraph.cli.pipeline.httpx.post",
                side_effect=httpx.ConnectError("Connection refused"),
            ),
        ):
            runner = CliRunner()
            result = runner.invoke(
                pipeline_run, ["--base-url", "http://localhost:9999", "--urlhaus-limit", "10"]
            )
        assert result.exit_code != 0
        assert "Could not reach http://localhost:9999" in result.output
        assert "uv run uvicorn intelgraph.api.main:app --reload" in result.output
        assert "Traceback" not in result.output

    def test_no_sources_errors(self, monkeypatch):
        monkeypatch.delenv("OTX_API_KEY", raising=False)
        runner = CliRunner()
        result = runner.invoke(pipeline_run, ["--skip-urlhaus"])
        assert result.exit_code != 0
        assert "No sources to run" in result.output

    def test_otx_included_when_key_set(self, monkeypatch):
        monkeypatch.setenv("OTX_API_KEY", "fake-key")
        fake_pulse = SimpleNamespace(
            to_source_dict=lambda: {"id": "otx_1", "name": "OTX Pulse: test", "text": "x", "value": 75}
        )
        fake_client = MagicMock()
        fake_client.get_pulses.return_value = [fake_pulse]
        fake_client.extract_iocs.return_value = {"IPv4": [{"indicator": "1.2.3.4"}]}
        with (
            patch("intelgraph.cli.pipeline.httpx.get", return_value=_fake_urlhaus_response()),
            patch("intelgraph.cli.pipeline.httpx.post", return_value=_fake_feed_response()),
            patch("intelgraph.core.source.otx.OtxClient", return_value=fake_client),
        ):
            runner = CliRunner()
            result = runner.invoke(pipeline_run, ["--urlhaus-limit", "10", "--otx-pulses", "1"])
        assert result.exit_code == 0, result.output
        assert "1 pulses, 1 IOCs" in result.output
