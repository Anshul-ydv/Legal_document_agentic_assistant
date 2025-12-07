import google.generativeai as genai
from src.state.shared_state import ComplianceAdvisorState, FinalReport
from src.config import GEMINI_MODEL_COMPLEX
from src.monitoring.callbacks import monitor
from src.utils.llm import generate_with_retry
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class ReportSynthesizerAgent:
    """Agent 6: Synthesize final comprehensive report"""
    
    def __init__(self):
        self.name = "ReportSynthesizerAgent"
        self.model = genai.GenerativeModel(GEMINI_MODEL_COMPLEX)
    
    def process(self, state: ComplianceAdvisorState) -> ComplianceAdvisorState:
        """Generate final report"""
        context = monitor.on_agent_start(self.name, {
            'document_id': state['document_id']
        })
        
        try:
            # Gather data
            adk_a_data = state.get('adk_a_data', {})
            total_clauses = adk_a_data.get('clause_count', 0)
            high_risk_count = adk_a_data.get('high_risk_count', 0)
            suggestions = state.get('compliance_suggestions', [])
            
            # Determine compliance status
            if high_risk_count == 0:
                compliance_status = "compliant"
            elif high_risk_count <= 2:
                compliance_status = "needs_review"
            else:
                compliance_status = "high_risk"

            monitor.log_intermediate_output(
                self.name,
                "status_diagnostics",
                {
                    'total_clauses': total_clauses,
                    'high_risk_count': high_risk_count,
                    'suggestions_available': len(suggestions),
                    'computed_status': compliance_status
                }
            )
            
            # Generate executive summary using LLM
            executive_summary = self._generate_executive_summary(
                total_clauses,
                high_risk_count,
                len(suggestions),
                compliance_status
            )
            
            # Generate recommended actions
            recommended_actions = self._generate_recommended_actions(
                suggestions,
                compliance_status
            )

            monitor.log_intermediate_output(
                self.name,
                "recommended_actions",
                {
                    'actions_preview': recommended_actions[:3],
                    'action_total': len(recommended_actions)
                }
            )
            
            # Create Final Report
            final_report = FinalReport(
                document_id=state['document_id'],
                executive_summary=executive_summary,
                total_clauses=total_clauses,
                high_risk_clauses=high_risk_count,
                suggestions_generated=len(suggestions),
                compliance_status=compliance_status,
                recommended_actions=recommended_actions,
                generated_at=datetime.now()
            )
            
            state['final_report'] = final_report
            
            # Generate Markdown + structured outputs for ADK web consumption
            markdown_report = self._create_markdown_report(state, final_report)
            state['markdown_report'] = markdown_report
            state['structured_output'] = self._build_structured_output(
                state,
                final_report,
                markdown_report
            )

            monitor.log_intermediate_output(
                self.name,
                "report_payload",
                {
                    'markdown_length': len(markdown_report),
                    'structured_sections': list(state['structured_output'].keys())
                }
            )
            
            # Mark as ready to send back to ADK-A
            state['ready_to_send'] = True
            state['status'] = 'completed'
            
            logger.info(f"Final report generated for document: {state['document_id']}")
            
            monitor.on_agent_end(context, {
                'compliance_status': compliance_status,
                'report_length': len(markdown_report),
                'structured_suggestions': len(state['structured_output'].get('suggestions', []))
            }, GEMINI_MODEL_COMPLEX)
            
        except Exception as e:
            logger.error(f"Error in {self.name}: {str(e)}")
            monitor.on_agent_error(context, e)
            state['errors'].append(f"{self.name}: {str(e)}")
            state['status'] = 'error'
        
        return state
    
    def _generate_executive_summary(self, total_clauses: int, high_risk: int, 
                                   suggestions: int, status: str) -> str:
        """Generate executive summary using LLM"""
        
        prompt = f"""Generate a concise executive summary for a legal document analysis.

Document Analysis Results:
- Total Clauses Analyzed: {total_clauses}
- High-Risk Clauses Identified: {high_risk}
- Compliance Suggestions Generated: {suggestions}
- Overall Compliance Status: {status}

Write a professional 2-3 sentence executive summary highlighting key findings and recommendations.
"""
        
        try:
            response = generate_with_retry(self.model, prompt)
            return response.text.strip()
        except Exception as e:
            logger.warning(f"LLM summary generation failed: {e}")
            return f"""This legal document contains {total_clauses} clauses, of which {high_risk} 
            were identified as high-risk. Our AI system has generated {suggestions} compliance 
            suggestions to address potential legal exposures. The document's overall compliance 
            status is: {status}."""
    
    def _generate_recommended_actions(self, suggestions: list, status: str) -> list:
        """Generate prioritized action items"""
        
        actions = []
        
        if status == "high_risk":
            actions.append("URGENT: Review and address all high-risk clauses immediately")
            actions.append("Consult with legal counsel before finalizing this agreement")
        
        if status == "needs_review":
            actions.append("Review flagged clauses with legal team")
            actions.append("Consider implementing suggested compliance improvements")
        
        # Add specific actions based on suggestions
        frameworks = set()
        for suggestion in suggestions[:5]:  # Top 5
            frameworks.update(suggestion.compliance_frameworks)
            
        if 'GDPR' in frameworks:
            actions.append("Ensure GDPR compliance for data processing clauses")
        if 'CCPA' in frameworks:
            actions.append("Review California privacy requirements")
        
        actions.append("Maintain audit trail for all document modifications")
        actions.append("Schedule periodic compliance review (recommended: quarterly)")
        
        return actions[:5]  # Limit to top 5 actions
    
    def _create_markdown_report(self, state: ComplianceAdvisorState, 
                               final_report: FinalReport) -> str:
        """Create comprehensive Markdown report"""
        
        adk_a_data = state.get('adk_a_data', {})
        suggestions = state.get('compliance_suggestions', [])
        audit_summary = state.get('audit_summary', {})
        
        report = f"""# Legal Document Analysis Report

**Document ID:** {final_report.document_id}  
**Generated:** {final_report.generated_at.strftime('%Y-%m-%d %H:%M:%S')}  
**Compliance Status:** {final_report.compliance_status.upper()}

---

## Executive Summary

{final_report.executive_summary}

---

## Analysis Overview

| Metric | Count |
|--------|-------|
| Total Clauses Analyzed | {final_report.total_clauses} |
| High-Risk Clauses | {final_report.high_risk_clauses} |
| Compliance Suggestions | {final_report.suggestions_generated} |
| Overall Risk Score | {adk_a_data.get('overall_risk_score', 0):.2f}/10.0 |

---

## Recommended Actions

"""
        
        for i, action in enumerate(final_report.recommended_actions, 1):
            report += f"{i}. {action}\n"
        
        report += "\n---\n\n## Compliance Suggestions\n\n"
        
        for i, suggestion in enumerate(suggestions[:10], 1):  # Limit to 10
            report += f"""### Suggestion {i}: {suggestion.clause_id}

**Original Clause (excerpt):**  
{suggestion.original_text[:200]}...

**Suggested Revision:**  
{suggestion.suggested_text[:300]}...

**Rationale:**  
{suggestion.rationale}

**Compliance Frameworks:** {', '.join(suggestion.compliance_frameworks)}  
**Confidence:** {suggestion.confidence:.0%}  
**Model Used:** {suggestion.model_used}

---

"""
        
        report += f"""## Audit Trail Summary

- **Total Actions Logged:** {audit_summary.get('total_actions', 0)}
- **ADK-A Actions:** {audit_summary.get('adk_a_actions', 0)}
- **ADK-B Actions:** {audit_summary.get('adk_b_actions', 0)}
- **Models Used:** {', '.join(audit_summary.get('models_used', []))}
- **Compliance Frameworks:** {', '.join(audit_summary.get('compliance_frameworks_checked', []))}

---

## Next Steps

1. Review this report with your legal team
2. Implement high-priority suggestions
3. Document any deviations with justification
4. Schedule follow-up compliance review

**Note:** This analysis is provided for informational purposes and does not constitute legal advice. 
Always consult with qualified legal counsel for final review.
"""
        
        return report

    def _build_structured_output(self, state: ComplianceAdvisorState,
                                 final_report: FinalReport,
                                 markdown_report: str) -> dict:
        """Build machine-readable summary for downstream orchestration"""
        suggestions_payload = []
        for suggestion in state.get('compliance_suggestions', []):
            suggestions_payload.append({
                'clause_id': suggestion.clause_id,
                'source_risk': suggestion.source_risk,
                'original_text_excerpt': suggestion.original_text[:200],
                'suggested_text': suggestion.suggested_text,
                'rationale': suggestion.rationale,
                'compliance_frameworks': suggestion.compliance_frameworks,
                'confidence': suggestion.confidence,
                'model_used': suggestion.model_used
            })

        risk_highlights = []
        for assessment in state.get('risk_assessments', [])[:5]:
            risk_highlights.append({
                'clause_id': assessment.get('clause_id'),
                'risk_level': assessment.get('risk_level'),
                'severity_score': assessment.get('severity_score'),
                'risk_description': assessment.get('risk_description'),
                'model_used': assessment.get('model_used')
            })

        audit_summary = state.get('audit_summary', {})
        audit_timestamp = audit_summary.get('audit_timestamp')
        if isinstance(audit_timestamp, datetime):
            audit_summary = {**audit_summary, 'audit_timestamp': audit_timestamp.isoformat()}

        structured_output = {
            'document_id': final_report.document_id,
            'status': state.get('status'),
            'summary': {
                'executive_summary': final_report.executive_summary,
                'compliance_status': final_report.compliance_status,
                'total_clauses': final_report.total_clauses,
                'high_risk_clauses': final_report.high_risk_clauses,
                'suggestions_generated': final_report.suggestions_generated,
                'generated_at': final_report.generated_at.isoformat()
            },
            'recommended_actions': final_report.recommended_actions,
            'risk_highlights': risk_highlights,
            'suggestions': suggestions_payload,
            'audit': {
                'summary': audit_summary,
                'recommendation_trace': state.get('recommendation_trace', [])
            },
            'reports': {
                'markdown': markdown_report,
                'format': 'markdown',
                'length': len(markdown_report)
            }
        }

        return structured_output