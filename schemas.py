"""Pydantic schemas for API request/response validation."""

from typing import Any, Optional
from pydantic import BaseModel, Field


# --- Response ---

class PVExtractionResponse(BaseModel):
    """
    PV extraction response format wrapper.
    Includes Success flag, Data dict, and error handling structure.
    """
    Success: bool
    Data: Optional[dict[str, Any]] = None
    Error: Optional[str] = None

    @classmethod
    def from_extraction_dict(cls, data: dict[str, Any]) -> "PVExtractionResponse":
        """Build response from correct process_pv output."""
        return cls(Success=True, Data=data)


# --- Health ---

def _default_api_uris() -> dict[str, str]:
    return {
        "root": "/api/",
        "pv_extraction": "/api/report/extract",
        "version": "/api/version",
        "health": "/api/health",
    }


class HealthResponse(BaseModel):
    status: str = "running"
    message: str = "PV Extraction API is active"
    uris: dict[str, str] = Field(default_factory=_default_api_uris)
