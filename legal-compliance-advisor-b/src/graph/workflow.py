from langgraph.graph import StateGraph, END
from src.state.shared_state import ComplianceAdvisorState
from src.agents.suggestion_generator_agent import SuggestionGeneratorAgent
from src.agents.audit_trail_agent import AuditTrailAgent
from src.agents.report_synthesizer_agent import ReportSynthesizerAgent
import logging

logger = logging.getLogger(__name__)

def create_adk_b_workflow():
    """Create LangGraph workflow for ADK-B"""
    
    # Initialize agents
    suggestion_agent = SuggestionGeneratorAgent()
    audit_agent = AuditTrailAgent()
    report_agent = ReportSynthesizerAgent()
    
    # Create workflow graph
    workflow = StateGraph(ComplianceAdvisorState)
    
    # Add nodes
    workflow.add_node("generate_suggestions", suggestion_agent.process)
    workflow.add_node("create_audit_trail", audit_agent.process)
    workflow.add_node("synthesize_report", report_agent.process)
    
    # Define edges (sequential flow)
    workflow.set_entry_point("generate_suggestions")
    workflow.add_edge("generate_suggestions", "create_audit_trail")
    workflow.add_edge("create_audit_trail", "synthesize_report")
    workflow.add_edge("synthesize_report", END)
    
    # Compile graph
    app = workflow.compile()
    
    logger.info("ADK-B workflow compiled successfully")
    return app

def run_adk_b(document_id: str, adk_a_data: dict):
    """Run ADK-B workflow with data from ADK-A"""
    
    # Extract necessary data from ADK-A
    clauses = [
        {
            'id': c.get('id', ''),
            'type': c.get('type', ''),
            'text': c.get('text', ''),
            'location': c.get('location', '')
        }
        for c in adk_a_data.get('extracted_clauses', [])
    ]
    
    risk_assessments = [
        {
            'clause_id': r.get('clause_id', ''),
            'risk_level': r.get('risk_level', ''),
            'risk_description': r.get('risk_description', ''),
            'severity_score': r.get('severity_score', 0)
        }
        for r in adk_a_data.get('risk_assessments', [])
    ]
    recommendation_trace = adk_a_data.get('recommendation_trace', [])
    
    # Initialize state
    initial_state: ComplianceAdvisorState = {
        'document_id': document_id,
        'adk_a_data': adk_a_data,
        'clauses': clauses,
        'risk_assessments': risk_assessments,
        'recommendation_trace': recommendation_trace,
        'compliance_suggestions': [],
        'suggestion_count': 0,
        'audit_entries': [],
        'audit_summary': {},
        'final_report': None,
        'markdown_report': '',
        'structured_output': {},
        'ready_to_send': False,
        'sent_to_adk_a': False,
        'errors': [],
        'status': 'processing'
    }
    
    # Create and run workflow
    app = create_adk_b_workflow()
    
    logger.info(f"Starting ADK-B workflow for document: {document_id}")
    
    try:
        # Run the workflow
        result = app.invoke(initial_state)
        
        logger.info(f"ADK-B workflow completed for document: {document_id}")
        logger.info(f"Status: {result['status']}, Suggestions: {result['suggestion_count']}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error in ADK-B workflow: {str(e)}")
        initial_state['status'] = 'error'
        initial_state['errors'].append(f"Workflow error: {str(e)}")
        return initial_state