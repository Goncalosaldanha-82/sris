from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


class Speaker(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class ChatMessage(BaseModel):
    speaker: Speaker
    content: Annotated[str, Field(min_length=1, max_length=100000)]
    created_at: datetime | None = None
    message_id: str | None = None

    @field_validator("created_at")
    @classmethod
    def timezone_if_present(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


class ChatConversation(BaseModel):
    conversation_id: UUID = Field(default_factory=uuid4)
    title: Annotated[str, Field(min_length=1, max_length=255)]
    source: str = "chatgpt-manual-export"
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    messages: list[ChatMessage] = Field(min_length=1)
    author: str = "Human-supervised ATLAS workflow"
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("captured_at")
    @classmethod
    def captured_at_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")
        return value


class BridgeReceipt(BaseModel):
    receipt_id: UUID = Field(default_factory=uuid4)
    conversation_id: UUID
    intake_path: str
    message_count: int
    redactions: int
    knowledge_plan_items: int
    status: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
