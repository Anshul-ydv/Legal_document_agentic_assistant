import logging
import time
from datetime import datetime
from typing import Any, Dict

import requests

from src.config import MCP_SERVER_B_URL, ENABLE_A2A_DISPATCH
from src.monitoring.callbacks import monitor
from src.state.shared_state import LegalDocumentState, AuditEntry

logger = logging.getLogger(__name__)

DISPATCH_TIMEOUT = (10, 180)  # (connect, read) seconds
MAX_ATTEMPTS = 3
BACKOFF_SECONDS = 5


def _make_json_safe(value: Any) -> Any:

    if isinstance(value, dict):
        return {key: _make_json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_make_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_make_json_safe(item) for item in value]
    if isinstance(value, set):
        return [_make_json_safe(item) for item in value]
    if hasattr(value, "dict"):
        return _make_json_safe(value.dict())
    if isinstance(value, datetime):
        return value.isoformat()
    return value

class A2ADispatchAgent:
    """Agent 5: Communicate results to ADK-B via MCP/A2A"""

    def __init__(self):
        self.name = "A2ADispatchAgent"
        self.session = requests.Session()

    def process(self, state: LegalDocumentState) -> LegalDocumentState:
        context = monitor.on_agent_start(self.name, {"document_id": state["document_id"]})
        try:
            if not ENABLE_A2A_DISPATCH:
                state["status"] = "completed"
                state.setdefault("planning_notes", []).append("Dispatch disabled via config")
                monitor.on_agent_end(context, {"skipped": True, "reason": "disabled"}, "a2a")
                return state

            if not state.get("ready_for_suggestions"):
                state["status"] = "completed"
                state.setdefault("planning_notes", []).append("Dispatch skipped: no actionable risks detected")
                monitor.on_agent_end(context, {"skipped": True}, "a2a")
                return state

            payload = {
                "document_id": state["document_id"],
                "adk_a_data": state.get("context_bundle", {})
            }
            safe_payload = _make_json_safe(payload)
            endpoint = f"{MCP_SERVER_B_URL.rstrip('/')}/generate_suggestions"
            response = None
            last_error = None

            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    response = self.session.post(
                        endpoint,
                        json=safe_payload,
                        timeout=DISPATCH_TIMEOUT
                    )
                    break
                except requests.RequestException as exc:
                    last_error = exc
                    logger.warning(
                        "Dispatch attempt %s/%s to ADK-B failed: %s",
                        attempt,
                        MAX_ATTEMPTS,
                        exc
                    )
                    state.setdefault("planning_notes", []).append(
                        f"Dispatch attempt {attempt} failed: {exc}"
                    )
                    if attempt < MAX_ATTEMPTS:
                        time.sleep(BACKOFF_SECONDS * attempt)

            if response is None:
                warning_msg = (
                    f"ADK-B dispatch failed after {MAX_ATTEMPTS} attempts: {last_error}"
                )
                logger.error(warning_msg)
                state.setdefault("errors", []).append(warning_msg)
                state["adk_b_response"] = {
                    "status": "dispatch_failed",
                    "error": str(last_error)
                }
                state.setdefault("planning_notes", []).append(
                    "ADK-B unreachable; captured warning"
                )
                state["status"] = "completed_with_warning"
                monitor.on_agent_end(
                    context,
                    {"response_code": None, "failed": True},
                    "a2a"
                )
                return state

            if response.ok:
                state["adk_b_response"] = response.json()
                state.setdefault("planning_notes", []).append("ADK-B suggestions requested via MCP portal")
                state["status"] = "completed"
                logger.info("Dispatched document %s to ADK-B", state["document_id"])
            else:
                logger.warning("ADK-B responded with %s", response.status_code)
                state["adk_b_response"] = {"status": "dispatch_failed", "error": f"HTTP {response.status_code}"}
                state["status"] = "completed_with_warning"

            audit_entry = AuditEntry(
                timestamp=datetime.now(),
                agent_name=self.name,
                action="a2a_dispatch",
                input_data={"endpoint": MCP_SERVER_B_URL},
                output_data={"response_code": response.status_code if response else None},
                model_used="http",
                execution_time_ms=(datetime.now() - context["timestamp"]).total_seconds() * 1000
            )
            state.setdefault("audit_log", []).append(audit_entry)
            monitor.on_agent_end(context, {"response_code": response.status_code if response else None}, "a2a")
        except Exception as exc:
            logger.error("A2A dispatch failed: %s", exc)
            monitor.on_agent_error(context, exc)
            state.setdefault("errors", []).append(f"{self.name}: {exc}")
            state["status"] = "error"
        return state
