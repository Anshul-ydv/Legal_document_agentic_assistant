try:
    from datasets import load_dataset
except ImportError:  # pragma: no cover - optional dependency
    load_dataset = None
from typing import List, Dict
import hashlib
import google.generativeai as genai
from src.config import DATASET_NAME, CHUNK_SIZE, GEMINI_MODEL_STANDARD
import logging
import numpy as np

logger = logging.getLogger(__name__)

class RAGRetriever:
    """MCP Tool 2: Retrieve relevant legal precedents from ILC dataset"""
    
    def __init__(self):
        self.dataset = None
        self.embeddings_cache = {}
        self.model = genai.GenerativeModel(GEMINI_MODEL_STANDARD)
        
    def load_dataset(self):
        """Load the ILC legal dataset"""
        if self.dataset is None:
            try:
                if load_dataset is None:
                    raise ImportError("datasets package not installed")
                logger.info(f"Loading dataset: {DATASET_NAME}")
                self.dataset = load_dataset(DATASET_NAME, split='train')
                logger.info(f"Dataset loaded: {len(self.dataset)} documents")
            except Exception as e:
                logger.error(f"Error loading dataset: {str(e)}")
                # Fallback to mock data for demonstration
                self.dataset = self._create_mock_dataset()
    
    def _create_mock_dataset(self):
        """Create mock legal data if dataset unavailable"""
        mock_data = [
            {
                'text': 'Indemnification Clause: Party A shall indemnify and hold harmless Party B from any claims arising from...',
                'category': 'indemnification',
                'risk_level': 'medium'
            },
            {
                'text': 'Limitation of Liability: In no event shall either party be liable for indirect, incidental, or consequential damages...',
                'category': 'liability',
                'risk_level': 'high'
            },
            {
                'text': 'Governing Law: This agreement shall be governed by and construed in accordance with the laws of...',
                'category': 'jurisdiction',
                'risk_level': 'low'
            },
            {
                'text': 'Termination: Either party may terminate this agreement with 30 days written notice...',
                'category': 'termination',
                'risk_level': 'medium'
            },
            {
                'text': 'Confidentiality: Recipient agrees to maintain confidential information in strict confidence...',
                'category': 'confidentiality',
                'risk_level': 'high'
            }
        ]
        return mock_data
    
    def get_embedding(self, text: str) -> List[float]:
        """Get deterministic pseudo-embeddings for lightweight similarity scoring."""
        tokens = text.lower().split()
        embed: List[float] = []
        for token in tokens[:50]:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            # Use first 4 bytes for a stable integer, then normalize to [0, 1)
            int_val = int.from_bytes(digest[:4], byteorder="big", signed=False)
            embed.append((int_val % 1000) / 1000.0)
        return embed
    
    def retrieve_similar_clauses(self, query_text: str, top_k: int = 3) -> List[Dict]:
        """Retrieve similar legal clauses from knowledge base"""
        self.load_dataset()
        
        logger.info(f"Retrieving similar clauses for query: {query_text[:100]}...")
        
        # Simple keyword-based retrieval for demonstration
        query_terms = set(query_text.lower().split())
        
        results = []
        for doc in self.dataset:
            doc_text = doc.get('text', '')
            doc_terms = set(doc_text.lower().split())
            
            # Calculate similarity (Jaccard similarity)
            intersection = len(query_terms.intersection(doc_terms))
            union = len(query_terms.union(doc_terms))
            similarity = intersection / union if union > 0 else 0
            
            results.append({
                'text': doc_text,
                'category': doc.get('category', 'general'),
                'risk_level': doc.get('risk_level', 'unknown'),
                'similarity': similarity
            })
        
        # Sort by similarity and return top_k
        results.sort(key=lambda x: x['similarity'], reverse=True)
        top_results = results[:top_k]
        
        logger.info(f"Retrieved {len(top_results)} similar clauses")
        return top_results
    
    def get_risk_context(self, clause_type: str) -> Dict:
        """Get risk assessment context for specific clause types"""
        risk_knowledge = {
            'indemnification': {
                'common_risks': ['Unlimited liability', 'Broad scope', 'No cap on damages'],
                'best_practices': ['Include liability caps', 'Define scope clearly', 'Mutual indemnification']
            },
            'liability': {
                'common_risks': ['No limitation', 'Excludes consequential damages unfairly', 'Asymmetric terms'],
                'best_practices': ['Cap at contract value', 'Allow for gross negligence exceptions', 'Balanced allocation']
            },
            'termination': {
                'common_risks': ['Short notice period', 'No cure period', 'Harsh post-termination obligations'],
                'best_practices': ['30-60 day notice', 'Allow cure period', 'Clear transition terms']
            },
            'confidentiality': {
                'common_risks': ['Overly broad definition', 'No exclusions', 'Unlimited duration'],
                'best_practices': ['Define confidential info clearly', 'Standard exclusions', '3-5 year duration']
            }
        }
        
        return risk_knowledge.get(clause_type.lower(), {
            'common_risks': ['Non-standard terms', 'Unclear obligations'],
            'best_practices': ['Follow industry standards', 'Seek legal review']
        })