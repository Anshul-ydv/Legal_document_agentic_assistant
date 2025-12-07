import google.generativeai as genai
from src.state.shared_state import LegalDocumentState, Clause, AuditEntry
from src.config import GEMINI_MODEL_STANDARD, GEMINI_MODEL_COMPLEX, GEMINI_API_KEY
from src.utils.llm import generate_with_retry
from src.monitoring.callbacks import monitor
from datetime import datetime
import json
import re
import logging

logger = logging.getLogger(__name__)

class ClauseExtractionAgent:
    """Agent 2: Extract and classify legal clauses"""
    
    def __init__(self):
        self.name = "ClauseExtractionAgent"
        self.standard_model = genai.GenerativeModel(GEMINI_MODEL_STANDARD)
        self.complex_model = genai.GenerativeModel(GEMINI_MODEL_COMPLEX)
        self.llm_enabled = bool(GEMINI_API_KEY)
    
    def process(self, state: LegalDocumentState) -> LegalDocumentState:
        """Extract and classify clauses from document"""
        context = monitor.on_agent_start(self.name, {
            'document_id': state['document_id'],
            'text_length': len(state.get('parsed_text', '')),
            'use_complex_model': state.get('use_complex_model', False)
        })
        
        try:
            text = state['parsed_text']
            model = self.complex_model if state.get('use_complex_model') else self.standard_model
            model_name = GEMINI_MODEL_COMPLEX if state.get('use_complex_model') else GEMINI_MODEL_STANDARD

            use_llm = self.llm_enabled and bool(text.strip())
            logger.info(
                "Extracting clauses using %s",
                model_name if use_llm else "pattern_fallback"
            )
            
            clauses_data = []
            if use_llm:
                prompt = f"""You are a legal document analyzer. Extract all important legal clauses from the following document.

For each clause, identify:
1. Type (e.g., indemnification, liability, payment, termination, confidentiality, jurisdiction, warranties, etc.)
2. The full text of the clause
3. Location in the document (section/paragraph reference)
4. Your confidence in the classification (0.0 to 1.0)

Document text:
{text[:8000]}  # Limit to avoid token limits

Return ONLY a valid JSON array of clauses, with no other text. Format:
[
  {{
    "id": "clause_1",
    "type": "indemnification",
    "text": "Full clause text...",
    "location": "Section 5.2",
    "confidence": 0.95
  }}
]
"""
            
                try:
                    response = generate_with_retry(model, prompt)
                    response_text = response.text.strip()
                    monitor.log_intermediate_output(self.name, "llm_response", response_text[:200])
                    json_text = re.sub(r'^```json\s*', '', response_text)
                    json_text = re.sub(r'\s*```$', '', json_text)
                    clauses_data = json.loads(json_text)
                except (json.JSONDecodeError, ValueError):
                    logger.warning("LLM returned invalid JSON, using fallback extractor")
                    clauses_data = self._fallback_extraction(text)
                except Exception as llm_err:
                    logger.warning("Gemini clause extraction failed (%s); falling back to heuristic extraction", llm_err)
                    clauses_data = self._fallback_extraction(text)
                    model_name = "pattern_fallback"
            else:
                clauses_data = self._fallback_extraction(text)
                model_name = "pattern_fallback"
            
            # Convert to Pydantic models
            extracted_clauses = []
            for i, clause_dict in enumerate(clauses_data[:20]):  # Limit to 20 clauses
                try:
                    clause = Clause(
                        id=clause_dict.get('id', f'clause_{i+1}'),
                        type=clause_dict.get('type', 'general'),
                        text=clause_dict.get('text', '')[:1000],  # Limit length
                        location=clause_dict.get('location', 'Unknown'),
                        confidence=float(clause_dict.get('confidence', 0.8))
                    )
                    extracted_clauses.append(clause)
                except Exception as e:
                    logger.warning(f"Error creating Clause object: {e}")
                    continue
            
            state['extracted_clauses'] = extracted_clauses
            state['clause_count'] = len(extracted_clauses)
            
            logger.info(f"Extracted {len(extracted_clauses)} clauses")
            
            # Create audit entry
            audit_entry = AuditEntry(
                timestamp=datetime.now(),
                agent_name=self.name,
                action="clause_extraction",
                input_data={'text_length': len(text)},
                output_data={
                    'clause_count': len(extracted_clauses),
                    'clause_types': list(set(c.type for c in extracted_clauses))
                },
                model_used=model_name,
                execution_time_ms=(datetime.now() - context['timestamp']).total_seconds() * 1000
            )
            
            state.setdefault('audit_log', []).append(audit_entry)
            
            monitor.on_agent_end(context, {
                'clause_count': len(extracted_clauses)
            }, model_name)
            
        except Exception as e:
            logger.error(f"Error in {self.name}: {str(e)}")
            monitor.on_agent_error(context, e)
            state.setdefault('errors', []).append(f"{self.name}: {str(e)}")
            state['extracted_clauses'] = []
            state['clause_count'] = 0
        
        return state
    
    def _fallback_extraction(self, text: str) -> list:
        """Fallback method using pattern matching"""
        clauses = []
        
        # Common clause patterns
        patterns = {
            'indemnification': r'indemnif[y|ication].*?[.;]',
            'liability': r'liabilit[y|ies].*?[.;]',
            'termination': r'terminat[e|ion].*?[.;]',
            'confidentiality': r'confidential.*?[.;]',
            'payment': r'payment.*?[.;]'
        }
        
        for clause_type, pattern in patterns.items():
            matches = re.finditer(pattern, text, re.IGNORECASE | re.DOTALL)
            for i, match in enumerate(matches):
                clauses.append({
                    'id': f'{clause_type}_{i+1}',
                    'type': clause_type,
                    'text': match.group(0)[:500],
                    'location': 'Pattern matched',
                    'confidence': 0.6
                })
        
        return clauses[:10]  # Limit results