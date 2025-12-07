from flask import Flask, request, jsonify
from pymongo import MongoClient
from src.config import MCP_SERVER_B_PORT, MCP_SERVER_A_URL, MONGODB_URI, DATABASE_NAME
from src.graph.workflow import run_adk_b
from src.utils.persistence import (
    persist_json_output,
    persist_markdown_output,
    serialize_payload,
)
import requests
import logging
import json
import certifi

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


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
reports_collection = db['compliance_reports']
communication_collection = db['adk_communication']

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'service': 'ADK-B'}), 200

@app.route('/generate_suggestions', methods=['POST'])
def generate_suggestions():
    """
    Generate compliance suggestions based on ADK-A results
    Expected JSON: {
        "document_id": "doc_123",
        "adk_a_data": { ... }  # Result from ADK-A
    }
    """
    try:
        data = request.json
        document_id = data.get('document_id')
        adk_a_data = data.get('adk_a_data')
        
        if not document_id or not adk_a_data:
            return jsonify({'error': 'document_id and adk_a_data are required'}), 400
        
        logger.info(f"Processing compliance suggestions for document: {document_id}")
        
        # Run ADK-B workflow
        result = run_adk_b(
            document_id=document_id,
            adk_a_data=adk_a_data
        )
        persist_json_output("adk_b", document_id, result)
        if result.get('markdown_report'):
            persist_markdown_output("adk_b", document_id, result['markdown_report'])
        
        # Store report in MongoDB
        if result.get('final_report'):
            final_report = result['final_report']
            compliance_status = getattr(final_report, 'compliance_status', 'unknown')
            generated_at = getattr(final_report, 'generated_at', None)
            
            reports_collection.update_one(
                {'document_id': document_id},
                {'$set': {
                    'document_id': document_id,
                    'final_report': serialize_payload(final_report),
                    'markdown_report': result.get('markdown_report', ''),
                    'compliance_status': compliance_status,
                    'suggestions_count': result.get('suggestion_count', 0),
                    'generated_at': generated_at
                }},
                upsert=True
            )
        
        # Send results back to ADK-A
        if result.get('ready_to_send'):
            try:
                final_report = result.get('final_report')
                compliance_status = getattr(final_report, 'compliance_status', 'unknown') if final_report else 'unknown'
                
                response = requests.post(
                    f"{MCP_SERVER_A_URL}/communicate",
                    json={
                        'from': 'ADK-B',
                        'to': 'ADK-A',
                        'document_id': document_id,
                        'message_type': 'suggestions_complete',
                        'data': {
                            'suggestion_count': result.get('suggestion_count', 0),
                            'compliance_status': compliance_status,
                            'report_available': True
                        }
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    result['sent_to_adk_a'] = True
                    logger.info(f"Successfully sent results to ADK-A for document: {document_id}")
                else:
                    logger.warning(f"Failed to send to ADK-A: {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Error communicating with ADK-A: {e}")
        
        # Return serializable response
        final_report = result.get('final_report')
        compliance_status = getattr(final_report, 'compliance_status', 'unknown') if final_report else 'unknown'
        
        response_data = {
            'document_id': document_id,
            'status': result.get('status', 'unknown'),
            'suggestion_count': result.get('suggestion_count', 0),
            'compliance_status': compliance_status,
            'report_length': len(result.get('markdown_report', '')),
            'sent_to_adk_a': result.get('sent_to_adk_a', False),
            'errors': result.get('errors', [])
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"Error generating suggestions: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_report/<document_id>', methods=['GET'])
def get_report(document_id):
    """Retrieve compliance report for a document"""
    try:
        report = reports_collection.find_one({'document_id': document_id})
        
        if not report:
            return jsonify({'error': 'Report not found'}), 404
        
        # Remove MongoDB _id field
        report.pop('_id', None)
        
        return jsonify(report), 200
        
    except Exception as e:
        logger.error(f"Error retrieving report: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/get_markdown_report/<document_id>', methods=['GET'])
def get_markdown_report(document_id):
    """Retrieve Markdown report"""
    try:
        report = reports_collection.find_one({'document_id': document_id})
        
        if not report:
            return jsonify({'error': 'Report not found'}), 404
        
        markdown = report.get('markdown_report', '')
        
        return markdown, 200, {'Content-Type': 'text/markdown'}
        
    except Exception as e:
        logger.error(f"Error retrieving markdown report: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/poll_for_work', methods=['GET'])
def poll_for_work():
    """Poll for new work from ADK-A"""
    try:
        # Check for pending requests from ADK-A
        pending = communication_collection.find_one({
            'from': 'ADK-A',
            'to': 'ADK-B',
            'message_type': 'request_suggestions',
            'processed': {'$ne': True}
        })
        
        if pending:
            document_id = pending['document_id']
            
            # Get full data from ADK-A
            adk_a_result = documents_collection.find_one({'document_id': document_id})
            
            if adk_a_result and adk_a_result.get('adk_a_result'):
                # Mark as processed
                communication_collection.update_one(
                    {'_id': pending['_id']},
                    {'$set': {'processed': True}}
                )
                
                # Process automatically
                logger.info(f"Auto-processing document from poll: {document_id}")
                
                generate_suggestions_data = {
                    'document_id': document_id,
                    'adk_a_data': adk_a_result['adk_a_result']
                }
                
                # Simulate POST request
                with app.test_request_context(
                    '/generate_suggestions',
                    method='POST',
                    json=generate_suggestions_data
                ):
                    response = generate_suggestions()
                    return response
        
        return jsonify({'status': 'no_work'}), 200
        
    except Exception as e:
        logger.error(f"Error polling for work: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info(f"Starting ADK-B MCP Server on port {MCP_SERVER_B_PORT}")
    app.run(host='0.0.0.0', port=MCP_SERVER_B_PORT, debug=False)