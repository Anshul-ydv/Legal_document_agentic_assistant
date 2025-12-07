"""Legal Document Processor Agent (ADK-A)."""

from google.adk.agents.llm_agent import Agent
import logging
import os
import sys
from typing import Any, Dict, Optional, List, Tuple, cast
import base64
import binascii
import tempfile
from pathlib import Path

import requests


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")

for path in (SRC_DIR, PROJECT_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from src.graph.workflow import run_adk_a
from src.utils.persistence import persist_json_output, persist_markdown_output
from src.utils.reporting import build_adk_a_markdown_report
from src.config import (
    MCP_SERVER_B_URL,
    ENABLE_A2A_DISPATCH,
    LLM_MIN_CALL_INTERVAL,
    LLM_RPM_LIMIT,
)
from src.utils.global_llm_rate_limiter import install_global_llm_rate_limiter
from src.agents.a2a_dispatch_agent import _make_json_safe
from src.tools.pdf_parser import DocumentParser

logger = logging.getLogger(__name__)

# Ensure every Gemini call (including ADK root agent) respects rate limits
install_global_llm_rate_limiter(LLM_MIN_CALL_INTERVAL, LLM_RPM_LIMIT)

_BINARY_SUFFIX_MAP = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
    "text/plain": ".txt",
    "text/markdown": ".md",
}


def _payload_debug_info(payload: Any) -> str:
    """Summarize incoming payloads without logging full content."""

    if not payload:
        return "empty"

    if isinstance(payload, list):
        sample = next((item for item in payload if isinstance(item, dict)), None)
        sample_keys = sorted(sample.keys())[:6] if isinstance(sample, dict) else []
        return f"list(len={len(payload)}, sample_keys={sample_keys})"

    return f"type={type(payload).__name__}"


def _extract_text_from_documents(documents: Optional[List[Dict[str, Any]]]) -> str:
    """Best-effort extraction of text from ADK Web document payloads."""

    if not documents:
        return ""

    for idx, document in enumerate(documents):
        if not isinstance(document, dict):
            continue

        # Common plain-text fields first
        for key in ("text", "content", "raw_text", "document_text"):
            value = document.get(key)
            if isinstance(value, str) and value.strip():
                logger.info("Loaded inline text from document[%s].%s (len=%s)", idx, key, len(value))
                return value

        # Inline bytes (base64 encoded)
        inline_bytes, file_name, mime_type = _extract_document_bytes(document)
        if inline_bytes:
            decoded = _bytes_to_text(inline_bytes, file_name=file_name, mime_type=mime_type, idx=idx)
            if decoded:
                return decoded

        # Local filesystem fallback
        path_value = document.get("path") or document.get("local_path")
        if isinstance(path_value, str) and path_value.strip():
            try:
                with open(path_value, "r", encoding="utf-8") as handle:
                    file_text = handle.read()
                if file_text.strip():
                    logger.info("Read text from document[%s] path=%s (len=%s)", idx, path_value, len(file_text))
                    return file_text
            except OSError as exc:
                logger.warning("Unable to read uploaded document path %s: %s", path_value, exc)

    return ""


def _extract_document_bytes(document: Dict[str, Any]) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
    """Extract raw bytes plus identifying metadata from ADK Web document payloads."""

    inline_data = document.get("inline_data") or document.get("inlineData") or {}
    file_name = inline_data.get("file_name") or inline_data.get("fileName") or document.get("name")
    mime_type = inline_data.get("mime_type") or inline_data.get("mimeType") or document.get("mime_type") or document.get("mimeType")

    payload_candidates = [
        inline_data.get("data"),
        inline_data.get("bytes"),
        inline_data.get("base64"),
    ]

    for b64_key in ("data", "base64_data", "base64", "bytes"):
        payload_candidates.append(document.get(b64_key))

    for payload in payload_candidates:
        if isinstance(payload, str) and payload.strip():
            try:
                return base64.b64decode(payload), file_name, mime_type
            except (ValueError, binascii.Error):
                continue

    return None, file_name, mime_type


