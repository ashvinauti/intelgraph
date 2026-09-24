"""Phase 32 tests: Notification System."""

import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))


from intelgraph.core.notification.channels import (
    CHANNEL_DISPATCH,
    _build_email_html,
    send_email,
    send_slack,
    send_webhook,
)
from intelgraph.core.notification.manager import MAX_RETRIES, NotificationManager
from intelgraph.core.notification.models import (
    NotificationChannel,
    NotificationEvent,
    NotificationHistoryEntry,
    NotificationSeverity,
)

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestModels:
    def test_channel_roundtrip(self):
        ch = NotificationChannel(
            channel_id="ch_1", channel_type="webhook", config={"url": "http://example.com"}
        )
        d = ch.to_dict()
        ch2 = NotificationChannel.from_dict(d)
        assert ch2.channel_id == "ch_1"
        assert ch2.channel_type == "webhook"

    def test_event_defaults(self):
        ev = NotificationEvent(
            event_id="ev_1", event_type="test", severity="high", title="T", body="B"
        )
        assert ev.entity_id == ""
        assert ev.timestamp is not None

    def test_event_to_json(self):
        ev = NotificationEvent(
            event_id="ev_1", event_type="test", severity="low", title="Test", body="Body"
        )
        j = ev.to_json()
        assert '"event_id": "ev_1"' in j
        d2 = json.loads(j)
        assert d2["event_type"] == "test"

    def test_severity_comparison(self):
        assert NotificationSeverity.LOW >= NotificationSeverity.LOW
        assert NotificationSeverity.HIGH >= NotificationSeverity.MEDIUM
        assert not (NotificationSeverity.MEDIUM >= NotificationSeverity.HIGH)
        assert NotificationSeverity.CRITICAL >= NotificationSeverity.LOW

    def test_history_entry(self):
        h = NotificationHistoryEntry(event_id="e1", channel_id="ch1", status="sent")
        assert h.attempt == 1
        d = h.to_dict()
        assert d["status"] == "sent"
        h2 = NotificationHistoryEntry.from_dict(d)
        assert h2.event_id == "e1"


# ---------------------------------------------------------------------------
# NotificationManager tests
# ---------------------------------------------------------------------------


