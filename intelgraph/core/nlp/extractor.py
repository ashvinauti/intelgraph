from __future__ import annotations

import bisect
import ipaddress
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from intelgraph.core.nlp._tlds import AMBIGUOUS_EXTS, FILENAME_EXTS, IANA_TLDS

NLP_SCHEMA_VERSION = "1.0"


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    result = []
    for part in parts:
        stripped = part.strip().rstrip(".!?")
        if stripped:
            result.append(stripped)
    if not result and text.strip():
        result = [text.strip()]
    return result


# ---------------------------------------------------------------------------
# Entity patterns for rule-based NER
# ---------------------------------------------------------------------------

IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# IPv6 pattern — handles full, compressed (::), IPv4-mapped, loopback, and zone IDs.
_H = r"[0-9a-fA-F]{1,4}"
_V4 = r"(?:\d{1,3}\.){3}\d{1,3}"
_HEX_SEQ = rf"{_H}(?::{_H})*"
_HEX_SEQ_OPT = rf"(?:{_HEX_SEQ})?"
IPV6_RE = re.compile(
    r"(?<![:.\w])(?:"
    rf"(?:{_H}:){{7}}{_H}"  # 1. full 8-group
    rf"|(?:{_H}:){{6}}{_V4}"  # 2. full 6-group + IPv4 tail
    rf"|{_HEX_SEQ_OPT}::{_HEX_SEQ_OPT}"  # 3. compressed :: (hex only)
    rf"|{_HEX_SEQ_OPT}::(?:(?:{_H}:)*){_V4}"  # 4. compressed :: + IPv4 tail
    r")"
    r"(?:%[a-zA-Z0-9_]+)?"  # zone ID (e.g. %eth0)
    r"(?![:.\w])",
    re.IGNORECASE,
)
DOMAIN_RE = re.compile(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b")
CVE_RE = re.compile(r"\bCVE-\d{4}-\d{4,7}\b", re.IGNORECASE)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
URL_RE = re.compile(r'\bhttps?://[^\s<>"\'\]\[]+', re.IGNORECASE)
MD5_RE = re.compile(r"\b[a-fA-F0-9]{32}\b")
SHA1_RE = re.compile(r"\b[a-fA-F0-9]{40}\b")
SHA256_RE = re.compile(r"\b[a-fA-F0-9]{64}\b")
MALWARE_KEYWORDS = [
    "trojan",
    "ransomware",
    "worm",
    "backdoor",
    "dropper",
    "rootkit",
    "keylogger",
    "spyware",
    "adware",
    "botnet",
    "virus",
    "malware",
    "loader",
    "stealer",
    "infostealer",
    "rat",
    "webshell",
]
ORG_KEYWORDS = ["inc", "corp", "ltd", "llc", "gmbh", "group", "organization", "department"]
PERSON_TITLE_RE = re.compile(r"\b(Mr\.|Ms\.|Mrs\.|Dr\.|Prof\.|Capt\.|Gen\.)\s+([A-Z][a-z]+)\b")
ORG_RE = re.compile(
    r"\b[A-Z][a-zA-Z]+(?:[-\s][A-Z][a-zA-Z]+)*(?:\s(?:Inc|Corp|Ltd|LLC|Group|Organization|Department))\b"
)


@dataclass
class ExtractedEntity:
    text: str
    label: str
    start: int
    end: int
    confidence: float
    normalized: str = ""
    source: str = "rule-based"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "label": self.label,
            "start": self.start,
            "end": self.end,
            "confidence": round(self.confidence, 4),
            "normalized": self.normalized or self.text,
            "source": self.source,
        }

    def to_contradiction_dict(self, context: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "entity": self.normalized or self.text,
            "attribute": self.label,
            "value": (context or {}).get("value", 50),
            "confidence": self.confidence,
            "source": (context or {}).get("source", self.source),
            "context": (context or {}).get("context", self.text),
            "collected_at": (context or {}).get("collected_at"),
        }


