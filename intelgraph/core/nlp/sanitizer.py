from __future__ import annotations

import html
import re


class InputSanitizer:
    MAX_TEXT_LENGTH = 1_000_000

    @staticmethod
    def sanitize_text(text: str, max_length: int = MAX_TEXT_LENGTH) -> str:
        if not isinstance(text, str):
            return ""
        text = text[:max_length]
        text = text.replace("\x00", "")
        text = html.escape(text)
        return text

    @staticmethod
    def strip_html(text: str) -> str:
        clean = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", clean).strip()

    @staticmethod
    def validate_text(text: str, min_length: int = 1, max_length: int = MAX_TEXT_LENGTH) -> bool:
        if not isinstance(text, str):
            return False
        if len(text) < min_length:
            return False
        if len(text) > max_length:
            return False
        return True


class OutputSanitizer:
    @staticmethod
    def sanitize_entity_output(entities: list[dict]) -> list[dict]:
        sanitized = []
        for e in entities:
            safe = {
                "text": html.escape(e.get("text", ""))[:500],
                "label": e.get("label", "UNKNOWN"),
                "confidence": float(e.get("confidence", 0.0)),
            }
            sanitized.append(safe)
        return sanitized

    @staticmethod
    def sanitize_string(value: str, max_length: int = 1000) -> str:
        return html.escape(value)[:max_length]
