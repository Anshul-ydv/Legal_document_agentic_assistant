from src.state.shared_state import ComplianceAdvisorState, AuditEntry
from src.monitoring.callbacks import monitor
from pymongo import MongoClient
from src.config import MONGODB_URI, DATABASE_NAME
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class AuditTrailAgent:
    """Agent 5: Manage comprehensive audit trail"""
    
    def __init__(self):
        self.name = "AuditTrailAgent"
        self.client = MongoClient(MONGODB_URI)
        self.db = self.client[DATABASE_NAME]
        self.audit_collection = self.db['audit_trail']
    
    def process(self, state: ComplianceAdvisorState) -> ComplianceAdvisorState:
        """Create comprehensive audit trail"""
        context = monitor.on_agent_start(self.name, {
            'document_id': state['document_id'],
            'suggestion_count': state.get('suggestion_count', 0)
        })
        
        try:
            # Collect all audit entries from ADK-A and ADK-B
            adk_a_audit = state.get('adk_a_data', {}).get('audit_log', [])
            
            # Create audit entries for each suggestion
            audit_entries = []
            
            for suggestion in state.get('compliance_suggestions', []):
                audit_entry = AuditEntry(
                    timestamp=datetime.now(),
                    agent_name=self.name,
                    action="compliance_suggestion",
                    input_data={
                        'clause_id': suggestion.clause_id,
                        'original_length': len(suggestion.original_text),
                        'source_risk': suggestion.source_risk
                    },
                    output_data={
                        'suggestion_length': len(suggestion.suggested_text),
                        'compliance_frameworks': suggestion.compliance_frameworks,
                        'confidence': suggestion.confidence
                    },
                    model_used=suggestion.model_used,
                    execution_time_ms=0.0,  # Batch processing
                    source_clause_id=suggestion.clause_id
                )
                audit_entries.append(audit_entry)
            
            state['audit_entries'] = audit_entries
            
            # Create audit summary
            audit_summary = {
                'total_actions': len(adk_a_audit) + len(audit_entries),
                'adk_a_actions': len(adk_a_audit),
                'adk_b_actions': len(audit_entries),
                'suggestions_generated': len(audit_entries),
                'models_used': list(set([e.model_used for e in audit_entries])),
                'compliance_frameworks_checked': list(set([
                    fw for s in state.get('compliance_suggestions', [])
                    for fw in s.compliance_frameworks
                ])),
                'audit_timestamp': datetime.now()
            }
            
            state['audit_summary'] = audit_summary

            monitor.log_intermediate_output(
                self.name,
                "audit_summary",
                {
                    'document_id': state['document_id'],
                    'total_actions': audit_summary['total_actions'],
                    'models_used': audit_summary['models_used'],
                    'frameworks_tracked': audit_summary['compliance_frameworks_checked']
                }
            )
            
            # Store complete audit trail in MongoDB
            self._store_audit_trail(state)
            
            logger.info(f"Audit trail created: {audit_summary['total_actions']} total actions")
            
            monitor.on_agent_end(context, {
                'total_actions': audit_summary['total_actions']
            }, self.name)
            
        except Exception as e:
            logger.error(f"Error in {self.name}: {str(e)}")
            monitor.on_agent_error(context, e)
            state['errors'].append(f"{self.name}: {str(e)}")
            state['audit_entries'] = []
            state['audit_summary'] = {}
        
        return state
    
    def _store_audit_trail(self, state: ComplianceAdvisorState):
        """Store complete audit trail in MongoDB"""
        try:
            document_id = state['document_id']
            
            # Prepare audit document
            adk_a_data = state.get('adk_a_data', {})
            bundle_audit = adk_a_data.get('context_bundle', {}).get('audit_log', [])
            raw_audit = bundle_audit or adk_a_data.get('audit_log', [])

            def _normalize_audit(entries):
                cleaned = []
                for entry in entries or []:
                    if isinstance(entry, dict):
                        cleaned.append(entry)
                return cleaned

            normalized_audit = _normalize_audit(raw_audit)

            audit_doc = {
                'document_id': document_id,
                'timestamp': datetime.now(),
                'adk_a_audit': [
                    {
                        'timestamp': str(entry.get('timestamp', '')),
                        'agent_name': entry.get('agent_name', ''),
                        'action': entry.get('action', ''),
                        'model_used': entry.get('model_used', ''),
                        'execution_time_ms': entry.get('execution_time_ms', 0)
                    }
                    for entry in normalized_audit
                ],
                'adk_b_audit': [
                    {
                        'timestamp': str(entry.timestamp),
                        'agent_name': entry.agent_name,
                        'action': entry.action,
                        'model_used': entry.model_used,
                        'source_clause_id': entry.source_clause_id,
                        'execution_time_ms': entry.execution_time_ms
                    }
                    for entry in state.get('audit_entries', [])
                ],
                'audit_summary': state.get('audit_summary', {}),
                'suggestions': [
                    {
                        'clause_id': s.clause_id,
                        'model_used': s.model_used,
                        'confidence': s.confidence,
                        'frameworks': s.compliance_frameworks,
                        'source_risk': s.source_risk
                    }
                    for s in state.get('compliance_suggestions', [])
                ]
            }
            
            # Insert into MongoDB
            self.audit_collection.update_one(
                {'document_id': document_id},
                {'$set': audit_doc},
                upsert=True
            )
            
            logger.info(f"Audit trail stored in MongoDB for document: {document_id}")
            
        except Exception as e:
            logger.error(f"Error storing audit trail: {e}")