@dataclass
class ExtractedRelationship:
    subject: str
    relation: str
    obj: str
    confidence: float
    sentence: str = ""
    source_entity: ExtractedEntity | None = None
    target_entity: ExtractedEntity | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": self.subject,
            "relation": self.relation,
            "object": self.obj,
            "confidence": round(self.confidence, 4),
            "sentence": self.sentence,
            "source": self.source_entity.to_dict() if self.source_entity else None,
            "target": self.target_entity.to_dict() if self.target_entity else None,
        }


@dataclass
class ExtractedEvent:
    event_type: str
    trigger_word: str
    actors: list[str]
    actions: list[str]
    targets: list[str]
    timestamp: str = ""
    confidence: float = 0.5
    sentence: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "trigger_word": self.trigger_word,
            "actors": self.actors,
            "actions": self.actions,
            "targets": self.targets,
            "timestamp": self.timestamp,
            "confidence": round(self.confidence, 4),
            "sentence": self.sentence,
        }


# ---------------------------------------------------------------------------
# NER Engine
# ---------------------------------------------------------------------------


class NEREngine:
    def __init__(self) -> None:
        self._patterns: dict[str, list[tuple[re.Pattern, str, float]]] = {
            "IP": [(IP_RE, "IP", 0.95), (IPV6_RE, "IP", 0.95)],
            "DOMAIN": [(DOMAIN_RE, "DOMAIN", 0.9)],
            "CVE": [(CVE_RE, "CVE", 0.98)],
            "EMAIL": [(EMAIL_RE, "EMAIL", 0.95)],
            "URL": [(URL_RE, "URL", 0.9)],
            "HASH_MD5": [(MD5_RE, "HASH_MD5", 0.95)],
            "HASH_SHA1": [(SHA1_RE, "HASH_SHA1", 0.95)],
            "HASH_SHA256": [(SHA256_RE, "HASH_SHA256", 0.95)],
            "MALWARE": [
                (re.compile(r"\b" + kw + r"\b", re.IGNORECASE), "MALWARE", 0.85)
                for kw in MALWARE_KEYWORDS
            ],
            "PERSON": [(PERSON_TITLE_RE, "PERSON", 0.7)],
            "ORGANIZATION": [(ORG_RE, "ORGANIZATION", 0.65)],
        }

    # Keywords used by _classify_ip_match to detect version-number context.
    # These words *immediately* precede the dotted-decimal match (e.g. "before 2.2.3.1").
    _VERSION_KEYWORDS = (
        "version",
        "s\u00fcr\u00fcm",
        "release",
        "build",
        "update",
        "patch",
        "before",
        "after",
        "prior to",
        "up to",
        "through",
        "starting from",
        "fixed in",
        "patched in",
        "updated to",
        "affects",
        "impacts",
        "firmware",
    )
    # Operators that appear immediately before a version number (e.g. "<= 2.2.3.1").
    _VERSION_OPERATORS = ("<=", ">=", "<", ">", "=")

    # Strong IP indicators appearing anywhere in the context window.
    _IP_SIGNALS = (
        "http://",
        "https://",
        "://",
        "ip address",
        "ip:",
        "host:",
        "host ",
        "observed",
        "connect",
        "c2",
        "c&c",
        "src=",
        "dst=",
        "source:",
        "destination:",
        "victim",
        "infected",
        "scan",
        "server ",
        "address ",
        "host. ",
    )

    def _classify_ip_match(
        self,
        match_str: str,
        text: str,
        start: int,
        end: int,
        inside_url: bool,
    ) -> tuple[str, float]:
        """Classify an IP-regex match as 'IP' or 'VERSION'.

        For IPv6 (contains ':'), version-number confusion is impossible —
        colons never appear in dotted-decimal version strings.  We still
        validate with the stdlib *ipaddress* module to reject regex
        false-positives (e.g. 9-group sequences that the broad regex
        might accept).

        For IPv4, the existing reliability hierarchy applies:
          1. Octet range > 255  -> VERSION (definitive, no real IP has octet > 255)
          2. Inside URL span    -> IP (the URL host is an IP)
          3. Context keywords:
             * version keyword immediately before the match  -> VERSION
             * IP keyword in window OR ':<port>' after        -> IP
             * conflicting signals                            -> IP (common case in threat intel)
             * no clear signal                              -> IP (default, conservative)
        Range check alone is intentionally insufficient (2.2.3.1 is a valid IPv4 octet range),
        matching the Phase 13 requirement that context checking is mandatory.
        """
        # ── IPv6 path ──
        if ":" in match_str:
            addr = match_str.split("%")[0]
            try:
                ipaddress.IPv6Address(addr)
            except (ipaddress.AddressValueError, ValueError):
                return "UNKNOWN", 0.3
            if inside_url:
                return "IP", 0.95
            return "IP", 0.9

        # ── IPv4 path (existing logic) ──
        octets = match_str.split(".")
        if any(int(o) > 255 for o in octets):
            return "VERSION", 0.95

        if inside_url:
            return "IP", 0.95

        window_before = 60
        window_after = 30
        before = text[max(0, start - window_before) : start].lower()
        after = text[end : min(len(text), end + window_after)].lower()

        before_stripped = before.rstrip()

        has_version = False
        for kw in self._VERSION_KEYWORDS:
            if before_stripped.endswith(kw):
                has_version = True
                break
        if not has_version:
            for op in self._VERSION_OPERATORS:
                if before_stripped.endswith(op):
                    has_version = True
                    break
        if not has_version:
            # Single-letter "v"/"V" prefix (e.g. "v 1.2.3.4", "V.2.0.0.1")
            if re.search(r"\bv\.?\s*$", before_stripped[-15:]):
                has_version = True

        has_ip = False
        for sig in self._IP_SIGNALS:
            if sig in before or sig in after:
                has_ip = True
                break
        if re.match(r"^:\d{1,5}\b", after):
            has_ip = True

        if has_version and not has_ip:
            return "VERSION", 0.85
        if has_ip and not has_version:
            return "IP", 0.9
        if has_version and has_ip:
            return "IP", 0.65
        return "IP", 0.85

    def _classify_domain_match(
        self,
        match_str: str,
        inside_url: bool,
        known_hostnames: set[str],
    ) -> tuple[str, float]:
        labels = match_str.split(".")
        tld = labels[-1].lower()

        if match_str.lower() in known_hostnames:
            return "DOMAIN", 0.95

        if inside_url:
            if tld in FILENAME_EXTS:
                return "FILENAME", 0.85
            if tld in IANA_TLDS:
                return "DOMAIN", 0.5
            return "UNKNOWN", 0.3

        if tld in AMBIGUOUS_EXTS:
            return "FILENAME", 0.5
        if tld in IANA_TLDS:
            return "DOMAIN", 0.9
        if tld in FILENAME_EXTS:
            return "FILENAME", 0.5
        return "UNKNOWN", 0.5

    def extract(self, text: str) -> list[ExtractedEntity]:
        entities: list[ExtractedEntity] = []
        seen: set[tuple[int, int]] = set()
        url_spans: list[tuple[int, int]] = []
        known_hostnames: set[str] = set()

        # Pre-process URL matches to build hostname context
        for pattern, label, confidence in [(URL_RE, "URL", 0.9)]:
            for match in pattern.finditer(text):
                span = (match.start(), match.end())
                if span in seen:
                    continue
                seen.add(span)
                url_spans.append(span)
                entities.append(
                    ExtractedEntity(
                        text=match.group(),
                        label=label,
                        start=match.start(),
                        end=match.end(),
                        confidence=confidence,
                        normalized=match.group().lower(),
                    )
                )
                try:
                    parsed = urlparse(match.group())
                    hostname = (parsed.hostname or "").lower()
                    if hostname:
                        known_hostnames.add(hostname)
                except Exception:
                    pass

        # Sort url_spans by start position for binary search
        url_spans.sort(key=lambda s: s[0])

        # Main pass: all patterns (skip URL — already handled)
        for category, pattern_list in self._patterns.items():
            if category == "URL":
                continue
            for pattern, label, confidence in pattern_list:
                for match in pattern.finditer(text):
                    span = (match.start(), match.end())
                    if span in seen:
                        continue
                    seen.add(span)

                    effective_label = label
                    effective_conf = confidence

                    if label == "DOMAIN":
                        pos = match.start()
                        idx = bisect.bisect_right(url_spans, (pos, float("inf"))) - 1
                        inside = False
                        if idx >= 0:
                            us = url_spans[idx]
                            inside = us[0] <= pos and match.end() <= us[1]
                        effective_label, effective_conf = self._classify_domain_match(
                            match.group(),
                            inside,
                            known_hostnames,
                        )
                    elif label == "IP":
                        pos = match.start()
                        idx = bisect.bisect_right(url_spans, (pos, float("inf"))) - 1
                        inside = False
                        if idx >= 0:
                            us = url_spans[idx]
                            inside = us[0] <= pos and match.end() <= us[1]
                        effective_label, effective_conf = self._classify_ip_match(
                            match.group(),
                            text,
                            match.start(),
                            match.end(),
                            inside,
                        )

                    entities.append(
                        ExtractedEntity(
                            text=match.group(),
                            label=effective_label,
                            start=match.start(),
                            end=match.end(),
                            confidence=effective_conf,
                            normalized=match.group().lower(),
                        )
                    )

        entities.sort(key=lambda e: e.start)
        return entities


