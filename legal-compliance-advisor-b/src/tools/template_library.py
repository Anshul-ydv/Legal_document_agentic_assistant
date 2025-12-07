from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

class TemplateLibrary:
    """MCP Tool 4: Library of compliant clause templates"""
    
    def __init__(self):
        self.templates = {
            'indemnification': {
                'balanced': """
Mutual Indemnification: Each party shall indemnify, defend, and hold harmless the other party 
from and against any and all claims, damages, losses, and expenses (including reasonable 
attorneys' fees) arising out of or relating to: (a) any breach of this Agreement by the 
indemnifying party; (b) any negligence or willful misconduct by the indemnifying party; or 
(c) any violation of applicable laws by the indemnifying party. This indemnification shall 
not apply to claims arising from the indemnified party's own negligence or misconduct.
                """,
                'capped': """
Limited Indemnification: Subject to the limitations set forth in this Agreement, Party A 
shall indemnify Party B from third-party claims arising from Party A's gross negligence 
or willful misconduct. The maximum aggregate liability for indemnification shall not exceed 
the total amounts paid under this Agreement in the twelve (12) months preceding the claim.
                """
            },
            'liability': {
                'standard': """
Limitation of Liability: EXCEPT FOR BREACHES OF CONFIDENTIALITY, INFRINGEMENT OF INTELLECTUAL 
PROPERTY RIGHTS, OR EITHER PARTY'S GROSS NEGLIGENCE OR WILLFUL MISCONDUCT, IN NO EVENT SHALL 
EITHER PARTY BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE 
DAMAGES. EACH PARTY'S TOTAL LIABILITY UNDER THIS AGREEMENT SHALL NOT EXCEED THE AMOUNTS PAID 
OR PAYABLE UNDER THIS AGREEMENT IN THE TWELVE (12) MONTHS PRECEDING THE EVENT GIVING RISE 
TO LIABILITY.
                """,
                'mutual': """
Mutual Limitation: Subject to exceptions for willful misconduct, gross negligence, and breach 
of confidentiality obligations, neither party shall be liable for indirect or consequential 
damages. Each party's total cumulative liability shall be limited to the greater of (a) the 
fees paid in the preceding twelve months or (b) $100,000.
                """
            },
            'termination': {
                'standard': """
Termination: Either party may terminate this Agreement: (a) for convenience upon sixty (60) 
days' prior written notice; (b) immediately upon written notice if the other party materially 
breaches this Agreement and fails to cure such breach within thirty (30) days of receiving 
written notice; or (c) immediately if the other party becomes insolvent or files for bankruptcy. 
Upon termination, all rights and licenses granted shall immediately cease, except for those 
provisions that by their nature should survive termination.
                """,
                'with_cure': """
Termination for Cause: Either party may terminate this Agreement for cause if the other party 
materially breaches any provision and fails to cure within thirty (30) calendar days after 
receiving written notice specifying the breach. The non-breaching party may also terminate 
immediately without cure period for: (i) breach of confidentiality obligations; (ii) 
infringement of intellectual property; or (iii) violation of applicable laws.
                """
            },
            'confidentiality': {
                'standard': """
Confidentiality: Each party agrees to maintain in strict confidence all Confidential Information 
received from the other party and to use such information solely for purposes of this Agreement. 
Confidential Information excludes information that: (a) is publicly available through no fault 
of the receiving party; (b) was rightfully known prior to disclosure; (c) is independently 
developed; or (d) is rightfully obtained from a third party. The obligations herein shall 
survive for three (3) years following termination or expiration of this Agreement.
                """,
                'with_gdpr': """
Confidentiality and Data Protection: Recipient agrees to: (a) maintain confidentiality of all 
proprietary information; (b) process personal data only as instructed and in compliance with 
GDPR; (c) implement appropriate technical and organizational measures; (d) notify discloser 
of any data breaches within 72 hours; (e) assist with data subject rights requests; and 
(f) return or delete all confidential information upon termination. These obligations survive 
for five (5) years or as required by applicable data protection laws.
                """
            },
            'data_processing': {
                'gdpr_compliant': """
Data Processing: Processor shall process Personal Data only on documented instructions from 
Controller, including with regard to transfers outside the EEA. Processor shall: (a) ensure 
personnel are subject to confidentiality obligations; (b) implement appropriate technical and 
organizational security measures; (c) engage sub-processors only with prior written consent; 
(d) assist Controller in responding to data subject requests; (e) assist Controller with 
security breach notifications and impact assessments; (f) delete or return Personal Data upon 
termination; and (g) make available all information necessary to demonstrate compliance with 
GDPR Article 28.
                """
            },
            'jurisdiction': {
                'neutral': """
Governing Law and Jurisdiction: This Agreement shall be governed by and construed in accordance 
with the laws of [Jurisdiction], without regard to its conflict of laws principles. Any disputes 
arising from or relating to this Agreement shall be resolved through binding arbitration under 
the rules of [Arbitration Association], with the arbitration to be conducted in [Location]. 
Each party shall bear its own costs, and the prevailing party shall be entitled to reasonable 
attorneys' fees.
                """
            }
        }
    
    def get_template(self, clause_type: str, variant: str = 'standard') -> str:
        """Retrieve a compliant template for a clause type"""
        clause_type_lower = clause_type.lower()
        
        if clause_type_lower not in self.templates:
            logger.warning(f"No template found for clause type: {clause_type}")
            return ""
        
        templates = self.templates[clause_type_lower]

        requested_variant = variant
        if requested_variant not in templates:
            # Return first available variant
            variant = list(templates.keys())[0]
            logger.info(
                "Variant '%s' not found for %s clauses, using '%s'",
                requested_variant,
                clause_type,
                variant
            )
        else:
            variant = requested_variant
        
        template = templates[variant].strip()
        logger.info(f"Retrieved {clause_type} template (variant: {variant})")
        
        return template
    
    def get_available_variants(self, clause_type: str) -> List[str]:
        """Get all available variants for a clause type"""
        clause_type_lower = clause_type.lower()
        
        if clause_type_lower not in self.templates:
            return []
        
        return list(self.templates[clause_type_lower].keys())
    
    def search_templates(self, keyword: str) -> Dict[str, List[str]]:
        """Search for templates containing a keyword"""
        results = {}
        
        keyword_lower = keyword.lower()
        
        for clause_type, variants in self.templates.items():
            matching_variants = []
            for variant, template in variants.items():
                if keyword_lower in template.lower():
                    matching_variants.append(variant)
            
            if matching_variants:
                results[clause_type] = matching_variants
        
        return results