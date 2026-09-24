from __future__ import annotations

import hashlib
import json
from typing import Any


class FeedSchema:
    def __init__(self, schema: dict[str, Any] | None = None) -> None:
        self._schema = schema or {}

    @property
    def required_fields(self) -> list[str]:
        return self._schema.get("required_fields", [])

    @property
    def field_types(self) -> dict[str, str]:
        return self._schema.get("field_types", {})

    @property
    def field_defaults(self) -> dict[str, Any]:
        return self._schema.get("field_defaults", {})

    @property
    def version(self) -> int:
        return self._schema.get("version", 1)

    def validate_entry(self, entry: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        for field in self.required_fields:
            if field not in entry or entry[field] is None or str(entry[field]).strip() == "":
                errors.append(f"Missing required field: {field}")
        for field, expected_type in self.field_types.items():
            if field in entry and entry[field] is not None:
                val = entry[field]
                if expected_type == "string" and not isinstance(val, str):
                    errors.append(f"Field '{field}' should be string, got {type(val).__name__}")
                elif expected_type == "integer" and not isinstance(val, int):
                    errors.append(f"Field '{field}' should be integer, got {type(val).__name__}")
                elif expected_type == "number" and not isinstance(val, (int, float)):
                    errors.append(f"Field '{field}' should be number, got {type(val).__name__}")
        return errors

    def apply_defaults(self, entry: dict[str, Any]) -> dict[str, Any]:
        result = dict(entry)
        for field, default in self.field_defaults.items():
            if field not in result or result[field] is None:
                result[field] = default
        return result

    def to_dict(self) -> dict[str, Any]:
        return dict(self._schema)


class FeedValidator:
    def __init__(self, schema: FeedSchema | None = None) -> None:
        self._schema = schema or FeedSchema()

    def validate(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        valid: list[dict[str, Any]] = []
        for entry in entries:
            entry = self._schema.apply_defaults(entry)
            errors = self._schema.validate_entry(entry)
            if not errors:
                valid.append(entry)
        return valid

    def validate_with_errors(
        self, entries: list[dict[str, Any]]
    ) -> list[tuple[dict[str, Any], list[str]]]:
        results: list[tuple[dict[str, Any], list[str]]] = []
        for entry in entries:
            entry = self._schema.apply_defaults(entry)
            errors = self._schema.validate_entry(entry)
            results.append((entry, errors))
        return results


class DeduplicationEngine:
    def __init__(self, key_fields: list[str] | None = None) -> None:
        self._key_fields = key_fields or ["id", "name", "source_id"]

    def _compute_fingerprint(self, entry: dict[str, Any]) -> str:
        for field in self._key_fields:
            val = entry.get(field)
            if val is not None and str(val).strip():
                raw = f"{field}:{val}".lower().strip()
                return hashlib.sha256(raw.encode()).hexdigest()
        raw = json.dumps(entry, sort_keys=True).lower()
        return hashlib.sha256(raw.encode()).hexdigest()

    def deduplicate(
        self,
        entries: list[dict[str, Any]],
        existing_fingerprints: set[str] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        seen: set[str] = set(existing_fingerprints) if existing_fingerprints else set()
        unique: list[dict[str, Any]] = []
        removed = 0
        for entry in entries:
            fp = self._compute_fingerprint(entry)
            if fp in seen:
                removed += 1
                continue
            seen.add(fp)
            unique.append(entry)
        return unique, removed

    def compute_fingerprints(self, entries: list[dict[str, Any]]) -> set[str]:
        return {self._compute_fingerprint(e) for e in entries}
