from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from intelgraph.cli.simulate import simulate_network


class TestSimulateNetwork:
    def test_prints_text_to_stdout(self):
        runner = CliRunner()
        result = runner.invoke(simulate_network, ["--seed", "1", "--campaigns", "2"])
        assert result.exit_code == 0, result.output
        assert "SYNTHETIC" in result.output
        assert "## Campaign" in result.output

    def test_writes_text_and_json_with_format_both(self, tmp_path):
        out = tmp_path / "sim"
        runner = CliRunner()
        result = runner.invoke(
            simulate_network,
            ["--seed", "2", "--campaigns", "2", "--format", "both", "-o", str(out)],
        )
        assert result.exit_code == 0, result.output
        text = (tmp_path / "sim.txt").read_text()
        manifest = json.loads((tmp_path / "sim.json").read_text())
        assert "## Campaign" in text
        assert manifest["synthetic"] is True
        assert manifest["config"]["seed"] == 2

    def test_deterministic_output(self):
        runner = CliRunner()
        a = runner.invoke(simulate_network, ["--seed", "42"]).output
        b = runner.invoke(simulate_network, ["--seed", "42"]).output
        assert a == b

    def test_rejects_bad_config(self):
        runner = CliRunner()
        result = runner.invoke(simulate_network, ["--campaigns", "0"])
        assert result.exit_code != 0
        assert "campaigns must be" in result.output

    def test_feed_runs_pipeline_and_posts(self):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.raise_for_status = MagicMock()
        with patch("intelgraph.cli.simulate.httpx.post", return_value=fake_resp) as mock_post:
            runner = CliRunner()
            result = runner.invoke(
                simulate_network,
                ["--seed", "3", "--campaigns", "2", "--feed", "--base-url", "http://server:8000"],
            )
        assert result.exit_code == 0, result.output
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://server:8000/dashboard/feed"
        payload = kwargs["json"]
        assert "result" in payload
        assert payload["sources"]["Simulation"]["campaigns"] == 2
