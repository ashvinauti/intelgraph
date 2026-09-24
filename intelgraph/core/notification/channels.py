from __future__ import annotations

import json
import logging
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from intelgraph.core.notification.models import NotificationChannel, NotificationEvent

logger = logging.getLogger(__name__)


def send_webhook(event: NotificationEvent, channel: NotificationChannel) -> str | None:
    url = channel.config.get("webhook_url", "")
    if not url:
        return "webhook_url not configured"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "IntelGraph-Notification/1.0",
    }
    secret = channel.config.get("secret", "")
    if secret:
        headers["X-IntelGraph-Secret"] = secret
    extra_headers = channel.config.get("headers", {})
    if isinstance(extra_headers, dict):
        headers.update(extra_headers)

    body = json.dumps(event.to_dict(), default=str).encode("utf-8")
    try:
        req = Request(url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=15) as resp:
            if resp.status >= 400:
                return f"HTTP {resp.status}: {resp.read()[:200]}"
        return None
    except URLError as e:
        return f"URLError: {e.reason}"
    except Exception as e:
        return f"Error: {e}"


def send_email(event: NotificationEvent, channel: NotificationChannel) -> str | None:
    smtp_host = channel.config.get("smtp_host", "")
    smtp_port = channel.config.get("smtp_port", 587)
    use_tls = channel.config.get("use_tls", True)
    username = channel.config.get("username", "")
    password = channel.config.get("password", "")
    from_addr = channel.config.get("from_addr", "intelgraph@localhost")
    to_addrs = channel.config.get("to_addrs", [])
    if isinstance(to_addrs, str):
        to_addrs = [a.strip() for a in to_addrs.split(",") if a.strip()]
    if not to_addrs:
        return "no recipients configured"

    html_body = _build_email_html(event)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[IntelGraph] {event.title}"
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_addrs)
    msg.attach(MIMEText(event.body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        if use_tls:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            server.starttls()
        else:
            server = (
                smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
                if smtp_port == 465
                else smtplib.SMTP(smtp_host, smtp_port, timeout=15)
            )
        if username and password:
            server.login(username, password)
        server.sendmail(from_addr, to_addrs, msg.as_string())
        server.quit()
        return None
    except Exception as e:
        return f"SMTP error: {e}"


def send_slack(event: NotificationEvent, channel: NotificationChannel) -> str | None:
    url = channel.config.get("webhook_url", "")
    if not url:
        return "webhook_url not configured"
    color_map = {"low": "#3fb950", "medium": "#d29922", "high": "#f0883e", "critical": "#ff7b72"}
    color = color_map.get(event.severity, "#8b949e")
    payload = {
        "attachments": [
            {
                "color": color,
                "title": event.title,
                "text": event.body,
                "fields": [
                    {"title": "Event Type", "value": event.event_type, "short": True},
                    {"title": "Severity", "value": event.severity, "short": True},
                    {"title": "Entity", "value": event.entity_id or "N/A", "short": True},
                ],
                "footer": "IntelGraph Notification",
                "ts": int(time.time()),
            }
        ]
    }
    headers = {"Content-Type": "application/json"}
    body = json.dumps(payload).encode("utf-8")
    try:
        req = Request(url, data=body, headers=headers, method="POST")
        with urlopen(req, timeout=15) as resp:
            if resp.status >= 400:
                return f"HTTP {resp.status}: {resp.read()[:200]}"
        return None
    except URLError as e:
        return f"URLError: {e.reason}"
    except Exception as e:
        return f"Error: {e}"


CHANNEL_DISPATCH: dict[str, Any] = {
    "webhook": send_webhook,
    "email": send_email,
    "slack": send_slack,
}


def _build_email_html(event: NotificationEvent) -> str:
    meta_rows = "".join(
        f"<tr><td style='padding:4px 8px;color:#8b949e;font-weight:600'>{k}</td>"
        f"<td style='padding:4px 8px'>{v}</td></tr>"
        for k, v in event.metadata.items()
    )
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d1117;color:#c9d1d9;padding:24px">
<div style="max-width:600px;margin:0 auto;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:24px">
<div style="font-size:22px;font-weight:700;color:#f0f6fc;margin-bottom:4px">{event.title}</div>
<div style="font-size:13px;color:#8b949e;margin-bottom:16px">{event.event_type} &middot; {event.severity} &middot; {event.timestamp[:19]}</div>
<hr style="border:none;border-top:1px solid #30363d;margin:12px 0">
<div style="font-size:14px;line-height:1.6;color:#c9d1d9;margin-bottom:16px">{event.body}</div>
<table style="width:100%;font-size:13px;border-collapse:collapse">
{meta_rows}
</table>
</div></body></html>"""
