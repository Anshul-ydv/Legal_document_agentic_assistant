from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class ComplianceChecker:
    """MCP Tool 3: Check clauses against compliance frameworks"""
    
    def __init__(self):
        # Compliance rules database
        self.compliance_rules = {
            'GDPR': {
                'data_processing': [
                    'Must specify lawful basis for processing',
                    'Must include data subject rights',
                    'Must specify data retention periods',
                    'Must include data breach notification procedures'
                ],
                'liability': [
                    'Cannot exclude liability for gross negligence',
                    'Must include data protection impact assessments'
                ]
            },
            'CCPA': {
                'data_processing': [
                    'Must provide opt-out mechanisms',
                    'Must disclose data selling practices',
                    'Must honor "Do Not Sell" requests'
                ],
                'privacy': [
                    'Must provide privacy notice',
                    'Must allow data deletion requests'
                ]
            },
            'SOC2': {
                'security': [
                    'Must implement access controls',
                    'Must have incident response procedures',
                    'Must conduct regular security assessments'
                ],
                'availability': [
                    'Must define uptime commitments',
                    'Must have disaster recovery plans'
                ]
            },
            'ISO27001': {
                'security': [
                    'Must implement information security management system',
                    'Must conduct risk assessments',
                    'Must have security policies and procedures'
                ]
            },
            'HIPAA': {
                'privacy': [
                    'Must protect PHI (Protected Health Information)',
                    'Must implement minimum necessary standard',
                    'Must have Business Associate Agreements'
                ],
                'security': [
                    'Must implement administrative safeguards',
                    'Must implement physical safeguards',
                    'Must implement technical safeguards'
                ]
            }
        }
    
    def check_clause_compliance(self, clause_text: str, clause_type: str, 
                                frameworks: Optional[List[str]] = None) -> Dict:
        """Check if a clause complies with specified frameworks"""
        
        if frameworks is None:
            frameworks = ['GDPR', 'CCPA']  # Default frameworks
        
        logger.info(f"Checking compliance for {clause_type} clause against {frameworks}")
        
        results = {
            'compliant': True,
            'frameworks_checked': frameworks,
            'violations': [],
            'recommendations': []
        }
        
        clause_lower = clause_text.lower()
        
        for framework in frameworks:
            if framework not in self.compliance_rules:
                continue
            
            framework_rules = self.compliance_rules[framework]
            
            # Check relevant rule categories
            relevant_categories = self._get_relevant_categories(clause_type)
            
            for category in relevant_categories:
                if category in framework_rules:
                    rules = framework_rules[category]
                    
                    for rule in rules:
                        # Simple keyword checking (in production, use NLP)
                        if not self._check_rule_compliance(clause_lower, rule):
                            results['compliant'] = False
                            results['violations'].append({
                                'framework': framework,
                                'rule': rule,
                                'category': category
                            })
                            results['recommendations'].append(
                                f"Add compliance with: {rule}"
                            )
        
        return results
    
    def _get_relevant_categories(self, clause_type: str) -> List[str]:
        """Map clause types to compliance categories"""
        mapping = {
            'data_processing': ['data_processing', 'privacy'],
            'privacy': ['privacy', 'data_processing'],
            'confidentiality': ['privacy', 'security'],
            'security': ['security'],
            'liability': ['liability'],
            'indemnification': ['liability'],
            'termination': ['general'],
            'payment': ['general']
        }
        
        return mapping.get(clause_type.lower(), ['general'])
    
    def _check_rule_compliance(self, clause_text: str, rule: str) -> bool:
        """Simple keyword-based compliance check"""
        # Extract key terms from rule
        rule_lower = rule.lower()
        
        keywords = {
            'data subject rights': ['rights', 'access', 'deletion', 'rectification'],
            'retention periods': ['retention', 'period', 'duration'],
            'breach notification': ['breach', 'notification', 'notify'],
            'opt-out': ['opt-out', 'opt out', 'unsubscribe'],
            'access controls': ['access', 'control', 'authorization'],
            'disaster recovery': ['disaster', 'recovery', 'backup'],
            'phi': ['phi', 'protected health', 'health information']
        }
        
        # Check if rule keywords are mentioned
        for key_concept, terms in keywords.items():
            if key_concept in rule_lower:
                return any(term in clause_text for term in terms)
        
        # Default: assume compliant if no specific check
        return True
    
    def get_framework_requirements(self, framework: str, clause_type: str) -> List[str]:
        """Get specific requirements for a framework and clause type"""
        if framework not in self.compliance_rules:
            return []
        
        requirements = []
        categories = self._get_relevant_categories(clause_type)
        
        for category in categories:
            if category in self.compliance_rules[framework]:
                requirements.extend(self.compliance_rules[framework][category])
        
        return requirements