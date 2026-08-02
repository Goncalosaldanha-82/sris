from __future__ import annotations

import re
from dataclasses import dataclass

from .models import ChatConversation, ChatMessage


@dataclass(frozen=True)
class RedactionResult:
    conversation: ChatConversation
    count: int


class SensitiveDataRedactor:
    """Conservative redaction for common secrets before repository ingestion."""

    PATTERNS = [
        re.compile(r"(?i)\bghp_[A-Za-z0-9]{20,}\b"),
        re.compile(r"(?i)\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
        re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{20,}\b"),
        re.compile(r"(?i)\bAKIA[0-9A-Z]{16}\b"),
        re.compile(r"(?i)(password|senha|token|secret|api[_ -]?key)\s*[:=]\s*\S+"),
    ]

    def redact(self, conversation: ChatConversation) -> RedactionResult:
        total = 0
        messages: list[ChatMessage] = []

        for message in conversation.messages:
            content = message.content
            for pattern in self.PATTERNS:
                content, count = pattern.subn("[REDACTED]", content)
                total += count
            messages.append(message.model_copy(update={"content": content}))

        return RedactionResult(
            conversation=conversation.model_copy(update={"messages": messages}),
            count=total,
        )