def _bytes_to_text(data: bytes, file_name: Optional[str], mime_type: Optional[str], idx: int) -> str:
    """Convert uploaded binary payloads into plaintext suitable for Gemini input."""

    suffix = _infer_suffix(file_name, mime_type)

    # Treat small payloads or explicit text formats as utf-8 text directly
    if suffix in (".txt", ".md") or mime_type and mime_type.startswith("text/"):
        try:
            decoded = data.decode("utf-8", errors="ignore")
            if decoded.strip():
                logger.info("Decoded text payload for document[%s] (%s)", idx, suffix)
                return decoded
        except UnicodeDecodeError as exc:
            logger.warning("Unable to decode textual payload for document[%s]: %s", idx, exc)

    # Persist to a temporary file so we can reuse the existing parser stack
    if suffix in (".pdf", ".docx", ".doc"):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(data)
                tmp_path = tmp.name
            try:
                parsed = DocumentParser.parse_document(tmp_path)
                full_text = parsed.get("full_text", "")
                if full_text.strip():
                    logger.info("Parsed %s payload for document[%s] via DocumentParser", suffix, idx)
                    return full_text
            finally:
                Path(tmp_path).unlink(missing_ok=True)
        except Exception as exc:  # noqa: BLE001 - we need to continue down fallback paths
            logger.warning("Failed to parse %s payload for document[%s]: %s", suffix, idx, exc)

    # Final fallback: attempt utf-8 decode regardless of suffix
    decoded = data.decode("utf-8", errors="ignore")
    if decoded.strip():
        logger.info("Decoded binary payload for document[%s] using permissive utf-8 fallback", idx)
        return decoded

    logger.warning("Document[%s] payload could not be converted to text", idx)
    return ""


def _infer_suffix(file_name: Optional[str], mime_type: Optional[str]) -> str:
    """Infer a temporary file suffix from available metadata."""

    if file_name:
        suffix = Path(file_name).suffix
        if suffix:
            return suffix.lower()

    if mime_type and mime_type in _BINARY_SUFFIX_MAP:
        return _BINARY_SUFFIX_MAP[mime_type]

    return ".txt"


