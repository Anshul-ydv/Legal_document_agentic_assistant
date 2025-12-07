import logging
from datetime import datetime
from typing import List
import google.generativeai as genai
from src.state.shared_state import LegalDocumentState, AuditEntry
from src.monitoring.callbacks import monitor
from src.config import GEMINI_MODEL_STANDARD, GEMINI_MODEL_COMPLEX, GEMINI_API_KEY
from src.utils.llm import generate_with_retry

logger = logging.getLogger(__name__)

class MetadataSummaryAgent:
    """Summarize document structure & provide outline"""

    def __init__(self):
        self.name = "MetadataSummaryAgent"
        self.flash_model = genai.GenerativeModel(GEMINI_MODEL_STANDARD)
        self.pro_model = genai.GenerativeModel(GEMINI_MODEL_COMPLEX)
        self.llm_enabled = bool(GEMINI_API_KEY)

    def process(self, state: LegalDocumentState) -> LegalDocumentState:
        context = monitor.on_agent_start(self.name, {
            "document_id": state["document_id"],
            "strategy": state.get("processing_strategy", "standard")
        })
        try:
            strategy = state.get("processing_strategy", "standard")
            text = state.get("parsed_text", "")
            summary = self._generate_summary(text, strategy)
            outline = summary.get("outline", [])

            state["metadata_summary"] = summary
            state["document_outline"] = outline
            state["key_entities"] = list(dict.fromkeys(state.get("key_entities", []) + summary.get("entities", [])))

            audit_entry = AuditEntry(
                timestamp=datetime.now(),
                agent_name=self.name,
                action="metadata_summary",
                input_data={"strategy": strategy, "text_length": len(text)},
                output_data={"outline_len": len(outline), "entities": summary.get("entities", [])},
                model_used=summary.get("model_used", "local"),
                execution_time_ms=(datetime.now() - context["timestamp"]).total_seconds() * 1000
            )
            state.setdefault("audit_log", []).append(audit_entry)

            monitor.on_agent_end(context, {
                "outline_len": len(outline)
            }, summary.get("model_used", "local"))
        except Exception as exc:
            logger.error("Metadata summary failed: %s", exc)
            monitor.on_agent_error(context, exc)
            state.setdefault("errors", []).append(f"{self.name}: {exc}")
        return state

    def _generate_summary(self, text: str, strategy: str) -> dict:
        if not text:
            return {
                "model_used": "local",
                "outline": [],
                "entities": [],
                "summary": "No text provided"
            }

        if strategy == "standard" or not self.llm_enabled:
            return self._keyword_summary(text)

        # Use LLM for advanced strategy
        prompt = (
            "Produce a structured summary with sections: outline (bullet list), "
            "entities (parties, regulators), and obligations. Keep under 200 words.\n" +
            text[:6000]
        )
        model = self.pro_model if strategy == "advanced" else self.flash_model
        response = generate_with_retry(model, prompt)
        outline = [line.strip("- ") for line in response.text.splitlines() if line.strip()]
        return {
            "model_used": model.model_name,
            "outline": outline[:10],
            "entities": outline[:5],
            "summary": "\n".join(outline[:5])
        }

    def _keyword_summary(self, text: str) -> dict:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        outline = lines[:10]
        entities = [token for token in text.split() if token.istitle()][:5]
        return {
            "model_used": "local-keyword",
            "outline": outline,
            "entities": entities,
            "summary": "\n".join(outline[:3])
        }