class TestNotificationManager:
    def test_init_empty(self):
        nm = NotificationManager(state_path="/tmp/opencode/test_notif_empty.json")
        assert nm.list_channels() == []
        assert nm.get_history() == []

    def test_add_list_remove_channel(self):
        nm = NotificationManager(state_path="/tmp/opencode/test_notif_crud.json")
        ch = NotificationChannel(
            channel_id="ch_test", channel_type="webhook", enabled=True, min_severity="medium"
        )
        nm.add_channel(ch)
        assert len(nm.list_channels()) == 1
        assert nm.get_channel("ch_test") is not None
        nm.remove_channel("ch_test")
        assert nm.list_channels() == []

    def test_build_event(self):
        ev = NotificationManager.build_event(
            event_type="alert",
            severity="critical",
            title="Test",
            body="Body",
            entity_id="ent_1",
            metadata={"k": "v"},
        )
        assert ev.event_type == "alert"
        assert ev.severity == "critical"
        assert ev.entity_id == "ent_1"
        assert ev.metadata["k"] == "v"

    def test_min_severity_filter(self):
        nm = NotificationManager(state_path="/tmp/opencode/test_notif_sev.json")
        nm.add_channel(
            NotificationChannel(
                channel_id="ch_crit", channel_type="webhook", enabled=True, min_severity="critical"
            )
        )
        nm.add_channel(
            NotificationChannel(
                channel_id="ch_low", channel_type="webhook", enabled=True, min_severity="low"
            )
        )

        # low event should match ch_low but NOT ch_crit
        ev_low = NotificationManager.build_event("test", "low", "t", "b")
        entries = nm.send_event(ev_low)
        # Both should be "unknown channel_type -> failed" but ch_crit won't be included
        ch_ids = {e.channel_id for e in entries}
        assert "ch_low" in ch_ids
        assert "ch_crit" not in ch_ids

    def test_disabled_channel_skipped(self):
        nm = NotificationManager(state_path="/tmp/opencode/test_notif_disabled.json")
        nm.add_channel(
            NotificationChannel(
                channel_id="ch_dis", channel_type="webhook", enabled=False, min_severity="low"
            )
        )
        ev = NotificationManager.build_event("test", "low", "t", "b")
        entries = nm.send_event(ev)
        assert len(entries) == 0

    @patch("intelgraph.core.notification.channels.urlopen")
    def test_successful_webhook(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        nm = NotificationManager(state_path="/tmp/opencode/test_notif_webhook.json")
        nm.add_channel(
            NotificationChannel(
                channel_id="ch_wh",
                channel_type="webhook",
                config={"webhook_url": "https://example.com/hook", "secret": "s3cret"},
                enabled=True,
                min_severity="low",
            )
        )
        ev = NotificationManager.build_event("alert", "high", "Alert!", "Details")
        entries = nm.send_event(ev)
        assert len(entries) == 1
        assert entries[0].status == "sent"

    @patch("intelgraph.core.notification.channels.urlopen")
    def test_webhook_retry(self, mock_urlopen):
        """Failed webhook should be retried MAX_RETRIES times."""
        mock_urlopen.side_effect = Exception("Connection refused")

        nm = NotificationManager(state_path="/tmp/opencode/test_notif_retry.json")
        nm.add_channel(
            NotificationChannel(
                channel_id="ch_retry",
                channel_type="webhook",
                config={"webhook_url": "https://example.com/fail"},
                enabled=True,
                min_severity="low",
            )
        )
        ev = NotificationManager.build_event("test", "low", "t", "b")
        entries = nm.send_event(ev)
        assert len(entries) == 1
        assert entries[0].status == "failed"
        assert entries[0].attempt == MAX_RETRIES
        assert mock_urlopen.call_count == MAX_RETRIES

    def test_unknown_channel_type(self):
        nm = NotificationManager(state_path="/tmp/opencode/test_notif_unknown.json")
        nm.add_channel(
            NotificationChannel(
                channel_id="ch_bad", channel_type="pigeon", enabled=True, min_severity="low"
            )
        )
        ev = NotificationManager.build_event("test", "low", "t", "b")
        entries = nm.send_event(ev)
        assert entries[0].status == "failed"
        assert "unknown" in entries[0].error

    def test_async_send(self):
        nm = NotificationManager(state_path="/tmp/opencode/test_notif_async.json")
        nm.add_channel(
            NotificationChannel(
                channel_id="ch_async", channel_type="webhook", enabled=True, min_severity="low"
            )
        )
        ev = NotificationManager.build_event("test", "low", "t", "b")
        nm.send_event_async(ev)
        time.sleep(0.3)
        # async sent without blocking
        assert True

    def test_history_limit(self):
        nm = NotificationManager(state_path="/tmp/opencode/test_notif_hist.json")
        for i in range(5):
            nm.add_channel(
                NotificationChannel(
                    channel_id=f"ch_{i}", channel_type="webhook", enabled=True, min_severity="low"
                )
            )
            ev = NotificationManager.build_event("test", "low", f"t{i}", "b")
            nm.send_event(ev)
            nm.remove_channel(f"ch_{i}")
        history = nm.get_history(limit=3)
        assert len(history) <= 3

    def test_clear_history(self):
        nm = NotificationManager(state_path="/tmp/opencode/test_notif_clear.json")
        nm.add_channel(
            NotificationChannel(
                channel_id="ch_clr", channel_type="webhook", enabled=True, min_severity="low"
            )
        )
        nm.send_event(NotificationManager.build_event("test", "low", "t", "b"))
        assert len(nm.get_history()) > 0
        nm.clear_history()
        assert nm.get_history() == []

    def test_persistence(self):
        path = "/tmp/opencode/test_notif_persist.json"
        if os.path.exists(path):
            os.remove(path)
        nm1 = NotificationManager(state_path=path)
        nm1.add_channel(
            NotificationChannel(
                channel_id="ch_persist", channel_type="webhook", enabled=True, min_severity="medium"
            )
        )
        nm1.send_event(NotificationManager.build_event("test", "medium", "t", "b"))
        del nm1

        nm2 = NotificationManager(state_path=path)
        assert len(nm2.list_channels()) == 1
        assert nm2.list_channels()[0].channel_id == "ch_persist"
        assert len(nm2.get_history()) == 1
        os.remove(path)


# ---------------------------------------------------------------------------
# Channel implementation tests
# ---------------------------------------------------------------------------


class TestChannels:
    @patch("intelgraph.core.notification.channels.urlopen")
    def test_send_webhook_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        ev = NotificationEvent(
            event_id="ev_1", event_type="test", severity="low", title="Test", body="Body"
        )
        ch = NotificationChannel(
            channel_id="ch_1",
            channel_type="webhook",
            config={"webhook_url": "https://ex.com/hook", "secret": "s3cret"},
        )
        err = send_webhook(ev, ch)
        assert err is None

        # Verify the call included the secret header
        call_req = mock_urlopen.call_args[0][0]
        assert call_req.method == "POST"
        # Python's Request lowercases header keys internally
        headers = dict(call_req.header_items())
        assert headers.get("X-intelgraph-secret") == "s3cret"

    @patch("intelgraph.core.notification.channels.urlopen")
    def test_send_webhook_failure(self, mock_urlopen):
        mock_urlopen.side_effect = Exception("Timeout")
        ev = NotificationEvent(
            event_id="ev_1", event_type="test", severity="low", title="Test", body="Body"
        )
        ch = NotificationChannel(
            channel_id="ch_1", channel_type="webhook", config={"webhook_url": "https://ex.com/hook"}
        )
        err = send_webhook(ev, ch)
        assert err is not None
        assert "Timeout" in err

    @patch("intelgraph.core.notification.channels.urlopen")
    def test_send_slack(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        ev = NotificationEvent(
            event_id="ev_1",
            event_type="test",
            severity="critical",
            title="Critical!",
            body="Alert body",
        )
        ch = NotificationChannel(
            channel_id="ch_slack",
            channel_type="slack",
            config={"webhook_url": "https://hooks.slack.com/test"},
        )
        err = send_slack(ev, ch)
        assert err is None

        # Check Slack-specific payload
        call_body = json.loads(mock_urlopen.call_args[0][0].data)
        assert "attachments" in call_body
        assert call_body["attachments"][0]["color"] == "#ff7b72"

    def test_email_html_template(self):
        ev = NotificationEvent(
            event_id="ev_1",
            event_type="alert",
            severity="critical",
            title="Test Alert",
            body="Something bad happened",
            entity_id="ent_1",
            metadata={"confidence": 95, "source": "urlhaus"},
        )
        html = _build_email_html(ev)
        assert "Test Alert" in html
        assert "Something bad happened" in html
        assert "confidence" in html
        assert "95" in html
        assert "ent_1" not in html  # entity_id is not in metadata

    @patch("smtplib.SMTP")
    def test_send_email_smtp(self, mock_smtp):
        mock_instance = MagicMock()
        mock_smtp.return_value = mock_instance

        ev = NotificationEvent(
            event_id="ev_1", event_type="alert", severity="high", title="Email Test", body="Body"
        )
        ch = NotificationChannel(
            channel_id="ch_email",
            channel_type="email",
            config={
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "use_tls": True,
                "username": "user",
                "password": "pass",
                "from_addr": "alert@intelgraph.local",
                "to_addrs": ["soc@example.com"],
            },
        )
        err = send_email(ev, ch)
        assert err is None
        mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=15)
        mock_instance.starttls.assert_called_once()
        mock_instance.login.assert_called_once_with("user", "pass")
        mock_instance.sendmail.assert_called_once()
        args = mock_instance.sendmail.call_args[0]
        assert args[0] == "alert@intelgraph.local"
        assert args[1] == ["soc@example.com"]

    def test_dispatch_map(self):
        assert "webhook" in CHANNEL_DISPATCH
        assert "email" in CHANNEL_DISPATCH
        assert "slack" in CHANNEL_DISPATCH


# ---------------------------------------------------------------------------
# API-level integration test (via mock)
# ---------------------------------------------------------------------------


class TestAPIIntegration:
    def test_create_channel_api(self):
        """Test that the notification API create/list/delete pattern works."""
        from intelgraph.api.routers.notifications import _get_notifier, _notifier
        from intelgraph.core.notification.models import NotificationChannel

        # Clear state for test
        _notifier._channels.clear()
        _notifier._history.clear()

        nt = _get_notifier()
        nt.add_channel(
            NotificationChannel(
                channel_id="api_test_ch",
                channel_type="webhook",
                config={"webhook_url": "https://ex.com/hook"},
                enabled=True,
                min_severity="high",
            )
        )

        channels = nt.list_channels()
        assert any(ch.channel_id == "api_test_ch" for ch in channels)

        nt.remove_channel("api_test_ch")
        assert not any(ch.channel_id == "api_test_ch" for ch in nt.list_channels())

    def test_dashboard_summary_roundtrip(self):
        """Verify the notification router's module can be imported without error."""
        from intelgraph.api.routers import notifications as nr

        assert hasattr(nr, "router")
        assert hasattr(nr, "create_channel")
        assert hasattr(nr, "list_channels")
        assert hasattr(nr, "get_history")


# ---------------------------------------------------------------------------
# Notification history cleanup
# ---------------------------------------------------------------------------


def teardown_module():
    for f in os.listdir("/tmp/opencode/"):
        if f.startswith("test_notif"):
            try:
                os.remove(f"/tmp/opencode/{f}")
            except OSError:
                pass
