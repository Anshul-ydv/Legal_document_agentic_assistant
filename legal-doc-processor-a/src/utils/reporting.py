from datetime import datetime
from typing import Any, Dict, Iterable, List, cast


def _to_dict(item: Any) -> Dict[str, Any]:
    if item is None:
        return {}
    if hasattr(item, "dict") and callable(item.dict):
        return cast(Dict[str, Any], item.dict())
    if hasattr(item, "model_dump") and callable(item.model_dump):
        return cast(Dict[str, Any], item.model_dump())
    if isinstance(item, dict):
        return item
    return {}


def _truncate(text: str, limit: int = 240) -> str:
    sanitized = (text or "").strip().replace("\n", " ")
    if len(sanitized) <= limit:
        return sanitized
    return f"{sanitized[:limit].rstrip()}..."


def _format_float(value: Any, precision: int = 2, fallback: str = "n/a") -> str:
    try:
        return f"{float(value):.{precision}f}"
    except (TypeError, ValueError):
        return fallback


def build_adk_a_markdown_report(result: Dict[str, Any]) -> str:
    """Render a readable Markdown summary for ADK-A outputs."""
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    doc_id = result.get("document_id", "unknown")
    status = result.get("status", "unknown").upper()
    ready = result.get("ready_for_suggestions", False)

    lines: List[str] = [
        "# ADK-A Document Processing Report",
        "",
        f"**Document ID:** {doc_id}",
        f"**Generated:** {generated_at}",
        f"**Processing Status:** {status}",
        "",
        "---",
        "",
        "## Analysis Metrics",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Clauses Extracted | {result.get('clause_count', 0)} |",
        f"| High-Risk Clauses | {result.get('high_risk_count', 0)} |",
        f"| Overall Risk Score | {_format_float(result.get('overall_risk_score', 0.0))}/10.00 |",
        f"| Document Type | {result.get('document_type', 'n/a')} |",
        f"| Page Count | {result.get('page_count', 'n/a')} |",
        f"| Ready For Suggestions | {'Yes' if ready else 'No'} |",
        "",
    ]

    clauses = [_to_dict(item) for item in result.get("extracted_clauses", [])]
    if clauses:
        lines.extend([
            "## Clause Highlights",
            "",
        ])
        for clause in clauses[:5]:
            clause_id = clause.get("id", "clause")
            clause_type = clause.get("type", "general").title()
            location = clause.get("location", "unspecified")
            confidence = _format_float(clause.get("confidence"))
            excerpt = _truncate(clause.get("text", "")) or "_No clause text available._"
            lines.extend([
                f"### {clause_id} · {clause_type}",
                f"- Location: {location}",
                f"- Confidence: {confidence}",
                "",
                excerpt,
                "",
            ])

    risks = [_to_dict(item) for item in result.get("risk_assessments", [])]
    if risks:
        lines.extend([
            "## Risk Highlights",
            "",
        ])
        for risk in risks[:5]:
            clause_ref = risk.get("clause_id", "n/a")
            level = risk.get("risk_level", "unknown")
            severity = _format_float(risk.get("severity_score"))
            description = _truncate(risk.get("risk_description", "")) or "_Description not provided._"
            frameworks = ", ".join(risk.get("risk_factors", [])) if risk.get("risk_factors") else "n/a"
            lines.extend([
                f"- **Clause:** {clause_ref} · **Level:** {level} · **Severity:** {severity}",
                f"  - Factors: {frameworks}",
                f"  - Detail: {description}",
            ])
        lines.append("")

    planning_notes = result.get("planning_notes") or []
    if planning_notes:
        lines.extend([
            "## Planning Notes",
            "",
        ])
        for note in planning_notes[:5]:
            lines.append(f"- {note}")
        if len(planning_notes) > 5:
            lines.append(f"- ...and {len(planning_notes) - 5} more notes")
        lines.append("")

    context_bundle = result.get("context_bundle") or {}
    if context_bundle:
        keys = ", ".join(sorted(context_bundle.keys()))
        lines.extend([
            "## Context Bundle",
            "",
            f"Available Keys: {keys if keys else 'n/a'}",
            "",
        ])

    errors = result.get("errors") or []
    lines.extend([
        "## System Status",
        "",
        f"- Ready for ADK-B: {'Yes' if ready else 'No'}",
        f"- Recorded Errors: {len(errors)}",
    ])
    if errors:
        for err in errors[:5]:
            lines.append(f"  - {err}")
        if len(errors) > 5:
            lines.append(f"  - ...and {len(errors) - 5} more errors")
    lines.append("")

    lines.extend([
        "## Next Steps",
        "",
        "1. Review highlighted clauses and risk notes.",
        "2. Address high-risk clauses before execution.",
        "3. Trigger ADK-B suggestions if not already queued.",
        "4. Update the document and rerun this workflow as needed.",
        "",
        "---",
        "",
        "_Report auto-generated by ADK-A._",
    ])

    return "\n".join(lines).strip()