# ---------------------------------------------------------------------------
# Relationship Extraction Engine
# ---------------------------------------------------------------------------


class RelationshipExtractor:
    def __init__(self, min_confidence: float = 0.0) -> None:
        self._min_confidence = min_confidence
        self._verb_patterns: list[tuple[re.Pattern, str]] = [
            (
                re.compile(
                    r"\b(connected to|linked to|communicates with|uses|exploits|targets|attacks)\b",
                    re.IGNORECASE,
                ),
                "connects_to",
            ),
            (re.compile(r"\b(owns|controls|manages|operates|hosts|runs)\b", re.IGNORECASE), "owns"),
            (re.compile(r"\b(contains|includes|has|possesses)\b", re.IGNORECASE), "contains"),
            (
                re.compile(r"\b(related to|associated with|part of|member of)\b", re.IGNORECASE),
                "associated_with",
            ),
            (
                re.compile(r"\b(authenticates|logs in|accesses|connects)\b", re.IGNORECASE),
                "accesses",
            ),
            (
                re.compile(r"\b(downloads|uploads|sends|receives|transmits)\b", re.IGNORECASE),
                "transfers_to",
            ),
        ]

    def extract(
        self, text: str, entities: list[ExtractedEntity] | None = None
    ) -> list[ExtractedRelationship]:
        relationships: list[ExtractedRelationship] = []
        sentences = _split_sentences(text)
        for sentence in sentences:
            for verb_pattern, rel_type in self._verb_patterns:
                match = verb_pattern.search(sentence)
                if not match:
                    continue
                before = sentence[: match.start()].strip()
                after = sentence[match.end() :].strip()
                if entities:
                    before_ents = [e for e in entities if before.rfind(e.text) >= 0]
                    after_ents = [e for e in entities if after.find(e.text) >= 0]
                    if before_ents and after_ents:
                        relationships.append(
                            ExtractedRelationship(
                                subject=before_ents[-1].text,
                                relation=rel_type,
                                obj=after_ents[0].text,
                                confidence=0.6,
                                sentence=sentence,
                                source_entity=before_ents[-1],
                                target_entity=after_ents[0],
                            )
                        )
            # Phase 10.2: Same-sentence co-occurrence — CVE↔IP/Domain pairs
            if entities:
                sent_ents = [e for e in entities if sentence.find(e.text) >= 0]
                cve_ents = [e for e in sent_ents if e.label == "CVE"]
                other_ents = [e for e in sent_ents if e.label in ("IP", "DOMAIN", "URL", "EMAIL")]
                if cve_ents and other_ents:
                    for ce in cve_ents:
                        for oe in other_ents:
                            if not any(
                                r.subject == ce.text and r.obj == oe.text for r in relationships
                            ):
                                relationships.append(
                                    ExtractedRelationship(
                                        subject=ce.text,
                                        relation="related_to",
                                        obj=oe.text,
                                        confidence=0.5,
                                        sentence=sentence,
                                        source_entity=ce,
                                        target_entity=oe,
                                    )
                                )
        # Phase 10.2: Document-level co-occurrence — CVE↔IP/Domain across sentences
        if entities:
            doc_cve = [e for e in entities if e.label == "CVE"]
            doc_other = [e for e in entities if e.label in ("IP", "DOMAIN")]
            if doc_cve and doc_other:
                for ce in doc_cve:
                    for oe in doc_other:
                        if not any(
                            r.subject == ce.text and r.obj == oe.text for r in relationships
                        ):
                            relationships.append(
                                ExtractedRelationship(
                                    subject=ce.text,
                                    relation="related_to",
                                    obj=oe.text,
                                    confidence=0.35,
                                    sentence="",
                                    source_entity=ce,
                                    target_entity=oe,
                                )
                            )
        # Filter by min_confidence
        if self._min_confidence > 0:
            relationships = [r for r in relationships if r.confidence >= self._min_confidence]
        return relationships


