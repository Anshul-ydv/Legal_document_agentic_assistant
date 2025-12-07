import asyncio
import copy
import logging
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Mapping, Tuple

from src.agents.clause_extraction_agent import ClauseExtractionAgent
from src.agents.metadata_summary_agent import MetadataSummaryAgent
from src.agents.risk_detection_agent import RiskDetectionAgent
from src.agents.a2a_dispatch_agent import A2ADispatchAgent
from src.monitoring.callbacks import monitor
from src.state.shared_state import LegalDocumentState, AuditEntry
from src.config import FORCE_SEQUENTIAL_EXECUTION

logger = logging.getLogger(__name__)

class ParallelInsightsAgent:
    """Agent 3: Orchestrate clause, summary, risk, and suggestion tasks concurrently"""

    def __init__(self):
        self.name = "ParallelInsightsAgent"
        self.clause_agent = ClauseExtractionAgent()
        self.summary_agent = MetadataSummaryAgent()
        self.risk_agent = RiskDetectionAgent()
        self.dispatch_agent = A2ADispatchAgent()

    def process(self, state: LegalDocumentState) -> LegalDocumentState:
        context = monitor.on_agent_start(self.name, {
            "document_id": state["document_id"],
            "strategy": state.get("processing_strategy", "standard")
        })

        try:
            results, task_errors = self._run_parallel_execution(state)

            for label, exc in task_errors:
                logger.error("Concurrent task %s failed: %s", label, exc)
                state.setdefault("errors", []).append(f"{label}_task: {exc}")

            clause_state = results.get("clauses") or {}
            summary_state = results.get("summary") or {}
            risk_state = results.get("risk") or {}
            suggestion_state = results.get("suggestion") or {}

            if clause_state:
                state["extracted_clauses"] = clause_state.get("extracted_clauses", [])
                state["clause_count"] = clause_state.get("clause_count", 0)
                self._extend_audit_log(state, clause_state)

            if summary_state:
                state["metadata_summary"] = summary_state.get("metadata_summary", state.get("metadata_summary", {}))
                state["document_outline"] = summary_state.get("document_outline", [])
                state["key_entities"] = summary_state.get("key_entities", state.get("key_entities", []))
                self._extend_audit_log(state, summary_state)

            if risk_state:
                if "risk_assessments" in risk_state:
                    state["risk_assessments"] = risk_state.get("risk_assessments", [])
                if "high_risk_count" in risk_state:
                    state["high_risk_count"] = risk_state.get("high_risk_count", 0)
                if "overall_risk_score" in risk_state:
                    state["overall_risk_score"] = risk_state.get("overall_risk_score", 0.0)
                if "recommendation_trace" in risk_state:
                    state["recommendation_trace"] = risk_state.get("recommendation_trace", [])
                if "context_bundle" in risk_state:
                    state["context_bundle"] = risk_state.get("context_bundle", {})
                if "ready_for_suggestions" in risk_state:
                    state["ready_for_suggestions"] = risk_state.get("ready_for_suggestions", False)
                if "cost_spent" in risk_state:
                    state["cost_spent"] = risk_state.get("cost_spent", state.get("cost_spent", 0.0))
                if risk_state.get("planning_notes"):
                    state.setdefault("planning_notes", []).extend(risk_state["planning_notes"])
                if risk_state.get("status"):
                    state["status"] = risk_state["status"]
                if risk_state.get("errors"):
                    state.setdefault("errors", []).extend(risk_state["errors"])
                self._extend_audit_log(state, risk_state)

            if suggestion_state:
                if suggestion_state.get("planning_notes"):
                    state.setdefault("planning_notes", []).extend(suggestion_state["planning_notes"])
                if suggestion_state.get("adk_b_response"):
                    state["adk_b_response"] = suggestion_state["adk_b_response"]
                if suggestion_state.get("status"):
                    state["status"] = suggestion_state["status"]
                if suggestion_state.get("errors"):
                    state.setdefault("errors", []).extend(suggestion_state["errors"])
                self._extend_audit_log(state, suggestion_state)

            parallel_audit = AuditEntry(
                timestamp=datetime.now(),
                agent_name=self.name,
                action="parallel_insights",
                input_data={
                    "strategy": state.get("processing_strategy"),
                    "tasks": ["clause_extraction", "metadata_summary", "risk_detection", "suggestion_dispatch"]
                },
                output_data={
                    "clause_count": state.get("clause_count", 0),
                    "high_risk_count": state.get("high_risk_count", 0),
                    "ready_for_suggestions": state.get("ready_for_suggestions", False)
                },
                model_used="parallel_executor",
                execution_time_ms=(datetime.now() - context["timestamp"]).total_seconds() * 1000
            )
            state.setdefault("audit_log", []).append(parallel_audit)

            monitor.on_agent_end(context, {
                "clause_count": state.get("clause_count", 0),
                "high_risk_count": state.get("high_risk_count", 0),
                "adk_b_response": bool(state.get("adk_b_response"))
            }, "parallel_executor")
        except Exception as exc:
            logger.error("Parallel insights failed: %s", exc)
            monitor.on_agent_error(context, exc)
            state.setdefault("errors", []).append(f"{self.name}: {exc}")
        return state

    def _run_parallel_execution(self, state: LegalDocumentState) -> Tuple[Dict[str, LegalDocumentState], List[Tuple[str, BaseException]]]:
        """Execute async workflow even when caller already runs an event loop."""
        
        # Force sequential execution to avoid concurrent API calls that trigger 429
        if FORCE_SEQUENTIAL_EXECUTION:
            logger.info("Running tasks sequentially to avoid rate limits")
            return self._execute_sequential_tasks(state)

        coroutine = self._execute_parallel_tasks(state)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        return self._run_coroutine_in_thread(coroutine)

    @staticmethod
    def _run_coroutine_in_thread(coroutine: Any) -> Any:
        result_container: Dict[str, Any] = {}
        error: List[BaseException] = []

        def runner() -> None:
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                result_container["value"] = new_loop.run_until_complete(coroutine)
            except BaseException as exc:  # Capture any exception to raise in caller thread
                error.append(exc)
            finally:
                new_loop.close()

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()

        if error:
            raise error[0]
        return result_container["value"]

    async def _execute_parallel_tasks(self, state: LegalDocumentState) -> Tuple[Dict[str, LegalDocumentState], List[Tuple[str, BaseException]]]:
        clause_task = asyncio.create_task(self._run_clause_task_async(state))
        summary_task = asyncio.create_task(self._run_summary_task_async(state))
        risk_task = asyncio.create_task(self._run_risk_task_async(state, clause_task))
        suggestion_task = asyncio.create_task(self._run_suggestion_task_async(risk_task))

        task_order = [
            ("clauses", clause_task),
            ("summary", summary_task),
            ("risk", risk_task),
            ("suggestion", suggestion_task)
        ]

        gathered = await asyncio.gather(*(task for _, task in task_order), return_exceptions=True)

        results: Dict[str, LegalDocumentState] = {}
        errors: List[Tuple[str, BaseException]] = []
        for (label, _), outcome in zip(task_order, gathered):
            if isinstance(outcome, BaseException):
                errors.append((label, outcome))
            else:
                results[label] = outcome

        return results, errors

    async def _run_clause_task_async(self, state: LegalDocumentState) -> LegalDocumentState:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run_clause_task, state)

    async def _run_summary_task_async(self, state: LegalDocumentState) -> LegalDocumentState:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run_summary_task, state)

    async def _run_risk_task_async(self, state: LegalDocumentState, clause_task: "asyncio.Task[LegalDocumentState]") -> LegalDocumentState:
        clause_state = await clause_task
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run_risk_task, state, clause_state)

    async def _run_suggestion_task_async(self, risk_task: "asyncio.Task[LegalDocumentState]") -> LegalDocumentState:
        risk_state = await risk_task
        if not risk_state:
            return risk_state
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run_suggestion_task, risk_state)

    def _run_clause_task(self, state: LegalDocumentState) -> LegalDocumentState:
        return self.clause_agent.process(copy.deepcopy(state))

    def _run_summary_task(self, state: LegalDocumentState) -> LegalDocumentState:
        return self.summary_agent.process(copy.deepcopy(state))

    def _run_risk_task(self, state: LegalDocumentState, clause_state: LegalDocumentState):
        merged_state = copy.deepcopy(state)
        if clause_state:
            merged_state["extracted_clauses"] = clause_state.get("extracted_clauses", [])
            merged_state["clause_count"] = clause_state.get("clause_count", 0)
        return self.risk_agent.process(merged_state)

    def _run_suggestion_task(self, risk_state: LegalDocumentState):
        if not risk_state:
            return risk_state
        return self.dispatch_agent.process(risk_state)

    def _execute_sequential_tasks(self, state: LegalDocumentState) -> Tuple[Dict[str, LegalDocumentState], List[Tuple[str, BaseException]]]:
        """Execute tasks one by one to avoid hitting rate limits."""
        results: Dict[str, LegalDocumentState] = {}
        errors: List[Tuple[str, BaseException]] = []
        
        try:
            logger.info("[Sequential] Running clause extraction...")
            results["clauses"] = self._run_clause_task(state)
            time.sleep(15)  # 15 second delay between tasks to prevent 429 errors
        except Exception as e:
            errors.append(("clauses", e))
            logger.error(f"Clause extraction failed: {e}")
            results["clauses"] = state  # Use original state as fallback
        
        try:
            logger.info("[Sequential] Running metadata summary...")
            results["summary"] = self._run_summary_task(state)
            time.sleep(15)
        except Exception as e:
            errors.append(("summary", e))
            logger.error(f"Metadata summary failed: {e}")
            results["summary"] = state  # Use original state as fallback
        
        try:
            logger.info("[Sequential] Running risk detection...")
            clause_state = results.get("clauses", state)
            results["risk"] = self._run_risk_task(state, clause_state)
            time.sleep(15)
        except Exception as e:
            errors.append(("risk", e))
            logger.error(f"Risk detection failed: {e}")
            results["risk"] = state  # Use original state as fallback
        
        try:
            logger.info("[Sequential] Running suggestion dispatch...")
            risk_state = results.get("risk", state)
            results["suggestion"] = self._run_suggestion_task(risk_state)
        except Exception as e:
            errors.append(("suggestion", e))
            logger.error(f"Suggestion dispatch failed: {e}")
            results["suggestion"] = state  # Use original state as fallback
        
        return results, errors
    
    def _extend_audit_log(self, state: LegalDocumentState, source_state: Mapping[str, Any]) -> None:
        if source_state.get("audit_log"):
            state.setdefault("audit_log", []).extend(source_state["audit_log"])
