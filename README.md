
# Legal AI Multi-Agent Document Processing System

## Overview

A sophisticated legal document analysis system built with **LangGraph**, **Google Gemini AI**, and **MCP (Model Context Protocol)** that provides comprehensive risk assessment and compliance advisory services.

### Architecture

The system consists of two connected Agentic Development Kits (ADKs):

- **ADK-A (Legal Document Processor)**: Ingests, parses, and analyzes legal documents
- **ADK-B (Compliance Advisor)**: Generates compliance suggestions and synthesizes reports

## Features

### ADK-A: Legal Document Processor
-  **Document Ingestion**: Supports PDF, DOCX, and TXT formats
-  **Clause Extraction**: AI-powered identification and classification of legal clauses
-  **Risk Detection**: Intelligent risk assessment with RAG-enhanced analysis
-  **Dynamic Model Routing**: Automatic selection between Gemini Flash and Pro models

### ADK-B: Compliance Advisor
-  **Compliance Suggestions**: AI-generated recommendations for risky clauses
-  **Template Library**: Pre-vetted compliant clause templates
-  **Audit Trail**: Complete tracking of all analysis steps
-  **Report Synthesis**: Professional markdown reports with executive summaries

## Project Structure

```
genaiprj/
├── legal-doc-processor-a/          # ADK-A
│   ├── main.py                     # CLI interface
│   ├── mcp_server_a.py            # MCP server
│   └── src/
│       ├── agents/                 # Agent implementations
│       │   ├── document_ingestion_agent.py
│       │   ├── clause_extraction_agent.py
│       │   └── risk_detection_agent.py
│       ├── tools/                  # Tools
│       │   ├── pdf_parser.py
│       │   └── rag_retriever.py
│       ├── graph/                  # LangGraph workflows
│       ├── state/                  # State definitions
│       └── monitoring/             # Callbacks
│
├── legal-compliance-advisor-b/     # ADK-B
│   ├── main.py                     # CLI interface
│   ├── mcp_server_b.py            # MCP server
│   └── src/
│       ├── agents/                 # Agent implementations
│       │   ├── suggestion_generator_agent.py
│       │   ├── audit_trail_agent.py
│       │   └── report_synthesizer_agent.py
│       ├── tools/                  # Tools
│       │   ├── compliance_checker.py
│       │   └── template_library.py
│       └── ...
│
├── connect_adks.py                 # Integration script
├── requirements.txt                # Dependencies
└── .env.example                    # Environment template
```

## Prerequisites

- Python 3.9+
- MongoDB (local or cloud instance)
- Google Gemini API key

## Installation

### 1. Clone and Setup

```bash
cd genaiprj
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
# Copy example environment file
cp .env.example legal-doc-processor-a/.env
cp .env.example legal-compliance-advisor-b/.env

# Edit .env files with your configuration
```

**Required Environment Variables:**
```bash
GEMINI_API_KEY=your_gemini_api_key_here
MONGODB_URI=mongodb://localhost:27017/
DATABASE_NAME=legal_ai_db
MCP_SERVER_A_PORT=8001
MCP_SERVER_B_PORT=8002
```

### 5. Start MongoDB

```bash
# Using Homebrew on macOS
brew services start mongodb-community

# Or using Docker
docker run -d -p 27017:27017 --name mongodb mongo:latest
```

## Usage

### Method 1: Integrated Pipeline (Recommended)

This method runs both ADKs and handles all communication automatically.

```bash
python connect_adks.py \
    --document-id "contract_001" \
    --document-path "path/to/contract.pdf" \
    --output-report "compliance_report.md"
```

**Example with text input:**
```bash
python connect_adks.py \
    --document-id "contract_002" \
    --document-text "This Agreement is made between Party A and Party B..." \
    --output-report "report.md" \
    --output-json "results.json"
```

### Method 2: MCP Server Mode

Start both servers in separate terminals:

**Terminal 1 - Start ADK-A:**
```bash
cd legal-doc-processor-a
python mcp_server_a.py
```

**Terminal 2 - Start ADK-B:**
```bash
cd legal-compliance-advisor-b
python mcp_server_b.py
```

**Use REST API:**
```bash
# Process document through ADK-A
curl -X POST http://localhost:8001/process_document \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "doc_123",
    "document_path": "/path/to/document.pdf"
  }'

# Generate compliance suggestions through ADK-B
curl -X POST http://localhost:8002/generate_suggestions \
  -H "Content-Type: application/json" \
  -d '{
    "document_id": "doc_123",
    "adk_a_data": {...}
  }'
```