def process_legal_document(
    document_id: str,
    document_text: str = "",
    document_path: str = "",
    documents: Optional[List[Dict[str, Any]]] = None,
    document_uploads: Optional[List[Dict[str, Any]]] = None,
    **kwargs: Any,
) -> str:
    """
    Process a legal document through ADK-A pipeline.
    
    Args:
        document_id: Unique identifier for the document
        document_text: Direct text input (optional if document_path provided)
        document_path: Path to document file (optional if document_text provided)
    
    Returns:
        str: Formatted analysis results as text
    """
    try:
        # Bridge ADK Web uploads (if any) into the workflow when no explicit text/path provided
        camel_case_uploads = kwargs.get("documentUploads")
        logger.info(
            "Tool input payloads: documents=%s, document_uploads=%s, documentUploads=%s, extra_keys=%s",
            _payload_debug_info(documents),
            _payload_debug_info(document_uploads),
            _payload_debug_info(camel_case_uploads),
            sorted(kwargs.keys()),
        )
        combined_documents: List[Dict[str, Any]] = []
        for payload in (documents, document_uploads, camel_case_uploads):
            if payload:
                combined_documents.extend([doc for doc in payload if isinstance(doc, dict)])

        logger.info(
            "process_legal_document invoked (id=%s, text_len=%s, path=%s, docs=%s)",
            document_id,
            len(document_text) if document_text else 0,
            bool(document_path),
            len(combined_documents),
        )

        if not document_text and not document_path:
            extracted_text = _extract_text_from_documents(combined_documents)
            if extracted_text:
                document_text = extracted_text
            else:
                logger.warning("No document content provided for %s; document uploads were empty", document_id)
                return (
                    "⚠️ I could not find any text in the uploaded document. "
                    "Please upload a readable file or paste the contract text so I can analyze it."
                )

        logger.info(
            "Running ADK-A workflow for %s (text_len=%s, path=%s)",
            document_id,
            len(document_text) if document_text else 0,
            document_path or "",
        )

        # Run the ADK-A workflow
        result = run_adk_a(
            document_id=document_id,
            document_path=document_path if document_path else None,
            document_text=document_text if document_text else None,
            document_type="contract"
        )

        result_dict: Dict[str, Any] = cast(Dict[str, Any], result)

        # Extract filename from document_path for saving, fallback to document_id
        save_name = document_id
        if document_path:
            save_name = Path(document_path).stem
        
        markdown_report = build_adk_a_markdown_report(result_dict)
        result_dict["markdown_report"] = markdown_report
        persist_json_output("adk_a", save_name, result_dict)
        persist_markdown_output("adk_a", save_name, markdown_report)

        adk_b_summary: Optional[Dict[str, Any]] = None
        if ENABLE_A2A_DISPATCH and result_dict.get("ready_for_suggestions"):
            adk_b_summary = _dispatch_to_adk_b(document_id, result_dict)
            if adk_b_summary:
                result_dict["adk_b_response"] = adk_b_summary
        
        # Format response for ADK
        summary_parts = [
            f"Analyzed {result_dict.get('clause_count', 0)} clauses",
            f"{result_dict.get('high_risk_count', 0)} high-risk items identified",
            f"Overall risk score: {result_dict.get('overall_risk_score', 0):.2f}/10.0"
        ]
        if adk_b_summary and adk_b_summary.get("status") == "completed":
            summary_parts.append(
                f"Generated {adk_b_summary.get('suggestion_count', 0)} compliance suggestions"
            )

        response_payload = {
            "status": "success",
            "document_id": result_dict.get('document_id'),
            "summary": "; ".join(summary_parts),
            "clause_count": result_dict.get('clause_count', 0),
            "high_risk_count": result_dict.get('high_risk_count', 0),
            "overall_risk_score": result_dict.get('overall_risk_score', 0),
            "ready_for_suggestions": result_dict.get('ready_for_suggestions', False),
            "adk_b_summary": adk_b_summary,
            "details": {
                "clauses": [
                    {
                        "id": c.id,
                        "type": c.type,
                        "text": c.text[:200] + "..." if len(c.text) > 200 else c.text,
                        "location": c.location,
                        "confidence": c.confidence
                    }
                    for c in result_dict.get('extracted_clauses', [])[:10]
                ],
                "risks": [
                    {
                        "clause_id": r.clause_id,
                        "risk_level": r.risk_level,
                        "severity_score": r.severity_score,
                        "description": r.risk_description
                    }
                    for r in result_dict.get('risk_assessments', [])[:10]
                ]
            }
        }

        if adk_b_summary:
            response_payload["details"]["adk_b"] = adk_b_summary

        # Format as readable text response for ADK with detailed analysis
        risk_score = result_dict.get('overall_risk_score', 0)
        clause_count = result_dict.get('clause_count', 0)
        high_risk_count = result_dict.get('high_risk_count', 0)
        
        # Categorize risks
        high_risks = []
        medium_risks = []
        low_risks = []
        if result_dict.get('risk_assessments'):
            for risk in result_dict.get('risk_assessments', []):
                level = risk.risk_level.lower()
                if level == 'high':
                    high_risks.append(risk)
                elif level == 'medium':
                    medium_risks.append(risk)
                else:
                    low_risks.append(risk)
        
        # Get clause types for summary
        clause_types = {}
        for clause in result_dict.get('extracted_clauses', []):
            clause_type = clause.type
            clause_types[clause_type] = clause_types.get(clause_type, 0) + 1
        
        output_lines = [
            "═" * 90,
            "📋 LEGAL DOCUMENT ANALYSIS REPORT",
            "═" * 90,
            "",
            "🎯 OVERALL RISK SCORE",
            "─" * 90,
            f"Risk Score: {risk_score:.2f} / 10.0",
            ""
        ]
        
        # Add visual risk indicator
        if risk_score >= 7.0:
            output_lines.append("⚠️  HIGH RISK - This document requires immediate legal attention")
        elif risk_score >= 5.0:
            output_lines.append("⚡ MODERATE RISK - Several areas need review and clarification")
        elif risk_score >= 3.0:
            output_lines.append("✓ LOW-MODERATE RISK - Minor adjustments recommended")
        else:
            output_lines.append("✓ LOW RISK - Document appears generally acceptable")
        
        output_lines.extend([
            "",
            "═" * 90,
            "📄 CLAUSES IDENTIFIED",
            "─" * 90,
            f"Total Clauses Extracted: {clause_count}",
            ""
        ])
        
        # List clause types found
        if clause_types:
            output_lines.append("Clause Types Found:")
            for clause_type, count in sorted(clause_types.items(), key=lambda x: x[1], reverse=True)[:10]:
                output_lines.append(f"  • {clause_type.replace('_', ' ').title()}: {count} clause(s)")
        
        output_lines.extend([
            "",
            "═" * 90,
            "🚨 HIGH RISK CLAUSES",
            "─" * 90,
        ])
        
        if high_risks:
            output_lines.append(f"Total High-Risk Clauses: {len(high_risks)}")
            output_lines.append("")
            for i, risk in enumerate(high_risks[:8], 1):
                clause_type = getattr(risk, 'clause_type', 'Unknown')
                output_lines.extend([
                    f"{i}. {clause_type.replace('_', ' ').upper()}",
                    f"   └─ Severity: {risk.severity_score:.1f}/10.0",
                    f"   └─ Issue: {risk.risk_description}",
                    ""
                ])
        else:
            output_lines.append("✓ No high-risk clauses identified")
            output_lines.append("")
        
        output_lines.extend([
            "═" * 90,
            "📊 MEDIUM & LOW RISK CLAUSES",
            "─" * 90,
        ])
        
        if medium_risks:
            output_lines.append(f"Medium Risk Clauses: {len(medium_risks)}")
            output_lines.append("")
            for i, risk in enumerate(medium_risks[:4], 1):
                clause_type = getattr(risk, 'clause_type', 'Unknown')
                output_lines.extend([
                    f"{i}. {clause_type.replace('_', ' ').title()} - Severity: {risk.severity_score:.1f}/10.0",
                    f"   {risk.risk_description[:120]}{'...' if len(risk.risk_description) > 120 else ''}",
                    ""
                ])
        
        if low_risks:
            output_lines.append(f"Low Risk Clauses: {len(low_risks)}")
            output_lines.append("These clauses present minimal concern and are generally acceptable.")
        elif not medium_risks:
            output_lines.append("✓ No medium or low risk clauses to report")
        
        output_lines.extend([
            "",
            "═" * 90,
            "🔍 RISK ASSESSMENT SUMMARY",
            "─" * 90,
        ])
        
        # Detailed risk assessment
        if risk_score >= 7.0:
            output_lines.extend([
                "CRITICAL CONCERNS IDENTIFIED:",
                "",
                f"• {len(high_risks)} clauses require immediate review and modification",
                "• Significant legal exposure identified in financial and liability terms",
                "• Document should NOT be executed without legal counsel review",
                "• Potential for disputes and legal complications is HIGH",
            ])
        elif risk_score >= 5.0:
            output_lines.extend([
                "NOTABLE CONCERNS IDENTIFIED:",
                "",
                f"• {len(high_risks)} high-risk clause(s) need attention",
                f"• {len(medium_risks)} medium-risk clause(s) should be reviewed",
                "• Legal review is strongly recommended before proceeding",
                "• Several areas require clarification to prevent future disputes",
            ])
        elif risk_score >= 3.0:
            output_lines.extend([
                "MINOR CONCERNS IDENTIFIED:",
                "",
                "• Document is generally acceptable with some improvements needed",
                f"• {len(high_risks) + len(medium_risks)} clause(s) could benefit from refinement",
                "• Consider implementing suggested enhancements",
                "• Standard legal review recommended as best practice",
            ])
        else:
            output_lines.extend([
                "MINIMAL CONCERNS:",
                "",
                "• Document appears well-structured and balanced",
                "• No major legal risks identified",
                "• Standard review recommended to ensure compliance",
                "• Minor improvements may enhance clarity",
            ])
        
        output_lines.extend([
            "",
            "═" * 90,
            "💡 COMPLIANCE & IMPROVEMENT SUGGESTIONS",
            "─" * 90,
        ])
        
        # Show compliance suggestions if available
        if adk_b_summary and adk_b_summary.get("suggestions"):
            suggestions = adk_b_summary.get("suggestions", [])
            output_lines.append(f"Total Suggestions Generated: {len(suggestions)}")
            output_lines.append("")
            
            high_priority = [s for s in suggestions if s.get("priority", "").lower() == "high"]
            medium_priority = [s for s in suggestions if s.get("priority", "").lower() == "medium"]
            low_priority = [s for s in suggestions if s.get("priority", "").lower() == "low"]
            
            if high_priority:
                output_lines.append("🔴 HIGH PRIORITY RECOMMENDATIONS:")
                output_lines.append("")
                for i, sugg in enumerate(high_priority[:6], 1):
                    text = sugg.get("suggestion_text", "")
                    clause_ref = sugg.get("clause_id", "General")
                    output_lines.extend([
                        f"{i}. [{clause_ref}]",
                        f"   {text[:180]}{'...' if len(text) > 180 else ''}",
                        ""
                    ])
            
            if medium_priority:
                output_lines.append("🟡 MEDIUM PRIORITY RECOMMENDATIONS:")
                output_lines.append("")
                for i, sugg in enumerate(medium_priority[:4], 1):
                    text = sugg.get("suggestion_text", "")
                    output_lines.append(f"{i}. {text[:150]}{'...' if len(text) > 150 else ''}")
                    output_lines.append("")
            
            if low_priority and (len(high_priority) + len(medium_priority) < 5):
                output_lines.append("🟢 ADDITIONAL RECOMMENDATIONS:")
                output_lines.append("")
                for i, sugg in enumerate(low_priority[:2], 1):
                    text = sugg.get("suggestion_text", "")
                    output_lines.append(f"{i}. {text[:120]}{'...' if len(text) > 120 else ''}")
                    output_lines.append("")
        elif adk_b_summary:
            output_lines.append("⚠️  Compliance suggestions service encountered an issue.")
            output_lines.append("Manual legal review is strongly recommended.")
            output_lines.append("")
        else:
            output_lines.append("ℹ️  Compliance suggestions were not requested for this document.")
            output_lines.append("")
        
        # Extract filename for display
        display_name = document_id
        if document_path:
            display_name = Path(document_path).stem
        
        output_lines.extend([
            "═" * 90,
            "📁 DETAILED REPORTS",
            "─" * 90,
            "",
            f"✓ JSON Report: output/adk_a_{display_name}_[timestamp].json",
            f"✓ Markdown Report: output/adk_a_{display_name}_[timestamp].md",
            "",
            "These files contain complete clause-by-clause analysis, detailed risk assessments,",
            "audit trails, and all compliance suggestions for comprehensive legal review.",
            "",
            f"Analysis Status: {result_dict.get('status', 'completed').upper()}",
            "═" * 90,
        ])

        return "\n".join(output_lines)

    except Exception as e:
        logger.exception("Error processing document %s", document_id)
        return f"❌ Error processing document: {str(e)}\n\nPlease check the document format and try again."


