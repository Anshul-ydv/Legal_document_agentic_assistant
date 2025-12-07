import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "Output"


def _ensure_output_dir() -> Path:
    output_dir = Path(os.getenv("ADK_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _json_default(value: Any):
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, set):
        return list(value)
    if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
        return value.model_dump()
    if hasattr(value, "dict") and callable(getattr(value, "dict")):
        return value.dict()
    return str(value)


def serialize_payload(payload: Any) -> Any:
    return json.loads(json.dumps(payload, default=_json_default))


def persist_json_output(prefix: str, document_id: str, payload: Dict[str, Any]) -> Path:
    output_dir = _ensure_output_dir()
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    safe_doc_id = document_id.replace(" ", "_")
    filename = f"{prefix}_{safe_doc_id}_{timestamp}.json"
    path = output_dir / filename
    serializable_payload = serialize_payload(payload)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(serializable_payload, handle, indent=2)
    return path


def persist_markdown_output(prefix: str, document_id: str, markdown: str) -> Path:
    output_dir = _ensure_output_dir()
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    safe_doc_id = document_id.replace(" ", "_")
    filename = f"{prefix}_{safe_doc_id}_{timestamp}.md"
    path = output_dir / filename
    with path.open("w", encoding="utf-8") as handle:
        handle.write(markdown)
    return path
