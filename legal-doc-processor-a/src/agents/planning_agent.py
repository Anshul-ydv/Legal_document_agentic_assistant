from datetime import datetime
from typing import Dict
from src.state.shared_state import LegalDocumentState, AuditEntry
from src.monitoring.callbacks import monitor
import logging

logger = logging.getLogger(__name__)

class PlanningAgent:
    """Agent 2: Dynamically plan the pipeline and model routing"""

    def __init__(self):
        self.name = "PlanningAgent"

    def process(self, state: LegalDocumentState) -> LegalDocumentState:
        context = monitor.on_agent_start(self.name, {
            "document_id": state["document_id"],
            "complexity": state.get("document_complexity", 0.0)
        })

        try:
            complexity = state.get("document_complexity", 0.0)
            page_count = state.get("page_count", 0)
            doc_category = state.get("document_category", "contract")

            strategy = self._determine_strategy(complexity, page_count)
            model_plan = self._build_model_plan(strategy)
            cost_budget = 3.0 if strategy == "advanced" else 1.2

            state["processing_strategy"] = strategy
            state["model_plan"] = model_plan
            state["cost_budget"] = cost_budget
            state["cost_spent"] = 0.0
            state["planning_notes"] = [
                f"Detected category: {doc_category}",
                f"Complexity score: {complexity:.2f}",
                f"Page count: {page_count}",
                f"Strategy selected: {strategy}",
                f"Model routing: {model_plan}"
            ]
            state["parallel_tasks"] = ["clause_extraction", "metadata_summary"]

            audit_entry = AuditEntry(
                timestamp=datetime.now(),
                agent_name=self.name,
                action="dynamic_planning",
                input_data={
                    "document_category": doc_category,
                    "complexity": complexity,
                    "page_count": page_count
                },
                output_data={
                    "processing_strategy": strategy,
                    "model_plan": model_plan,
                    "cost_budget": cost_budget
                },
                model_used="planning_heuristics",
                execution_time_ms=(datetime.now() - context["timestamp"]).total_seconds() * 1000
            )
            state.setdefault("audit_log", []).append(audit_entry)

            monitor.on_agent_end(context, {
                "strategy": strategy,
                "model_plan": model_plan
            }, "planning_heuristics")

        except Exception as exc:
            logger.error("Planning failed: %s", exc)
            monitor.on_agent_error(context, exc)
            state.setdefault("errors", []).append(f"{self.name}: {exc}")
            state["status"] = "error"
        return state

    def _determine_strategy(self, complexity: float, page_count: int) -> str:
        if complexity >= 0.65 or page_count > 20:
            return "advanced"
        if page_count > 50:
            return "bulk_review"
        return "standard"

    def _build_model_plan(self, strategy: str) -> Dict:
        if strategy == "advanced":
            return {
                "clause_model": "gemini-2.0-flash",
                "risk_model": "gemini-2.0-flash",
                "summary_model": "gemini-2.0-flash"
            }
        if strategy == "bulk_review":
            return {
                "clause_model": "local-keyword",
                "risk_model": "gemini-2.0-flash-lite",
                "summary_model": "local-keyword"
            }
        return {
            "clause_model": "gemini-2.0-flash-lite",
            "risk_model": "gemini-2.0-flash-lite",
            "summary_model": "local-keyword"
        }
