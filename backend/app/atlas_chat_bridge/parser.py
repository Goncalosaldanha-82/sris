from __future__ import annotations

import json
import re
from pathlib import Path

from .models import ChatConversation, ChatMessage, Speaker


class ChatParser:
    """Parses a structured JSON conversation or a simple Markdown transcript."""

    def from_file(self, path: Path) -> ChatConversation:
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            return ChatConversation.model_validate_json(text)
        return self.from_markdown(text, title=path.stem, source=path.name)

    def from_markdown(
        self,
        text: str,
        *,
        title: str = "ATLAS Chat Intake",
        source: str = "markdown",
    ) -> ChatConversation:
        messages = self._parse_role_blocks(text)
        if not messages:
            messages = [ChatMessage(speaker=Speaker.UNKNOWN, content=text.strip())]

        return ChatConversation(
            title=title,
            source=source,
            messages=messages,
        )

    def _parse_role_blocks(self, text: str) -> list[ChatMessage]:
        pattern = re.compile(
            r"(?mi)^(user|utilizador|assistant|assistente|system|sistema)\s*:\s*"
        )
        matches = list(pattern.finditer(text))
        if not matches:
            return []

        messages: list[ChatMessage] = []
        for index, match in enumerate(matches):
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            role = self._speaker(match.group(1))
            content = text[start:end].strip()
            if content:
                messages.append(ChatMessage(speaker=role, content=content))
        return messages

    @staticmethod
    def _speaker(value: str) -> Speaker:
        normalized = value.lower()
        if normalized in {"user", "utilizador"}:
            return Speaker.USER
        if normalized in {"assistant", "assistente"}:
            return Speaker.ASSISTANT
        if normalized in {"system", "sistema"}:
            return Speaker.SYSTEM
        return Speaker.UNKNOWN