### Method 3: Command-Line Interface

**Process with ADK-A only:**
```bash
cd legal-doc-processor-a
python main.py \
    --document-id "doc_001" \
    --document-path "contract.pdf" \
    --output "adk_a_results.json"
```

**Process with ADK-B:**
```bash
cd legal-compliance-advisor-b
python main.py \
    --document-id "doc_001" \
    --adk-a-result "adk_a_results.json" \
    --output "compliance_report.md"
```

## API Endpoints

### ADK-A (Port 8001)

- `GET /health` - Health check
- `POST /process_document` - Process a legal document
- `GET /get_result/<document_id>` - Retrieve processing results
- `POST /communicate` - Receive communication from ADK-B

### ADK-B (Port 8002)

- `GET /health` - Health check
- `POST /generate_suggestions` - Generate compliance suggestions
- `GET /get_report/<document_id>` - Get full report (JSON)
- `GET /get_markdown_report/<document_id>` - Get markdown report
- `GET /poll_for_work` - Poll for new work from ADK-A

## Example Workflow

1. **Upload Document**: Submit a legal contract for analysis
2. **ADK-A Processing**:
   - Parses document and extracts text
   - Identifies and classifies legal clauses
   - Assesses risk levels using RAG-enhanced analysis
3. **ADK-B Processing**:
   - Reviews high-risk clauses
   - Generates compliant alternatives using templates
   - Creates comprehensive audit trail
   - Synthesizes final markdown report
4. **Output**: Receive detailed compliance report with recommendations

## Configuration

### Model Selection

The system automatically routes between Gemini models:
- **Gemini 1.5 Flash**: Fast processing for standard documents
- **Gemini 1.5 Pro**: Complex analysis for high-complexity documents

Routing is based on document complexity (legal term density, length, sentence structure).

### Compliance Frameworks

Supported frameworks:
- GDPR (General Data Protection Regulation)
- CCPA (California Consumer Privacy Act)
- SOC 2
- ISO 27001
- HIPAA

## Monitoring and Logging

All agent executions are tracked with:
- Execution timestamps
- Input/output data
- Model usage
- Execution time
- Error tracking

Logs are stored in MongoDB collections:
- `execution_logs` - Detailed execution logs
- `performance_metrics` - Performance metrics
- `audit_trail` - Complete audit trail

## Sample Output

```markdown
# Legal Document Analysis Report

**Document ID:** contract_001
**Generated:** 2025-11-17 10:30:45
**Compliance Status:** NEEDS_REVIEW

## Executive Summary

This legal document contains 12 clauses, of which 3 were identified as high-risk...

## Analysis Overview

| Metric | Count |
|--------|-------|
| Total Clauses Analyzed | 12 |
| High-Risk Clauses | 3 |
| Compliance Suggestions | 8 |
| Overall Risk Score | 6.50/10.0 |

## Recommended Actions

1. Review and address all high-risk clauses immediately
2. Ensure GDPR compliance for data processing clauses
3. Consider implementing suggested compliance improvements
...
```

## Troubleshooting

### MongoDB Connection Issues
```bash
# Check MongoDB status
brew services list  # macOS
sudo systemctl status mongodb  # Linux

# Test connection
mongosh
```

### API Key Issues
- Verify GEMINI_API_KEY in `.env` files
- Check API quota at https://aistudio.google.com/

### Port Conflicts
- Change ports in `.env` files if 8001/8002 are in use
- Update MCP_SERVER_A_URL in ADK-B config accordingly

## Development

### Running Tests
```bash
# Install dev dependencies
pip install pytest pytest-cov

# Run tests
pytest tests/
```

### Code Style
```bash
pip install black flake8
black .
flake8 .
```

## Architecture Decisions

- **LangGraph**: Orchestrates multi-agent workflows with state management
- **Pydantic**: Ensures type safety for structured outputs
- **MongoDB**: Stores documents, results, and audit trails
- **Flask**: Provides REST API for MCP communication
- **Google Gemini**: Powers AI analysis with cost-optimized routing

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make changes with tests
4. Submit a pull request

## License

This project is provided for educational and demonstration purposes.

## Support

For issues or questions:
- Check MongoDB logs: `tail -f /usr/local/var/log/mongodb/mongo.log`
- Check application logs in console output
- Review audit trail in MongoDB

## Acknowledgments

- Google Gemini AI for language models
- LangGraph for agent orchestration
- Hugging Face for legal datasets

---

**Note**: This system provides AI-assisted legal analysis for informational purposes only. Always consult qualified legal professionals for final review and advice.