# ---------------------------------------------------------------------------
# Event Extraction Engine
# ---------------------------------------------------------------------------

TRIGGER_EVENTS: dict[str, list[str]] = {
    "breach": ["breach", "compromise", "intrusion", "hack", "infiltrate", "penetrate"],
    "infection": ["infect", "malware", "ransomware", "trojan", "worm"],
    "exfiltration": ["exfiltrate", "steal", "leak", "data breach", "dump"],
    "phishing": ["phishing", "spear", "social engineering", "fraudulent email"],
    "ddos": ["ddos", "flood", "amplification", "overload"],
    "exploit": ["exploit", "vulnerability", "cve", "zero-day", "0day"],
    "lateral_movement": ["lateral", "pivot", "spread", "propagate"],
    "privilege_escalation": ["escalate", "privilege", "admin access", "elevate"],
}


class EventExtractor:
    def extract(
        self, text: str, entities: list[ExtractedEntity] | None = None
    ) -> list[ExtractedEvent]:
        events: list[ExtractedEvent] = []
        sentences = _split_sentences(text)
        for sentence in sentences:
            for event_type, triggers in TRIGGER_EVENTS.items():
                for trigger in triggers:
                    if re.search(r"\b" + trigger + r"\b", sentence, re.IGNORECASE):
                        sentence.split()
                        actors = [
                            e.text
                            for e in (entities or [])
                            if sentence.find(e.text) >= 0
                            and e.label in ("PERSON", "ORGANIZATION", "IP", "DOMAIN")
                        ]
                        targets = [
                            e.text
                            for e in (entities or [])
                            if sentence.find(e.text) >= 0
                            and e.label in ("IP", "DOMAIN", "CVE", "URL")
                        ]
                        events.append(
                            ExtractedEvent(
                                event_type=event_type,
                                trigger_word=trigger,
                                actors=actors,
                                actions=[trigger],
                                targets=targets,
                                confidence=0.7,
                                sentence=sentence,
                            )
                        )
                        break
        return events


