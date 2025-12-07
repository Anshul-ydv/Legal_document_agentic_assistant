import google.generativeai as genai
from typing import Dict, List
from src.state.shared_state import ComplianceAdvisorState, ComplianceSuggestion
from src.config import GEMINI_MODEL_STANDARD, GEMINI_MODEL_COMPLEX
from src.tools.compliance_checker import ComplianceChecker
from src.tools.template_library import TemplateLibrary
from src.monitoring.callbacks import monitor
from src.utils.llm import generate_with_retry
import json
import re
import logging

logger = logging.getLogger(__name__)

class SuggestionGeneratorAgent:
    """Agent 4: Generate compliant alternative clause suggestions"""
    
    def __init__(self):
        self.name = "SuggestionGeneratorAgent"
        self.standard_model = genai.GenerativeModel(GEMINI_MODEL_STANDARD)
        self.complex_model = genai.GenerativeModel(GEMINI_MODEL_COMPLEX)
        self.compliance_checker = ComplianceChecker()
        self.template_library = TemplateLibrary()
    
    def process(self, state: ComplianceAdvisorState) -> ComplianceAdvisorState:
        """Generate suggestions for risky clauses"""
        context = monitor.on_agent_start(self.name, {
            'document_id': state['document_id'],
            'clause_count': len(state.get('clauses', []))
        })
        
        try:
            clauses = state.get('clauses', [])
            risk_assessments = state.get('risk_assessments', [])
            trace_lookup = {trace.get('clause_id'): trace for trace in state.get('recommendation_trace', [])}

            high_risk_clause_ids = [
                r['clause_id'] for r in risk_assessments
                if r.get('risk_level') in ['HIGH', 'CRITICAL']
            ]

            monitor.log_intermediate_output(
                self.name,
                "risk_filter",
                {
                    'total_clauses': len(clauses),
                    'high_risk_clause_ids': high_risk_clause_ids[:10],
                    'high_risk_total': len(high_risk_clause_ids)
                }
            )

            logger.info(f"Generating suggestions for {len(high_risk_clause_ids)} high-risk clauses")

            prepared_items = self._prepare_clause_payloads(
                clauses,
                high_risk_clause_ids,
                trace_lookup
            )

            high_risk_items = [item for item in prepared_items if item['is_high_risk']]
            standard_items = [item for item in prepared_items if not item['is_high_risk']]

            suggestions: List[ComplianceSuggestion] = []
            suggestions.extend(
                self._generate_batch_suggestions(
                    high_risk_items,
                    self.complex_model,
                    GEMINI_MODEL_COMPLEX
                )
            )
            suggestions.extend(
                self._generate_batch_suggestions(
                    standard_items,
                    self.standard_model,
                    GEMINI_MODEL_STANDARD
                )
            )

            # Preserve input ordering
            order_lookup = {item['clause_id']: idx for idx, item in enumerate(prepared_items)}
            suggestions.sort(key=lambda s: order_lookup.get(s.clause_id, 0))

            state['compliance_suggestions'] = suggestions
            state['suggestion_count'] = len(suggestions)

            logger.info(f"Generated {len(suggestions)} compliance suggestions")

            monitor.on_agent_end(context, {
                'suggestion_count': len(suggestions)
            }, self.name)
            
        except Exception as e:
            logger.error(f"Error in {self.name}: {str(e)}")
            monitor.on_agent_error(context, e)
            state['errors'].append(f"{self.name}: {str(e)}")
            state['compliance_suggestions'] = []
            state['suggestion_count'] = 0
        
        return state
    
    def _prepare_clause_payloads(
        self,
        clauses: List[Dict],
        high_risk_clause_ids: List[str],
        trace_lookup: Dict
    ) -> List[Dict]:
        """Pre-compute compliance context before batching LLM calls."""

        payloads: List[Dict] = []
        low_risk_budget = max(0, 10 - len(high_risk_clause_ids))

        for clause in clauses:
            clause_id = clause.get('id')
            if not clause_id:
                continue

            is_high_risk = clause_id in high_risk_clause_ids
            if not is_high_risk and low_risk_budget <= 0:
                continue

            try:
                compliance_result = self.compliance_checker.check_clause_compliance(
                    clause.get('text', ''),
                    clause.get('type', 'general'),
                    ['GDPR', 'CCPA']
                )

                monitor.log_intermediate_output(
                    self.name,
                    "compliance_check",
                    {
                        'clause_id': clause_id,
                        'violations_found': len(compliance_result.get('violations', [])),
                        'is_high_risk': is_high_risk
                    }
                )

                template = self.template_library.get_template(
                    clause.get('type', 'general'),
                    'standard'
                )

                payloads.append({
                    'clause_id': clause_id,
                    'clause': clause,
                    'compliance_result': compliance_result,
                    'template': template,
                    'is_high_risk': is_high_risk,
                    'source_trace': trace_lookup.get(clause_id, {})
                })

                if not is_high_risk:
                    low_risk_budget -= 1

            except Exception as exc:
                logger.warning(f"Error preparing clause {clause_id}: {exc}")
                continue

        return payloads

    def _generate_batch_suggestions(
        self,
        items: List[Dict],
        model,
        model_name: str
    ) -> List[ComplianceSuggestion]:
        """Generate suggestions for a group of clauses using a single LLM call."""

        if not items:
            return []

        prompt_payload = [
            {
                "clause_id": item['clause_id'],
                "type": item['clause'].get('type', 'general'),
                "text": item['clause'].get('text', '')[:1200],
                "compliance_issues": item['compliance_result'].get('violations', []),
                "template_hint": (item['template'] or "")[:600],
            }
            for item in items
        ]

        prompt = (
            "You are a senior legal compliance advisor. Given the clauses below, rewrite each one "
            "to address the listed compliance issues. For every clause, return a JSON object containing "
            "the same clause_id so the results can be mapped back. Your entire response must be a JSON array.\n\n"
            "Clauses:\n"
            f"{json.dumps(prompt_payload, indent=2)}\n\n"
            "Output JSON array schema:\n"
            "[\n"
            "  {\n"
            "    \"clause_id\": \"original id\",\n"
            "    \"suggested_text\": \"improved clause\",\n"
            "    \"rationale\": \"why the changes solve compliance issues\",\n"
            "    \"compliance_frameworks\": [\"GDPR\", \"CCPA\"],\n"
            "    \"confidence\": 0.0-1.0\n"
            "  }\n"
            "]\n"
            "Keep explanations concise but specific to each clause."
        )

        try:
            response = generate_with_retry(model, prompt)
            response_text = response.text.strip()
            json_text = re.sub(r'^```json\s*', '', response_text)
            json_text = re.sub(r'\s*```$', '', json_text)
            parsed = json.loads(json_text)
        except Exception as exc:
            logger.error(f"Batch suggestion generation failed: {exc}")
            parsed = []

        if isinstance(parsed, dict):
            parsed = parsed.get('suggestions', [])

        result_lookup = {}
        if isinstance(parsed, list):
            for entry in parsed:
                clause_id = entry.get('clause_id')
                if clause_id:
                    result_lookup[clause_id] = entry

        suggestions: List[ComplianceSuggestion] = []
        for item in items:
            clause_id = item['clause_id']
            payload = result_lookup.get(clause_id)

            if payload:
                suggestion = ComplianceSuggestion(
                    clause_id=clause_id,
                    original_text=item['clause'].get('text', '')[:500],
                    suggested_text=payload.get('suggested_text', '')[:1000],
                    rationale=payload.get('rationale', '')[:500],
                    compliance_frameworks=payload.get('compliance_frameworks', ['GDPR']),
                    confidence=float(payload.get('confidence', 0.8)),
                    model_used=model_name,
                    source_risk=item['source_trace']
                )
            else:
                suggestion = self._template_fallback(item, model_name)

            suggestions.append(suggestion)

            monitor.log_intermediate_output(
                self.name,
                "suggestion_ready",
                {
                    'clause_id': clause_id,
                    'model_used': suggestion.model_used,
                    'confidence': suggestion.confidence
                }
            )

        return suggestions

    def _template_fallback(self, item: Dict, model_name: str) -> ComplianceSuggestion:
        """Gracefully degrade to template output when LLM data is missing."""

        clause = item['clause']
        compliance_result = item['compliance_result']
        template = item['template']

        violations = compliance_result.get('violations', [])
        violation_rules = ', '.join([v.get('rule', 'N/A') for v in violations][:2])

        return ComplianceSuggestion(
            clause_id=clause.get('id'),
            original_text=clause.get('text', '')[:500],
            suggested_text=(template or "Review required")[:1000],
            rationale=(
                "Template-driven fallback. Review for context."
                if not violation_rules else
                f"Template-based fix addressing: {violation_rules}"
            )[:500],
            compliance_frameworks=['GDPR', 'CCPA'],
            confidence=0.6,
            model_used=f"{model_name}_template_fallback",
            source_risk=item['source_trace']
        )