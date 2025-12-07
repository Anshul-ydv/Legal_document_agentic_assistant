import os
import logging
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

# API Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logging.warning("GEMINI_API_KEY is not set; ADK-B will use template fallbacks")

# MongoDB Configuration
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
DATABASE_NAME = os.getenv("DATABASE_NAME", "legal_ai_db")

# MCP Configuration
MCP_SERVER_A_PORT = int(os.getenv("MCP_SERVER_A_PORT", "8001"))
MCP_SERVER_B_PORT = int(os.getenv("MCP_SERVER_B_PORT", "8002"))
MCP_SERVER_A_URL = f"http://localhost:{MCP_SERVER_A_PORT}"

# Model Configuration
GEMINI_MODEL_STANDARD = "gemini-2.0-flash-lite"
GEMINI_MODEL_COMPLEX = "gemini-2.0-flash-lite"

# Compliance databases/frameworks
COMPLIANCE_FRAMEWORKS = [
    "GDPR",
    "CCPA",
    "SOC2",
    "ISO27001",
    "HIPAA"
]

# LLM Rate-Limit Controls (synchronized with ADK-A)
LLM_RPM_LIMIT = max(int(os.getenv("LLM_RPM_LIMIT", "4")), 1)
LLM_MIN_CALL_INTERVAL = float(
    os.getenv("LLM_MIN_CALL_INTERVAL", str(max(60.0 / LLM_RPM_LIMIT, 15.0)))
)
LLM_MAX_RETRY_ATTEMPTS = int(os.getenv("LLM_MAX_RETRY_ATTEMPTS", "5"))
LLM_TPM_LIMIT = int(os.getenv("LLM_TPM_LIMIT", "1000000"))
LLM_RPD_LIMIT = int(os.getenv("LLM_RPD_LIMIT", "200"))
FORCE_SEQUENTIAL_EXECUTION = os.getenv("FORCE_SEQUENTIAL_EXECUTION", "true").lower() == "true"