# ---------------------------------------------------------------------------
# Text Classifier
# ---------------------------------------------------------------------------

THREAT_TYPE_PATTERNS: dict[str, list[tuple[re.Pattern, float]]] = {
    "malware": [(re.compile(r"\b" + kw + r"\b", re.IGNORECASE), 0.8) for kw in MALWARE_KEYWORDS],
    "phishing": [
        (re.compile(r"\bphish", re.IGNORECASE), 0.9),
        (re.compile(r"\bsocial engineering\b", re.IGNORECASE), 0.85),
    ],
    "vulnerability": [
        (re.compile(r"\bcve-\d", re.IGNORECASE), 0.95),
        (re.compile(r"\bvulnerability\b", re.IGNORECASE), 0.7),
        (re.compile(r"\bzero.day\b", re.IGNORECASE), 0.85),
    ],
    "network_attack": [
        (re.compile(r"\bddos\b", re.IGNORECASE), 0.9),
        (re.compile(r"\bport scan\b", re.IGNORECASE), 0.8),
        (re.compile(r"\bintrusion\b", re.IGNORECASE), 0.75),
    ],
    "data_breach": [
        (re.compile(r"\bbreach\b", re.IGNORECASE), 0.85),
        (re.compile(r"\bleak\b", re.IGNORECASE), 0.7),
        (re.compile(r"\bexfiltrat", re.IGNORECASE), 0.9),
    ],
}

