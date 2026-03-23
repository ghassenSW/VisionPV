"""Pydantic schemas for API request/response validation."""

from typing import Any
from pydantic import BaseModel, RootModel


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

class HealthResponse(BaseModel):
    status: str = "running"
    message: str = "PV Extraction API is active"
