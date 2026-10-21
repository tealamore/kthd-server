"""Request bodies. Pydantic validates these and rejects anything malformed with a 422."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConsentIn(_Base):
    participant_id: str = Field(min_length=1, max_length=128)
    consented: bool
    consent_version: str = Field(min_length=1, max_length=64)
    occurred_at: datetime | None = None
    extra: dict[str, Any] | None = None


class OpportunityIn(_Base):
    participant_id: str = Field(min_length=1, max_length=128)
    context: dict[str, Any]
    available: bool = True
    occurred_at: datetime | None = None
    client_decision_id: str | None = Field(default=None, max_length=128)


class RewardIn(_Base):
    decision_id: str = Field(min_length=1, max_length=64)
    reward: float = Field(allow_inf_nan=False)
    occurred_at: datetime | None = None
    extra: dict[str, Any] | None = None
