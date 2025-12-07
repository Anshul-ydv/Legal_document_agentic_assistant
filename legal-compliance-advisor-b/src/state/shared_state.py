from typing import TypedDict, List, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime

# Pydantic Models
class ComplianceSuggestion(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    clause_id: str
    original_text: str
    suggested_text: str
    rationale: str
    compliance_frameworks: List[str] = Field(description="Applicable frameworks like GDPR, CCPA")
    confidence: float = Field(ge=0.0, le=1.0)
    model_used: str
    source_risk: Dict = Field(default_factory=dict)

class AuditEntry(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    timestamp: datetime = Field(default_factory=datetime.now)
    agent_name: str
    action: str
    input_data: Dict
    output_data: Dict
    model_used: str
    execution_time_ms: float
    source_clause_id: Optional[str] = None

class FinalReport(BaseModel):
    document_id: str
    executive_summary: str
    total_clauses: int
    high_risk_clauses: int
    suggestions_generated: int
    compliance_status: str  # compliant, needs_review, high_risk
    recommended_actions: List[str]
    generated_at: datetime = Field(default_factory=datetime.now)

# LangGraph State
class ComplianceAdvisorState(TypedDict):
    # Input from ADK-A
    document_id: str
    adk_a_data: Dict  # Full data from ADK-A
    clauses: List[Dict]  # Simplified clause data
    risk_assessments: List[Dict]
    recommendation_trace: List[Dict]
    
    # Suggestion Generation (Agent 4)
    compliance_suggestions: List[ComplianceSuggestion]
    suggestion_count: int
    
    # Audit Trail (Agent 5)
    audit_entries: List[AuditEntry]
    audit_summary: Dict
    
    # Report Synthesis (Agent 6)
    final_report: Optional[FinalReport]
    markdown_report: str
    structured_output: Dict
    
    # Communication back to ADK-A
    ready_to_send: bool
    sent_to_adk_a: bool
    
    # Error handling
    errors: List[str]
    status: str  # processing, completed, error