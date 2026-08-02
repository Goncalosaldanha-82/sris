from __future__ import annotations

from .models import ChatConversation, Speaker


class ConversationNormalizer:
    """Converts a conversation into an ATLAS Knowledge Engine intake document."""

    def to_knowledge_intake(self, conversation: ChatConversation) -> str:
        sections: list[str] = [
            f"# Chat Intake — {conversation.title}",
            "",
            f"**Conversation ID:** `{conversation.conversation_id}`  ",
            f"**Source:** `{conversation.source}`  ",
            f"**Captured:** `{conversation.captured_at.isoformat()}`  ",
            "",
            "## Observation",
            "",
            "The following conversation was captured for governed ATLAS knowledge triage.",
            "",
            "## Research Note",
            "",
        ]

        for index, message in enumerate(conversation.messages, start=1):
            label = {
                Speaker.USER: "User",
                Speaker.ASSISTANT: "Assistant",
                Speaker.SYSTEM: "System",
                Speaker.UNKNOWN: "Unknown",
            }[message.speaker]
            sections.extend(
                [
                    f"### Message {index} — {label}",
                    "",
                    message.content.strip(),
                    "",
                ]
            )

        sections.extend(
            [
                "## Risk",
                "",
                "Conversation-derived content may contain provisional ideas, duplicates, errors or unsupported claims. "
                "No extracted item is adopted without human review.",
                "",
                "## Action",
                "",
                "Classify, route and index relevant decisions, hypotheses, concepts, risks, actions and observations "
                "through the ATLAS Knowledge Engine.",
                "",
            ]
        )
        return "\n".join(sections)
