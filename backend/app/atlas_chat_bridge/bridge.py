from __future__ import annotations

import json
from pathlib import Path

from app.atlas_knowledge_engine.engine import AtlasKnowledgeEngine

from .models import BridgeReceipt, ChatConversation
from .normalizer import ConversationNormalizer
from .parser import ChatParser
from .redactor import SensitiveDataRedactor


class AtlasChatBridge:
    def __init__(self) -> None:
        self.parser = ChatParser()
        self.redactor = SensitiveDataRedactor()
        self.normalizer = ConversationNormalizer()
        self.engine = AtlasKnowledgeEngine()

    def ingest_file(
        self,
        *,
        source_file: Path,
        repository_root: Path,
        apply: bool = False,
    ) -> tuple[BridgeReceipt, str]:
        conversation = self.parser.from_file(source_file)
        return self.ingest_conversation(
            conversation=conversation,
            repository_root=repository_root,
            apply=apply,
        )

    def ingest_conversation(
        self,
        *,
        conversation: ChatConversation,
        repository_root: Path,
        apply: bool = False,
    ) -> tuple[BridgeReceipt, str]:
        redacted = self.redactor.redact(conversation)
        intake_text = self.normalizer.to_knowledge_intake(redacted.conversation)

        inbox = repository_root / "docs/atlas/chat-inbox"
        receipts = repository_root / "docs/atlas/chat-receipts"
        inbox.mkdir(parents=True, exist_ok=True)
        receipts.mkdir(parents=True, exist_ok=True)

        intake_name = f"CHAT-{str(conversation.conversation_id)[:8]}.md"
        intake_path = inbox / intake_name
        intake_path.write_text(intake_text, encoding="utf-8")

        plan = self.engine.plan(source_file=intake_path, repository_root=repository_root)
        preview = self.engine.preview(source_file=intake_path, repository_root=repository_root)

        if apply:
            self.engine.apply_local(source_file=intake_path, repository_root=repository_root)
            status = "applied-locally"
        else:
            status = "preview-only"

        receipt = BridgeReceipt(
            conversation_id=conversation.conversation_id,
            intake_path=str(intake_path.relative_to(repository_root)),
            message_count=len(conversation.messages),
            redactions=redacted.count,
            knowledge_plan_items=len(plan.packet.items),
            status=status,
        )

        receipt_path = receipts / f"RECEIPT-{str(receipt.receipt_id)[:8]}.json"
        receipt_path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
        return receipt, preview
