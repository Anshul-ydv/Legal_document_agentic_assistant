import time
import logging
import json
import os
from pathlib import Path
from typing import Dict, Any
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from src.config import MONGODB_URI, DATABASE_NAME
from src.utils.persistence import serialize_payload
import certifi

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MonitoringCallback:
    """Callback handler for tracking agent execution"""
    
    def __init__(self):
        self.enabled = True
        self.client = None
        self.db = None
        self.logs_collection = None
        self.metrics_collection = None
        self.audit_dir = Path(os.getenv("ADK_AUDIT_LOG_DIR", "audits"))
        self.audit_dir.mkdir(parents=True, exist_ok=True)

        ca_file = certifi.where()
        if self._initialize_client(ca_file, allow_insecure=False):
            return

        logger.warning(
            "MongoDB TLS validation failed repeatedly; retrying with relaxed certificate checks"
        )

        if not self._initialize_client(ca_file, allow_insecure=True):
            self.enabled = False
            logger.warning(
                "MonitoringCallback running in degraded mode (MongoDB unavailable)"
            )

    def _initialize_client(self, ca_file: str, allow_insecure: bool) -> bool:
        """Try to connect to MongoDB with optional relaxed TLS requirements."""
        for attempt in range(3):
            try:
                # Atlas clusters can take a couple of seconds to finish TLS handshakes,
                # so keep the timeouts lenient enough to avoid false negatives.
                self.client = MongoClient(
                    MONGODB_URI,
                    serverSelectionTimeoutMS=12000,
                    connectTimeoutMS=10000,
                    tls=True,
                    tlsCAFile=ca_file,
                    tlsAllowInvalidCertificates=allow_insecure
                )
                # Force a lightweight connection check
                self.client.admin.command('ping')
                self.db = self.client[DATABASE_NAME]
                self.logs_collection = self.db['execution_logs']
                self.metrics_collection = self.db['performance_metrics']
                logger.info(
                    "MonitoringCallback connected to MongoDB%s",
                    " (TLS validation relaxed)" if allow_insecure else ""
                )
                return True
            except Exception as exc:
                logger.warning(
                    "MongoDB connection attempt %s%s failed: %s",
                    attempt + 1,
                    " (relaxed TLS)" if allow_insecure else "",
                    exc
                )
                time.sleep(1)
        return False
        
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
            f"Model: {model_used} | "
            f"Output keys: {list(output_data.keys())}"
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
        """Log intermediate processing steps"""
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
        """Insert into MongoDB if available, otherwise no-op."""
        if not self.enabled or collection is None:
            self._write_local_log(payload)
            return
        try:
            collection.insert_one(payload)
            self._write_local_log(payload)
        except PyMongoError as exc:
            logger.warning("MongoDB insert skipped due to error: %s", exc)
            self.enabled = False
            self._write_local_log(payload)

    def _write_local_log(self, payload: Dict[str, Any]):
        """Persist event payloads to per-event JSON files for offline auditing."""
        try:
            timestamp = datetime.now()
            sanitized_agent = str(payload.get('agent_name', 'agent')).replace(' ', '_').lower()
            filename = f"{timestamp.strftime('%Y%m%dT%H%M%S_%f')}_{sanitized_agent}.json"
            path = self.audit_dir / filename
            log_entry = serialize_payload({
                **payload,
                'logged_at': timestamp.isoformat()
            })
            with path.open('w', encoding='utf-8') as log_file:
                json.dump(log_entry, log_file, indent=2)
        except Exception as exc:
            logger.debug("Local audit log write skipped: %s", exc)

# Global callback instance
monitor = MonitoringCallback()