# Define the root agent for ADK
root_agent = Agent(
    model='gemini-2.0-flash-lite',
    name='legal_doc_processor',
    description='Legal Document Processor - Analyzes legal documents, extracts clauses, and assesses risks using AI',
    instruction="""You are a Legal Document Processing Assistant powered by AI. 

Your capabilities:
- Parse and analyze legal documents (PDF, DOCX, TXT)
- Extract and classify legal clauses (indemnification, liability, termination, etc.)
- Assess risk levels for each clause
- Provide risk scores and detailed analysis

When a user asks a general question or says greetings like "hi", "hello", "how are you", etc:
- Respond naturally and explain that you can analyze legal documents
- Ask them to provide a document or legal text for analysis
- Do NOT call the process_legal_document tool

When a user requests document analysis:

IMPORTANT - Two ways to provide documents:
1. **File Upload (Preferred)**: If the user uploaded a file using the upload button, call process_legal_document with just the document_id parameter. The system will automatically extract the file content.

2. **Text Input (Fallback)**: If the user shares document text directly in the chat (paste, copy, etc.), call process_legal_document with BOTH document_id AND document_text parameters, passing the full text the user provided.

After calling the tool:
- Return the tool's output EXACTLY as-is without any modifications or additional formatting
- Do NOT add introductory text, summaries, or explanations
- The tool returns a pre-formatted report that should be shown directly to the user

If the tool returns an error saying "no document content provided":
- This means the file upload didn't reach the system
- Politely ask the user to paste the contract text directly in the chat instead
- Example: "I couldn't access the uploaded file. Could you please paste the contract text directly here so I can analyze it?"

Always fulfill analysis requests by calling process_legal_document unless the user is clearly just chatting.""",
    tools=[process_legal_document]
)


def _dispatch_to_adk_b(document_id: str, adk_a_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Send ADK-A output to ADK-B MCP server for downstream suggestions."""

    endpoint = f"{MCP_SERVER_B_URL.rstrip('/')}/generate_suggestions"
    payload = {
        "document_id": document_id,
        "adk_a_data": adk_a_result
    }

    try:
        # Serialize Pydantic objects to JSON-safe format
        safe_payload = _make_json_safe(payload)
        response = requests.post(endpoint, json=safe_payload, timeout=180)
        response.raise_for_status()
        logger.info("ADK-B suggestions generated for document %s", document_id)
        return response.json()
    except (requests.RequestException, TypeError) as exc:
        logger.warning("ADK-B dispatch failed: %s", exc)
        return {
            "status": "error",
            "error": f"ADK-B dispatch failed: {exc}",
            "endpoint": endpoint
        }
