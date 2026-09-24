from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class CheckState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    AUTH_REQUIRED = "auth_required"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class Target(BaseModel):
    id: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9._-]+$")
    center: str = Field(min_length=1)
    category: str = Field(min_length=1)
    subcategory: str | None = None
    enabled: bool = True
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def validate_date_window(self) -> Target:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be <= date_to")
        return self

    def accepts_date(self, candidate: date) -> bool:
        if self.date_from and candidate < self.date_from:
            return False
        if self.date_to and candidate > self.date_to:
            return False
        return True


class SlotObservation(BaseModel):
    target_id: str
    state: CheckState
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: str = ""
    visible_dates: tuple[date, ...] = ()
    matching_dates: tuple[date, ...] = ()
    source_url: str = ""

    @property
    def fingerprint(self) -> str:
        payload = {
            "target_id": self.target_id,
            "state": self.state.value,
            "visible_dates": [item.isoformat() for item in self.visible_dates],
            "matching_dates": [item.isoformat() for item in self.matching_dates],
            "details": self.details[:300],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()


class StateChange(BaseModel):
    previous_state: CheckState | None
    state_changed: bool
    fingerprint_changed: bool
