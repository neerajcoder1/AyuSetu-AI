"""
Hindsight Long-Term Memory Layer — Data Contracts
===================================================
Data structures for configuring, storing, and querying long-term contextual memory.
"""

import os
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class HindsightConfig(BaseModel):
    """Configuration for Hindsight long-term memory integration."""
    enabled: bool = Field(
        default_factory=lambda: os.getenv("HINDSIGHT_ENABLED", "false").lower() in ("true", "1", "yes")
    )
    api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("HINDSIGHT_API_KEY")
    )
    api_url: str = Field(
        default_factory=lambda: os.getenv("HINDSIGHT_API_URL", "https://api.hindsight.ai/v1")
    )
    timeout_sec: float = Field(
        default_factory=lambda: float(os.getenv("HINDSIGHT_TIMEOUT_SEC", "3.0"))
    )


class HindsightMemoryRecord(BaseModel):
    """An individual memory record stored in Hindsight."""
    record_id: Optional[str] = None
    patient_id: str
    session_id: Optional[str] = None
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, str] = Field(default_factory=dict)


class HindsightQueryResult(BaseModel):
    """Result of querying Hindsight for historical context."""
    patient_id: str
    query: str
    records: List[HindsightMemoryRecord] = Field(default_factory=list)
    relevance_scores: List[float] = Field(default_factory=list)

    def format_as_context(self) -> Optional[str]:
        """Format retrieved records into a background context string for LLM prompts."""
        if not self.records:
            return None
        lines = []
        for i, rec in enumerate(self.records, 1):
            date_str = rec.timestamp.strftime("%Y-%m-%d") if rec.timestamp else "Past Visit"
            lines.append(f"- [{date_str}] {rec.content}")
        return "\n".join(lines)
