import time
import logging
from typing import Dict, Any
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from src.config import MONGODB_URI, DATABASE_NAME

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MonitoringCallback:
    """Callback handler for ADK-B agent execution"""
    
    def __init__(self):
        self.enabled = True
        self.client = None
        self.db = None
        self.logs_collection = None
        self.metrics_collection = None

        try:
            self.client = MongoClient(
                MONGODB_URI,
                serverSelectionTimeoutMS=2000,
                connectTimeoutMS=2000
            )
            self.client.admin.command('ping')
            self.db = self.client[DATABASE_NAME]
            self.logs_collection = self.db['execution_logs_b']
            self.metrics_collection = self.db['performance_metrics_b']
            logger.info("ADK-B monitoring connected to MongoDB")
        except Exception as exc:
            self.enabled = False
            logger.warning(
                "ADK-B monitoring running without MongoDB (degraded mode): %s",
                exc
            )
        
    def on_agent_start(self, agent_name: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Called when an agent starts execution"""
        context = {
            'agent_name': agent_name,
            'start_time': time.time(),
            'timestamp': datetime.now(),
            'input_data': input_data,
            'execution_id': f"{agent_name}_{int(time.time() * 1000)}"
        }
        
        logger.info(f"[START] Agent: {agent_name} | Input keys: {list(input_data.keys())}")
        
        self._safe_insert(
            self.logs_collection,
            {
                'execution_id': context['execution_id'],
                'agent_name': agent_name,
                'event': 'start',
                'timestamp': context['timestamp'],
                'input_summary': {k: str(v)[:100] for k, v in input_data.items()}
            }
        )
        
        return context
    
    def on_agent_end(self, context: Dict[str, Any], output_data: Dict[str, Any], model_used: str = "unknown"):
        """Called when an agent completes execution"""
        end_time = time.time()
        execution_time_ms = (end_time - context['start_time']) * 1000
        
        logger.info(
            f"[END] Agent: {context['agent_name']} | "
            f"Time: {execution_time_ms:.2f}ms | "
            f"Model: {model_used}"
        )
        
        self._safe_insert(
            self.logs_collection,
            {
                'execution_id': context['execution_id'],
                'agent_name': context['agent_name'],
                'event': 'end',
                'timestamp': datetime.now(),
                'execution_time_ms': execution_time_ms,
                'model_used': model_used,
                'output_summary': {k: str(v)[:100] for k, v in output_data.items()}
            }
        )

        self._safe_insert(
            self.metrics_collection,
            {
                'agent_name': context['agent_name'],
                'execution_time_ms': execution_time_ms,
                'model_used': model_used,
                'timestamp': datetime.now(),
                'success': True
            }
        )
        
    def on_agent_error(self, context: Dict[str, Any], error: Exception):
        """Called when an agent encounters an error"""
        end_time = time.time()
        execution_time_ms = (end_time - context['start_time']) * 1000
        
        logger.error(
            f"[ERROR] Agent: {context['agent_name']} | "
            f"Time: {execution_time_ms:.2f}ms | "
            f"Error: {str(error)}"
        )
        
        self._safe_insert(
            self.logs_collection,
            {
                'execution_id': context['execution_id'],
                'agent_name': context['agent_name'],
                'event': 'error',
                'timestamp': datetime.now(),
                'execution_time_ms': execution_time_ms,
                'error_message': str(error),
                'error_type': type(error).__name__
            }
        )

        self._safe_insert(
            self.metrics_collection,
            {
                'agent_name': context['agent_name'],
                'execution_time_ms': execution_time_ms,
                'timestamp': datetime.now(),
                'success': False,
                'error': str(error)
            }
        )

    def log_intermediate_output(self, agent_name: str, step: str, data: Any):
        logger.info(f"[INTERMEDIATE] Agent: {agent_name} | Step: {step}")
        self._safe_insert(
            self.logs_collection,
            {
                'agent_name': agent_name,
                'event': 'intermediate',
                'step': step,
                'timestamp': datetime.now(),
                'data_summary': str(data)[:200]
            }
        )

    def _safe_insert(self, collection, payload):
        if not self.enabled or collection is None:
            return
        try:
            collection.insert_one(payload)
        except PyMongoError as exc:
            logger.warning("ADK-B monitoring insert skipped: %s", exc)
            self.enabled = False

# Global callback instance
monitor = MonitoringCallback()