from src.state.shared_state import LegalDocumentState, AuditEntry
from src.tools.pdf_parser import DocumentParser
from src.monitoring.callbacks import monitor
from datetime import datetime
from collections import Counter
import logging

logger = logging.getLogger(__name__)

class DocumentIngestionAgent:
    """Agent 1: Parse and prepare documents for analysis"""
    
    def __init__(self):
        self.parser = DocumentParser()
        self.name = "DocumentIngestionAgent"
    
    def process(self, state: LegalDocumentState) -> LegalDocumentState:
        """Parse document and extract metadata"""
        context = monitor.on_agent_start(self.name, {
            'document_id': state['document_id'],
            'document_type': state.get('document_type', 'unknown')
        })
        
        try:
            # Parse document if path provided
            if state.get('document_path'):
                logger.info(f"Parsing document: {state['document_path']}")
                parsed_result = self.parser.parse_document(state['document_path'])
                
                state['parsed_text'] = parsed_result['full_text']
                state['metadata'] = parsed_result['metadata']
                state['page_count'] = parsed_result['metadata'].get('page_count', 0)
                
                monitor.log_intermediate_output(
                    self.name,
                    "document_parsed",
                    f"Extracted {len(parsed_result['full_text'])} characters"
                )
            else:
                # Use provided text
                state['parsed_text'] = state.get('document_text', '')
                state['metadata'] = {'format': 'text'}
                state['page_count'] = 1
            
            # Estimate document complexity for model routing
            complexity = self.parser.estimate_complexity(state['parsed_text'])
            state['document_complexity'] = complexity
            state['use_complex_model'] = complexity > 0.7
            state['document_category'] = self._categorize_document(state)
            state['metadata_summary'] = {
                'language': state['metadata'].get('language', 'unknown'),
                'format': state['metadata'].get('format', 'text'),
                'size_bytes': len(state['parsed_text'].encode('utf-8'))
            }
            state['key_entities'] = self._extract_entities(state['parsed_text'])
            state['document_outline'] = []
            
            logger.info(f"Document complexity: {complexity:.2f} - Using {'Pro' if state['use_complex_model'] else 'Flash'} model")
            
            # Create audit entry
            audit_entry = AuditEntry(
                timestamp=datetime.now(),
                agent_name=self.name,
                action="document_ingestion",
                input_data={
                    'document_id': state['document_id'],
                    'has_path': bool(state.get('document_path'))
                },
                output_data={
                    'text_length': len(state['parsed_text']),
                    'page_count': state['page_count'],
                    'complexity': complexity
                },
                model_used="DocumentParser",
                execution_time_ms=(datetime.now() - context['timestamp']).total_seconds() * 1000
            )
            
            if 'audit_log' not in state:
                state['audit_log'] = []
            state['audit_log'].append(audit_entry)
            
            state['status'] = 'processing'
            
            monitor.on_agent_end(context, {
                'text_length': len(state['parsed_text']),
                'complexity': complexity
            }, "DocumentParser")
            
        except Exception as e:
            logger.error(f"Error in {self.name}: {str(e)}")
            monitor.on_agent_error(context, e)
            
            if 'errors' not in state:
                state['errors'] = []
            state['errors'].append(f"{self.name}: {str(e)}")
            state['status'] = 'error'
        
        return state

    def _categorize_document(self, state: LegalDocumentState) -> str:
        """Heuristic document categorization"""
        doc_type = (state.get('document_type') or 'contract').lower()
        if 'policy' in doc_type:
            return 'policy'
        if 'privacy' in doc_type:
            return 'privacy'
        if 'sla' in doc_type:
            return 'sla'
        text = state.get('parsed_text', '').lower()
        if 'data processing' in text or 'controller' in text:
            return 'dpa'
        if 'service level' in text or 'uptime' in text:
            return 'sla'
        if 'employment' in text:
            return 'employment'
        return 'contract'

    def _extract_entities(self, text: str) -> list:
        """Very light-weight entity detection for planning"""
        tokens = [token.strip('.,()') for token in text.split() if token.istitle()]
        most_common = [entity for entity, _ in Counter(tokens).most_common(5)]
        return most_common