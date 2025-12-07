import sys
import argparse
import json
from src.graph.workflow import run_adk_b
from src.utils.persistence import persist_json_output, persist_markdown_output
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description='ADK-B: Compliance Advisory')
    parser.add_argument('--document-id', required=True, help='Document identifier')
    parser.add_argument('--adk-a-result', required=True, help='Path to ADK-A result JSON file')
    parser.add_argument('--output', help='Output file path for report (Markdown)')
    
    args = parser.parse_args()
    
    # Load ADK-A result
    try:
        with open(args.adk_a_result, 'r') as f:
            adk_a_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load ADK-A result: {e}")
        sys.exit(1)
    
    logger.info(f"Starting ADK-B for document: {args.document_id}")
    
    # Run workflow
    result = run_adk_b(
        document_id=args.document_id,
        adk_a_data=adk_a_data
    )
    persist_json_output("adk_b", args.document_id, result)
    if result.get('markdown_report'):
        persist_markdown_output("adk_b", args.document_id, result['markdown_report'])
    
    # Print summary
    print("\n" + "="*80)
    print("ADK-B PROCESSING COMPLETE")
    print("="*80)
    print(f"Document ID: {result['document_id']}")
    print(f"Status: {result['status']}")
    print(f"Compliance Suggestions: {result['suggestion_count']}")
    
    if result.get('final_report'):
        final_report = result['final_report']
        print(f"Compliance Status: {getattr(final_report, 'compliance_status', 'unknown').upper()}")
        print(f"High-Risk Clauses: {getattr(final_report, 'high_risk_clauses', 0)}")
        print(f"\nExecutive Summary:")
        print(getattr(final_report, 'executive_summary', 'N/A'))
        print(f"\nRecommended Actions:")
        recommended_actions = getattr(final_report, 'recommended_actions', [])
        for i, action in enumerate(recommended_actions, 1):
            print(f"  {i}. {action}")
    
    if result.get('errors'):
        print(f"\nErrors: {len(result['errors'])}")
        for error in result['errors']:
            print(f"  - {error}")
    
    print("="*80 + "\n")
    
    # Save markdown report if requested
    if args.output and result.get('markdown_report'):
        with open(args.output, 'w') as f:
            f.write(result['markdown_report'])
        logger.info(f"Markdown report saved to: {args.output}")
    
    # Print report preview
    if result.get('markdown_report'):
        print("\n--- REPORT PREVIEW ---\n")
        print(result['markdown_report'][:1000])
        print("\n... (truncated) ...\n")
    
    return 0 if result['status'] != 'error' else 1

if __name__ == '__main__':
    sys.exit(main())