SEVERITY_PATTERNS: dict[str, list[tuple[re.Pattern, float]]] = {
    "critical": [
        (re.compile(r"\bcritical\b", re.IGNORECASE), 0.9),
        (re.compile(r"\bsevere\b", re.IGNORECASE), 0.85),
        (re.compile(r"\bemergency\b", re.IGNORECASE), 0.95),
    ],
    "high": [
        (re.compile(r"\bhigh\b", re.IGNORECASE), 0.8),
        (re.compile(r"\bdangerous\b", re.IGNORECASE), 0.75),
    ],
    "medium": [
        (re.compile(r"\bmedium\b", re.IGNORECASE), 0.7),
        (re.compile(r"\bmoderate\b", re.IGNORECASE), 0.65),
    ],
    "low": [
        (re.compile(r"\blow\b", re.IGNORECASE), 0.6),
        (re.compile(r"\bminor\b", re.IGNORECASE), 0.6),
    ],
}


@dataclass
class ClassificationResult:
    threat_types: dict[str, float]
    severity: str
    confidence: float
    top_type: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "threat_types": {k: round(v, 4) for k, v in self.threat_types.items()},
            "severity": self.severity,
            "confidence": round(self.confidence, 4),
            "top_type": self.top_type,
        }


class TextClassifier:
    def classify(self, text: str) -> ClassificationResult:
        scores: dict[str, float] = {}
        for threat_type, patterns in THREAT_TYPE_PATTERNS.items():
            max_score = 0.0
            for pattern, conf in patterns:
                if pattern.search(text):
                    max_score = max(max_score, conf)
            if max_score > 0:
                scores[threat_type] = max_score
        if not scores:
            scores["unknown"] = 0.5
        top_type = max(scores, key=scores.get)
        severity_scores: dict[str, float] = {}
        for sev, patterns in SEVERITY_PATTERNS.items():
            for pattern, conf in patterns:
                if pattern.search(text):
                    severity_scores[sev] = conf
        severity = max(severity_scores, key=severity_scores.get) if severity_scores else "unknown"
        confidence = scores[top_type]
        return ClassificationResult(
            threat_types=scores,
            severity=severity,
            confidence=confidence,
            top_type=top_type,
        )


# ---------------------------------------------------------------------------
# Document Summarizer
# ---------------------------------------------------------------------------


class DocumentSummarizer:
    def __init__(self, max_sentences: int = 5) -> None:
        self._max_sentences = max_sentences

    def summarize(self, text: str, max_sentences: int | None = None) -> dict[str, Any]:
        k = max_sentences or self._max_sentences
        sentences = [s for s in _split_sentences(text) if len(s) > 20]
        if not sentences:
            return {"summary": "", "key_findings": [], "sentence_count": 0}
        scored = []
        for s in sentences:
            score = 0.0
            for kw in MALWARE_KEYWORDS + list(TRIGGER_EVENTS.keys()):
                if kw in s.lower():
                    score += 1.0
            if CVE_RE.search(s):
                score += 2.0
            if IP_RE.search(s):
                score += 1.0
            if DOMAIN_RE.search(s):
                score += 1.0
            scored.append((s, score))
        scored.sort(key=lambda x: -x[1])
        top = [s for s, _ in scored[:k]]
        key_findings = []
        seen_findings: set[str] = set()
        for s in top:
            entities = NEREngine().extract(s)
            for e in entities:
                if e.text not in seen_findings:
                    seen_findings.add(e.text)
                    key_findings.append({"entity": e.text, "type": e.label})
        return {
            "summary": " ".join(top),
            "key_findings": key_findings,
            "sentence_count": len(sentences),
            "summary_sentences": len(top),
        }
