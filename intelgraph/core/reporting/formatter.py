from typing import Any


def format_json(data: Any) -> str:
    import json

    return json.dumps(data, indent=2, default=str, ensure_ascii=False)


def format_markdown(report_type: str, data: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# {report_type} Report")
    lines.append("")

    if report_type == "Entity":
        lines.extend(_entity_markdown(data))
    elif report_type == "Evidence":
        lines.extend(_evidence_markdown(data))
    elif report_type == "Verification":
        lines.extend(_verification_markdown(data))
    elif report_type == "Source":
        lines.extend(_source_markdown(data))
    elif report_type == "Full":
        lines.append("## Overview")
        lines.append("")
        lines.append(f"- **Entities:** {data.get('entity_count', 0)}")
        lines.append(f"- **Edges:** {data.get('edge_count', 0)}")
        lines.append(f"- **Generated at:** {data.get('generated_at', '')}")
        lines.append("")
        for section_key in ("entities", "evidence", "verifications", "sources"):
            section = data.get(section_key, [])
            if section:
                label = section_key.capitalize()
                lines.append(f"## {label}")
                lines.append("")
                for item in section:
                    if isinstance(item, dict):
                        lines.append(f"- **{item.get('entity_id', item.get('source_id', '?'))}**")
                        for k, v in item.items():
                            if k in ("entity_id", "source_id"):
                                continue
                            lines.append(f"  - {k}: {v}")
                        lines.append("")
    else:
        lines.append("```json")
        import json

        lines.append(json.dumps(data, indent=2, default=str, ensure_ascii=False))
        lines.append("```")

    lines.append("")
    return "\n".join(lines)


def format_html(report_type: str, data: dict[str, Any]) -> str:
    md = format_markdown(report_type, data)

    def _code_escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    lines: list[str] = []
    lines.append("<!DOCTYPE html>")
    lines.append('<html lang="en">')
    lines.append("<head>")
    lines.append(f"<title>{_code_escape(report_type)} Report</title>")
    lines.append("<style>")
    lines.append(
        "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 960px; margin: 0 auto; padding: 2rem; background: #fafafa; color: #333; }"
    )
    lines.append("h1 { border-bottom: 2px solid #333; padding-bottom: 0.5rem; }")
    lines.append("h2 { margin-top: 2rem; color: #555; }")
    lines.append("table { border-collapse: collapse; width: 100%; margin: 1rem 0; }")
    lines.append("th, td { border: 1px solid #ddd; padding: 0.5rem; text-align: left; }")
    lines.append("th { background: #f0f0f0; }")
    lines.append(
        "pre { background: #f4f4f4; padding: 1rem; border-radius: 4px; overflow-x: auto; }"
    )
    lines.append("</style>")
    lines.append("</head>")
    lines.append("<body>")

    in_code = False
    code_buf: list[str] = []
    for line in md.split("\n"):
        if line.startswith("```"):
            if in_code:
                joined = "\n".join(code_buf)
                lines.append(f"<pre>{_code_escape(joined)}</pre>")
                code_buf = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_buf.append(line)
            continue
        if line.startswith("## "):
            lines.append(f"<h2>{_code_escape(line[3:])}</h2>")
        elif line.startswith("# "):
            lines.append(f"<h1>{_code_escape(line[2:])}</h1>")
        elif line.startswith("- **"):
            lines.append(f"<p>{_code_escape(line)}</p>")
        elif line.startswith("  - "):
            lines.append(f"<p style='margin-left:1.5rem;'>{_code_escape(line)}</p>")
        elif line.strip():
            lines.append(f"<p>{_code_escape(line)}</p>")

    if code_buf:
        joined = "\n".join(code_buf)
        lines.append(f"<pre>{_code_escape(joined)}</pre>")

    lines.append("</body>")
    lines.append("</html>")
    return "\n".join(lines)


def format_output(report_type: str, data: dict[str, Any], fmt: str = "json") -> str:
    if fmt == "json":
        return format_json(data)
    elif fmt == "markdown":
        return format_markdown(report_type, data)
    elif fmt == "html":
        return format_html(report_type, data)
    return format_json(data)


def _entity_markdown(data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.append(f"- **Entity ID:** {data.get('entity_id', 'N/A')}")
    lines.append(f"- **Type:** {data.get('entity_type', 'N/A')}")
    for k, v in data.get("attributes", {}).items():
        lines.append(f"- **{k}:** {v}")
    lines.append("")
    lines.append("### Verification")
    lines.append(f"- **Status:** {data.get('verification_status', 'N/A')}")
    lines.append(f"- **Confidence:** {data.get('confidence', 0)}")
    lines.append(f"- **Evidence Count:** {data.get('evidence_count', 0)}")
    return lines


def _evidence_markdown(data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.append(f"- **Entity ID:** {data.get('entity_id', 'N/A')}")
    lines.append(f"- **Chain ID:** {data.get('chain_id', 'N/A')}")
    lines.append(f"- **Overall Confidence:** {data.get('confidence', 0)}")
    lines.append(f"- **Contradiction Score:** {data.get('contradiction_score', 0)}")
    lines.append(f"- **Status:** {data.get('status', 'N/A')}")
    lines.append(f"- **Evidence Count:** {data.get('evidence_count', 0)}")
    lines.append("")
    items = data.get("evidence", [])
    if items:
        lines.append("### Evidence Items")
        lines.append("")
        for i, item in enumerate(items, 1):
            lines.append(f"#### Item {i}")
            lines.append(f"- **ID:** {item.get('evidence_id', 'N/A')}")
            lines.append(f"- **Source:** {item.get('source_id', 'N/A')}")
            lines.append(f"- **Claim:** {item.get('claim', '')}")
            lines.append(f"- **Support:** {item.get('support_type', 'N/A')}")
            lines.append(f"- **Confidence:** {item.get('confidence', 0)}")
            lines.append("")
    return lines


def _verification_markdown(data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.append(f"- **Entity ID:** {data.get('entity_id', 'N/A')}")
    lines.append(f"- **Entity Type:** {data.get('entity_type', 'N/A')}")
    lines.append(f"- **Verification State:** {data.get('verification_state', 'N/A')}")
    lines.append(f"- **Operational State:** {data.get('operational_state', 'N/A')}")
    lines.append(f"- **Confidence:** {data.get('confidence', 0)}")
    lines.append(f"- **Consensus:** {data.get('consensus', 0)}")
    lines.append(f"- **Contradiction:** {data.get('contradiction', 0)}")
    lines.append(f"- **Source Count:** {data.get('source_count', 0)}")
    if data.get("reasoning"):
        lines.append(f"- **Reasoning:** {data['reasoning']}")
    if data.get("matched_rules"):
        lines.append(f"- **Matched Rules:** {', '.join(data['matched_rules'])}")
    return lines


def _source_markdown(data: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    lines.append(f"- **Source ID:** {data.get('id', data.get('source_id', 'N/A'))}")
    lines.append(f"- **URL:** {data.get('source_url', 'N/A')}")
    lines.append(f"- **Name:** {data.get('source_name', 'N/A')}")
    lines.append(f"- **Tier:** {data.get('source_tier', data.get('tier', 'N/A'))}")
    lines.append(f"- **Trust Score:** {data.get('trust_score', data.get('effective_trust', 0))}")
    lines.append(f"- **Reliability:** {data.get('reliability_score', 0)}")
    lines.append(f"- **Classification:** {data.get('classification', 'N/A')}")
    lines.append(f"- **Validation Count:** {data.get('validation_count', 0)}")
    flags = data.get("flags", [])
    if flags:
        lines.append(f"- **Flags:** {', '.join(flags) if isinstance(flags, list) else flags}")
    return lines
