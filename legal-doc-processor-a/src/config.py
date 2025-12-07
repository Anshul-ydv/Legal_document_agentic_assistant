import os
import logging
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

# API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if GEMINI_API_KEY:
	# Keep both env vars in sync so ADK + direct SDK clients share the same key
	os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY
	existing_google_key = os.getenv("GOOGLE_API_KEY")
	if existing_google_key != GEMINI_API_KEY:
		logging.info("Synchronizing GOOGLE_API_KEY with GEMINI_API_KEY to avoid stale credentials")
		os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY
	genai.configure(api_key=GEMINI_API_KEY)
else:
	logging.warning("GEMINI_API_KEY is not set; LLM features will use fallbacks")

# MongoDB Configuration
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DATABASE_NAME = os.getenv("DATABASE_NAME", "legal_ai_db")

# MCP Configuration
MCP_SERVER_A_PORT = int(os.getenv("MCP_SERVER_A_PORT", "8001"))
MCP_SERVER_B_PORT = int(os.getenv("MCP_SERVER_B_PORT", "8002"))
MCP_SERVER_B_URL = os.getenv("MCP_SERVER_B_URL", f"http://localhost:{MCP_SERVER_B_PORT}")
ENABLE_A2A_DISPATCH = os.getenv("ENABLE_A2A_DISPATCH", "true").lower() == "true"

# Model Configuration
GEMINI_MODEL_STANDARD = "gemini-2.0-flash-lite"  # Unified model per latest requirement
GEMINI_MODEL_COMPLEX = "gemini-2.0-flash-lite"   # Use same flash tier for complex analysis

# Cost thresholds for routing
COMPLEXITY_THRESHOLD = 0.7  # If complexity > 0.7, use Pro model

# LLM Rate-Limit Controls (helps avoid 429 RESOURCE_EXHAUSTED)
LLM_RPM_LIMIT = max(int(os.getenv("LLM_RPM_LIMIT", "8")), 1)
LLM_MIN_CALL_INTERVAL = float(
    os.getenv("LLM_MIN_CALL_INTERVAL", str(max(60.0 / LLM_RPM_LIMIT, 8.0)))
)
LLM_MAX_RETRY_ATTEMPTS = int(os.getenv("LLM_MAX_RETRY_ATTEMPTS", "5"))
LLM_TPM_LIMIT = int(os.getenv("LLM_TPM_LIMIT", "1000000"))
LLM_RPD_LIMIT = int(os.getenv("LLM_RPD_LIMIT", "200"))
FORCE_SEQUENTIAL_EXECUTION = os.getenv("FORCE_SEQUENTIAL_EXECUTION", "true").lower() == "true"# RAG Configuration
DATASET_NAME = "d0r1h/ILC"
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200