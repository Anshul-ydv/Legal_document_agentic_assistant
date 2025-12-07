from flask import Flask, request, jsonify
from pymongo import MongoClient
from src.config import MCP_SERVER_A_PORT, MONGODB_URI, DATABASE_NAME
from src.graph.workflow import run_adk_a
from src.utils.persistence import (
    persist_json_output,
    persist_markdown_output,
    serialize_payload,
)
from src.utils.reporting import build_adk_a_markdown_report
import logging
import json
import certifi

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# MongoDB connection
def _build_mongo_client() -> MongoClient:
    mongo_kwargs = {}
    if MONGODB_URI.startswith("mongodb+srv://"):
        mongo_kwargs.update({
            "tls": True,
            "tlsCAFile": certifi.where(),
        })

    try:
        client = MongoClient(MONGODB_URI, **mongo_kwargs)
        client.admin.command('ping')
        return client
    except Exception as exc:
        if not mongo_kwargs:
            logger.error("MongoDB connection failed: %s", exc)
            raise
        logger.warning("Primary MongoDB TLS validation failed: %s", exc)
        mongo_kwargs["tlsAllowInvalidCertificates"] = True
        client = MongoClient(MONGODB_URI, **mongo_kwargs)
        client.admin.command('ping')
        logger.warning("Connected to MongoDB with relaxed TLS validation")
        return client

client = _build_mongo_client()
db = client[DATABASE_NAME]
documents_collection = db['documents']
communication_collection = db['adk_communication']

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'ADK-A'}), 200

@app.route('/process_document', methods=['POST'])
def process_document():
    """
    Process a legal document through ADK-A pipeline
    Expected JSON: {
        "document_id": "doc_123",
        "document_path": "/path/to/doc.pdf" (optional),
        "document_text": "text content" (optional),
        "document_type": "contract" (default)
    }
    """
    try:
        data = request.json
        document_id = data.get('document_id')
        document_path = data.get('document_path')
        document_text = data.get('document_text')
        document_type = data.get('document_type', 'contract')
        
        if not document_id:
            return jsonify({'error': 'document_id is required'}), 400
        
        if not document_path and not document_text:
            return jsonify({'error': 'Either document_path or document_text must be provided'}), 400
        
        logger.info(f"Processing document: {document_id}")
        
        # Run ADK-A workflow
        result = run_adk_a(
            document_id=document_id,
            document_path=document_path,
            document_text=document_text,
            document_type=document_type
        )
        markdown_report = build_adk_a_markdown_report(result)
        result["markdown_report"] = markdown_report
        persist_json_output("adk_a", document_id, result)
        persist_markdown_output("adk_a", document_id, markdown_report)
        
        # Store result in MongoDB
        documents_collection.update_one(
            {'document_id': document_id},
            {'$set': {
                'adk_a_result': serialize_payload(result),
                'status': result['status'],
                'processed_at': result['audit_log'][-1].timestamp if result.get('audit_log') else None
            }},
            upsert=True
        )
        
        # If ready for suggestions, notify ADK-B
        if result.get('ready_for_suggestions'):
            communication_collection.insert_one({
                'from': 'ADK-A',
                'to': 'ADK-B',
                'document_id': document_id,
                'message_type': 'request_suggestions',
                'data': {
                    'clause_count': result['clause_count'],
                    'high_risk_count': result['high_risk_count'],
                    'overall_risk_score': result['overall_risk_score']
                }
            })
        
        # Return serializable result
        response = {
            'document_id': result['document_id'],
            'status': result['status'],
            'clause_count': result['clause_count'],
            'high_risk_count': result['high_risk_count'],
            'overall_risk_score': result['overall_risk_score'],
            'ready_for_suggestions': result.get('ready_for_suggestions', False),
            'errors': result.get('errors', [])
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        logger.error(f"Error processing document: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_result/<document_id>', methods=['GET'])
def \
    get_result(document_id):
    """Retrieve processing result for a document"""
    try:
        result = documents_collection.find_one({'document_id': document_id})
        
        if not result:
            return jsonify({'error': 'Document not found'}), 404
        
        # Remove MongoDB _id field
        result.pop('_id', None)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error retrieving result: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/communicate', methods=['POST'])
def receive_communication():
    """Receive communication from ADK-B"""
    try:
        data = request.json
        
        logger.info(f"Received communication from {data.get('from')}")
        
        # Store communication
        communication_collection.insert_one(data)
        
        # Update document with ADK-B response
        if data.get('message_type') == 'suggestions_complete':
            documents_collection.update_one(
                {'document_id': data['document_id']},
                {'$set': {'adk_b_response': data.get('data')}}
            )
        
        return jsonify({'status': 'received'}), 200
        
    except Exception as e:
        logger.error(f"Error handling communication: {str(e)}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info(f"Starting ADK-A MCP Server on port {MCP_SERVER_A_PORT}")
    app.run(host='0.0.0.0', port=MCP_SERVER_A_PORT, debug=False)