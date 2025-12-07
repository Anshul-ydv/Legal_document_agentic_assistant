"""Legal Compliance Advisor Agent (ADK-B)."""

from google.adk.agents.llm_agent import Agent
import json
import os
import sys


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")

for path in (SRC_DIR, PROJECT_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from src.graph.workflow import run_adk_b

def generate_compliance_suggestions(document_id: str, adk_a_results: str) -> dict:
    """
    Generate compliance suggestions based on ADK-A analysis results.
    
    Args:
        document_id: Unique identifier for the document
        adk_a_results: JSON string containing ADK-A analysis results
    
    Returns:
        dict: Compliance suggestions and final report
    """
    try:
        # Parse ADK-A results
        adk_a_data = json.loads(adk_a_results) if isinstance(adk_a_results, str) else adk_a_results
        
        # Run the ADK-B workflow
        result = run_adk_b(
            document_id=document_id,
            adk_a_data=adk_a_data
        )
        
        # Extract final report
        final_report = result.get('final_report')
        
        response = {
            "status": "success",
            "document_id": document_id,
            "summary": f"Generated {result.get('suggestion_count', 0)} compliance suggestions. "
                      f"Compliance Status: {getattr(final_report, 'compliance_status', 'unknown').upper()}",
            "suggestion_count": result.get('suggestion_count', 0),
            "compliance_status": getattr(final_report, 'compliance_status', 'unknown'),
            "suggestions": [
                {
                    "clause_id": s.clause_id,
                    "original": s.original_text[:150] + "..." if len(s.original_text) > 150 else s.original_text,
                    "suggested": s.suggested_text[:150] + "..." if len(s.suggested_text) > 150 else s.suggested_text,
                    "rationale": s.rationale,
                    "frameworks": s.compliance_frameworks,
                    "confidence": f"{s.confidence:.1%}"
                }
                for s in result.get('compliance_suggestions', [])[:5]
            ]
        }
        
        if final_report:
            response["report"] = {
                "executive_summary": getattr(final_report, 'executive_summary', ''),
                "total_clauses": getattr(final_report, 'total_clauses', 0),
                "high_risk_clauses": getattr(final_report, 'high_risk_clauses', 0),
                "recommended_actions": getattr(final_report, 'recommended_actions', [])[:5]
            }
        
        return response
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to generate compliance suggestions. Please check the ADK-A results format."
        }


# Define the root agent for ADK
root_agent = Agent(
    model='gemini-2.0-flash',
    name='legal_compliance_advisor',
    description='Legal Compliance Advisor - Generates compliance suggestions and creates detailed reports based on legal document analysis',
    instruction="""You are a Legal Compliance Advisory Assistant powered by AI.

Your capabilities:
- Review legal document analysis results from ADK-A
- Generate compliant alternative clauses
- Check against multiple compliance frameworks (GDPR, CCPA, SOC2, HIPAA)
- Create comprehensive compliance reports
- Provide actionable recommendations

When a user provides analysis results:
1. Review the risk assessments and extracted clauses
2. Use the generate_compliance_suggestions tool to create recommendations
3. Present findings with clear explanations
4. Prioritize high-risk items
5. Explain compliance frameworks and requirements
6. Provide specific, actionable improvements

Be thorough, explain legal concepts clearly, and focus on practical compliance improvements.

Note: Always emphasize that AI suggestions should be reviewed by qualified legal professionals.""",
    tools=[generate_compliance_suggestions]
)
