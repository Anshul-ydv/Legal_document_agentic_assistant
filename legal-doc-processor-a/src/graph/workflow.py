from langgraph.graph import StateGraph, END
from src.state.shared_state import LegalDocumentState
from src.agents.document_ingestion_agent import DocumentIngestionAgent
from src.agents.planning_agent import PlanningAgent
from src.agents.parallel_insights_agent import ParallelInsightsAgent
from typing import Optional
import logging

logger = logging.getLogger(__name__)

def create_adk_a_workflow():
    """Create LangGraph workflow for ADK-A"""
    
    # Initialize agents
    ingestion_agent = DocumentIngestionAgent()
    planning_agent = PlanningAgent()
    parallel_agent = ParallelInsightsAgent()
    
    # Create workflow graph
    workflow = StateGraph(LegalDocumentState)
    
    # Add nodes
    workflow.add_node("ingest_document", ingestion_agent.process)
    workflow.add_node("plan_pipeline", planning_agent.process)
    workflow.add_node("parallel_insights", parallel_agent.process)
    
    # Define edges (sequential flow)
    workflow.set_entry_point("ingest_document")
    workflow.add_edge("ingest_document", "plan_pipeline")
    workflow.add_edge("plan_pipeline", "parallel_insights")
    workflow.add_edge("parallel_insights", END)
    
    # Compile graph
    app = workflow.compile()
    
    logger.info("ADK-A workflow compiled successfully")
    return app

def run_adk_a(document_id: str, document_path: Optional[str] = None, document_text: Optional[str] = None, document_type: str = "contract"):
    """Run ADK-A workflow"""
    
    # Initialize state
    initial_state: LegalDocumentState = {
        'document_id': document_id,
        'document_path': document_path,
        'document_text': document_text or '',
        'document_type': document_type,
        'parsed_text': '',
        'metadata': {},
        'page_count': 0,
        'document_category': document_type,
        'metadata_summary': {},
        'key_entities': [],
        'document_outline': [],
        'extracted_clauses': [],
        'clause_count': 0,
        'risk_assessments': [],
        'high_risk_count': 0,
        'overall_risk_score': 0.0,
        'document_complexity': 0.0,
        'use_complex_model': False,
        'processing_strategy': 'standard',
        'model_plan': {},
        'cost_budget': 0.0,
        'cost_spent': 0.0,
        'planning_notes': [],
        'parallel_tasks': [],
        'ready_for_suggestions': False,
        'adk_b_response': None,
        'context_bundle': {},
        'audit_log': [],
        'recommendation_trace': [],
        'errors': [],
        'status': 'pending'
    }
    
    # Create and run workflow
    app = create_adk_a_workflow()
    
    logger.info(f"Starting ADK-A workflow for document: {document_id}")
    
    try:
        # Run the workflow
        result = app.invoke(initial_state)
        
        logger.info(f"ADK-A workflow completed for document: {document_id}")
        logger.info(f"Status: {result['status']}, Clauses: {result['clause_count']}, High Risk: {result['high_risk_count']}")
        
        return result
        
    except Exception as e:
        logger.error(f"Error in ADK-A workflow: {str(e)}")
        initial_state['status'] = 'error'
        initial_state['errors'].append(f"Workflow error: {str(e)}")
        return initial_state