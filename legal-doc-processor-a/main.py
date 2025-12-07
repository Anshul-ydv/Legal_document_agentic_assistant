import sys
import argparse
from src.graph.workflow import run_adk_a
from src.utils.persistence import (
    persist_json_output,
    persist_markdown_output,
    serialize_payload,
)
from src.utils.reporting import build_adk_a_markdown_report
import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='ADK-A: Legal Document Processing')
    parser.add_argument('--document-id', required=True, help='Unique document identifier')
    parser.add_argument('--document-path', help='Path to document file')
    parser.add_argument('--document-text', help='Direct text input')
    parser.add_argument('--document-type', default='contract', help='Type of document')
    parser.add_argument('--output', help='Output file path for results (JSON)')
    
    args = parser.parse_args()
    
    if not args.document_path and not args.document_text:
        logger.error("Either --document-path or --document-text must be provided")
        sys.exit(1)
    
    logger.info(f"Starting ADK-A for document: {args.document_id}")
    
    # Run workflow
    result = run_adk_a(
        document_id=args.document_id,
        document_path=args.document_path,
        document_text=args.document_text,
        document_type=args.document_type
    )
    markdown_report = build_adk_a_markdown_report(result)
    result["markdown_report"] = markdown_report
    archive_path = persist_json_output("adk_a", args.document_id, result)
    logger.info("ADK-A result archived to %s", archive_path)
    markdown_path = persist_markdown_output("adk_a", args.document_id, markdown_report)
    logger.info("ADK-A markdown report archived to %s", markdown_path)
    
    # Print summary
    print("\n" + "="*80)
    print("ADK-A PROCESSING COMPLETE")
    print("="*80)
    print(f"Document ID: {result['document_id']}")
    print(f"Status: {result['status']}")
    print(f"Clauses Extracted: {result['clause_count']}")
    print(f"High Risk Clauses: {result['high_risk_count']}")
    print(f"Overall Risk Score: {result['overall_risk_score']:.2f}/10.0")
    print(f"Ready for Suggestions: {result.get('ready_for_suggestions', False)}")
    
    if result.get('errors'):
        print(f"\nErrors: {len(result['errors'])}")
        for error in result['errors']:
            print(f"  - {error}")
    
    print("="*80 + "\n")
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(serialize_payload(result), f, indent=2)
        logger.info(f"Results saved to: {args.output}")
    
    return 0 if result['status'] != 'error' else 1

if __name__ == '__main__':
    sys.exit(main())