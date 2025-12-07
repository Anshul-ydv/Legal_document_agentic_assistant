from typing import TypedDict, List, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime

# Pydantic Models for Structured Output
class Clause(BaseModel):
    id: str = Field(description="Unique clause identifier")
    type: str = Field(description="Clause type (e.g., liability, payment, termination)")
    text: str = Field(description="Full clause text")
    location: str = Field(description="Location in document (page, section)")
    confidence: float = Field(ge=0.0, le=1.0, description="Extraction confidence")

class RiskAssessment(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    clause_id: str
    risk_level: str = Field(description="LOW, MEDIUM, HIGH, CRITICAL")
    risk_description: str = Field(description="Plain language explanation")
    risk_factors: List[str] = Field(description="Specific risk factors identified")
    severity_score: float = Field(ge=0.0, le=10.0)
    model_used: str = Field(description="Model that assessed this risk")

class AuditEntry(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    timestamp: datetime = Field(default_factory=datetime.now)
    agent_name: str
    action: str
    input_data: Dict
    output_data: Dict
    model_used: str
    execution_time_ms: float

# LangGraph State
class LegalDocumentState(TypedDict):
    # Input
    document_id: str
    document_path: Optional[str]
    document_text: str
    document_type: str  # contract, regulation, case_doc
    
    # Document Processing (Agent 1)
    parsed_text: str
    metadata: Dict
    page_count: int
    document_category: str
    metadata_summary: Dict
    key_entities: List[str]
    document_outline: List[str]
    
    # Clause Extraction (Agent 2)
    extracted_clauses: List[Clause]
    clause_count: int
    
    # Risk Detection (Agent 3)
    risk_assessments: List[RiskAssessment]
    high_risk_count: int
    overall_risk_score: float
    
    # Complexity routing
    document_complexity: float
    use_complex_model: bool
    processing_strategy: str
    model_plan: Dict
    cost_budget: float
    cost_spent: float
    planning_notes: List[str]
    parallel_tasks: List[str]
    
    # Inter-ADK communication
    ready_for_suggestions: bool
    adk_b_response: Optional[Dict]
    context_bundle: Dict
    
    # Audit Trail
    audit_log: List[AuditEntry]
    recommendation_trace: List[Dict]
    
    # Error handling
    errors: List[str]
    status: str  # processing, completed, error