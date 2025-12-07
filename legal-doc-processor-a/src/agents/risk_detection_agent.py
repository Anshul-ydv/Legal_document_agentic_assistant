import google.generativeai as genai
from src.state.shared_state import LegalDocumentState, RiskAssessment, AuditEntry
from src.config import GEMINI_MODEL_STANDARD, GEMINI_MODEL_COMPLEX, GEMINI_API_KEY
from src.tools.rag_retriever import RAGRetriever
from src.monitoring.callbacks import monitor
from src.utils.llm import generate_with_retry
from datetime import datetime
import json
import re
import logging

logger = logging.getLogger(__name__)

class RiskDetectionAgent:
    """Agent 3: Assess risk level of extracted clauses"""
    
    def __init__(self):
        self.name = "RiskDetectionAgent"
        self.standard_model = genai.GenerativeModel(GEMINI_MODEL_STANDARD)
        self.complex_model = genai.GenerativeModel(GEMINI_MODEL_COMPLEX)
        self.rag_retriever = RAGRetriever()
        self.llm_enabled = bool(GEMINI_API_KEY)
    
    def process(self, state: LegalDocumentState) -> LegalDocumentState:
        """Assess risks for each extracted clause"""
        context = monitor.on_agent_start(self.name, {
            'document_id': state['document_id'],
            'clause_count': state.get('clause_count', 0)
        })
        
        try:
            clauses = state.get('extracted_clauses', [])
            plan = state.get('model_plan', {})
            planned_model = plan.get('risk_model', GEMINI_MODEL_STANDARD)
            model = self.complex_model if 'pro' in planned_model else self.standard_model
            default_model_name = planned_model if self.llm_enabled else 'heuristic_risk'
            
            logger.info(f"Assessing risk for {len(clauses)} clauses using {default_model_name}")
            
            risk_assessments = []
            high_risk_count = 0
            total_risk_score = 0.0
            
            recommendation_trace = state.get('recommendation_trace', [])

            for clause in clauses:
                try:
                    # Get relevant precedents from RAG
                    similar_clauses = self.rag_retriever.retrieve_similar_clauses(
                        clause.text,
                        top_k=2
                    )
                    risk_context = self.rag_retriever.get_risk_context(clause.type)
                    
                    monitor.log_intermediate_output(
                        self.name,
                        f"rag_retrieval_{clause.id}",
                        f"Found {len(similar_clauses)} similar clauses"
                    )
                    
                    use_llm = self.llm_enabled and bool(clause.text.strip())
                    model_used = 'heuristic_risk'
                    if use_llm:
                        prompt = f"""You are a legal risk analyst. Assess the risk of this clause.

Clause ID: {clause.id}
Clause Type: {clause.type}
Clause Text: {clause.text}

Similar Precedents:
{json.dumps([c['text'][:200] for c in similar_clauses], indent=2)}

Known Risks for {clause.type}:
{json.dumps(risk_context.get('common_risks', []), indent=2)}

Assess:
1. Risk Level (LOW, MEDIUM, HIGH, or CRITICAL)
2. Plain language explanation of the risk
3. Specific risk factors
4. Severity score (0.0 to 10.0)

Return ONLY a valid JSON object:
{{
  "risk_level": "HIGH",
  "risk_description": "This clause presents significant liability exposure because...",
  "risk_factors": ["Factor 1", "Factor 2"],
  "severity_score": 7.5
}}
"""
                    
                        try:
                            response = generate_with_retry(model, prompt)
                            response_text = response.text.strip()
                            json_text = re.sub(r'^```json\s*', '', response_text)
                            json_text = re.sub(r'\s*```$', '', json_text)
                            risk_data = json.loads(json_text)
                        except (json.JSONDecodeError, ValueError):
                            logger.warning("Invalid JSON from risk model; using heuristic fallback")
                            risk_data = self._fallback_risk_assessment(clause.type)
                        except Exception as llm_err:
                            logger.warning("Risk LLM call failed (%s); using heuristic fallback", llm_err)
                            risk_data = self._fallback_risk_assessment(clause.type)
                        else:
                            model_used = default_model_name
                    else:
                        risk_data = self._fallback_risk_assessment(clause.type)
                    
                    # Create RiskAssessment object
                    risk = RiskAssessment(
                        clause_id=clause.id,
                        risk_level=risk_data.get('risk_level', 'MEDIUM'),
                        risk_description=risk_data.get('risk_description', 'Standard risk assessment'),
                        risk_factors=risk_data.get('risk_factors', ['Requires review']),
                        severity_score=float(risk_data.get('severity_score', 5.0)),
                        model_used=model_used
                    )
                    
                    risk_assessments.append(risk)
                    total_risk_score += risk.severity_score
                    
                    if risk.risk_level in ['HIGH', 'CRITICAL']:
                        high_risk_count += 1
                        recommendation_trace.append({
                            'clause_id': clause.id,
                            'source_text': clause.text[:400],
                            'risk_level': risk.risk_level,
                            'severity_score': risk.severity_score,
                            'model_used': risk.model_used
                        })
                    
                except Exception as e:
                    logger.warning(f"Error assessing clause {clause.id}: {e}")
                    continue
            
            state['risk_assessments'] = risk_assessments
            state['high_risk_count'] = high_risk_count
            state['overall_risk_score'] = total_risk_score / max(len(risk_assessments), 1)
            state['recommendation_trace'] = recommendation_trace
            state['cost_spent'] = min(
                state.get('cost_budget', 0),
                state.get('cost_spent', 0) + (0.35 if 'pro' in default_model_name else 0.1)
            )
            state['context_bundle'] = {
                'document_id': state['document_id'],
                'metadata_summary': state.get('metadata_summary', {}),
                'key_entities': state.get('key_entities', []),
                'document_outline': state.get('document_outline', []),
                'extracted_clauses': [clause.dict() for clause in state.get('extracted_clauses', [])],
                'risk_assessments': [assessment.dict() for assessment in risk_assessments],
                'recommendation_trace': recommendation_trace,
                'planning_notes': state.get('planning_notes', []),
                'audit_log': [entry.dict() for entry in state.get('audit_log', [])]
            }
            
            logger.info(
                f"Risk assessment complete: {high_risk_count} high-risk clauses, "
                f"overall score: {state['overall_risk_score']:.2f}"
            )
            
            # Ready to send to ADK-B when there are actionable items
            state['ready_for_suggestions'] = high_risk_count > 0
            
            # Create audit entry
            audit_entry = AuditEntry(
                timestamp=datetime.now(),
                agent_name=self.name,
                action="risk_detection",
                input_data={'clause_count': len(clauses)},
                output_data={
                    'risk_assessment_count': len(risk_assessments),
                    'high_risk_count': high_risk_count,
                    'overall_risk_score': state['overall_risk_score']
                },
                model_used=default_model_name,
                execution_time_ms=(datetime.now() - context['timestamp']).total_seconds() * 1000
            )
            
            state['audit_log'].append(audit_entry)
            
            monitor.on_agent_end(context, {
                'assessment_count': len(risk_assessments),
                'high_risk_count': high_risk_count
            }, default_model_name)
            
        except Exception as e:
            logger.error(f"Error in {self.name}: {str(e)}")
            monitor.on_agent_error(context, e)
            state['errors'].append(f"{self.name}: {str(e)}")
            state['risk_assessments'] = []
            state['high_risk_count'] = 0
            state['overall_risk_score'] = 0.0
        
        return state
    
    def _fallback_risk_assessment(self, clause_type: str) -> dict:
        """Fallback risk assessment based on clause type"""
        risk_defaults = {
            'indemnification': {'risk_level': 'HIGH', 'severity_score': 7.0},
            'liability': {'risk_level': 'HIGH', 'severity_score': 8.0},
            'termination': {'risk_level': 'MEDIUM', 'severity_score': 5.0},
            'confidentiality': {'risk_level': 'MEDIUM', 'severity_score': 6.0},
            'payment': {'risk_level': 'MEDIUM', 'severity_score': 5.5}
        }
        
        defaults = risk_defaults.get(clause_type.lower(), {
            'risk_level': 'MEDIUM',
            'severity_score': 5.0
        })
        
        return {
            'risk_level': defaults['risk_level'],
            'risk_description': f'Standard {clause_type} clause requires review',
            'risk_factors': ['Standard terms', 'Requires legal review'],
            'severity_score': defaults['severity_score']
        }