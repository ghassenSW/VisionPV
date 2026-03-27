"""Pydantic schemas for API request/response validation."""

from typing import Any
from pydantic import BaseModel, Field, RootModel


# --- Response ---

class PVExtractionResponse(RootModel[dict[str, Any]]):
    """
    PV extraction response. Excludes Référence FTUSA.
    Validates and serializes the full extraction dict.
    """

    @classmethod
    def from_extraction_dict(cls, data: dict[str, Any]) -> "PVExtractionResponse":
        """Build response from process_pv output, excluding Référence FTUSA."""
        cleaned = {k: v for k, v in data.items() if k != "Référence FTUSA"}
        return cls(root=cleaned)


# --- Health ---

def _default_api_uris() -> dict[str, str]:
    return {
        "root": "/api/v1/pv/",
        "pv_extraction": "/api/v1/pv/pv-extraction",
        "health": "/api/v1/pv/health",
    }


class HealthResponse(BaseModel):
    status: str = "running"
    message: str = "PV Extraction API is active"
    uris: dict[str, str] = Field(default_factory=_default_api_uris)
