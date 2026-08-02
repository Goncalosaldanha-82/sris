from pathlib import Path

from app.atlas_chat_bridge.bridge import AtlasChatBridge
from app.atlas_chat_bridge.models import ChatConversation, ChatMessage, Speaker
from app.atlas_chat_bridge.parser import ChatParser
from app.atlas_chat_bridge.redactor import SensitiveDataRedactor


def seed_repo(root: Path) -> None:
    paths = [
        "docs/atlas/research-notes",
        "docs/atlas/missions",
        "docs/atlas/registry",
        "docs/atlas/knowledge-vault",
    ]
    for rel in paths:
        (root / rel).mkdir(parents=True, exist_ok=True)

    (root / "docs/atlas/registry/ASSET-REGISTRY.md").write_text(
        "# ATLAS Asset Registry\n", encoding="utf-8"
    )
    (root / "docs/atlas/knowledge-vault/MASTER-INDEX.md").write_text(
        "# ATLAS Knowledge Vault — Master Index\n", encoding="utf-8"
    )


def test_parser_role_blocks() -> None:
    text = "User: Nova hipótese.\nAssistant: Deve ser testada.\n"
    conversation = ChatParser().from_markdown(text, title="Test")
    assert len(conversation.messages) == 2
    assert conversation.messages[0].speaker == Speaker.USER


def test_redactor_removes_secret() -> None:
    conversation = ChatConversation(
        title="Secret test",
        messages=[ChatMessage(speaker=Speaker.USER, content="token: abcdefghijklmnop")],
    )
    result = SensitiveDataRedactor().redact(conversation)
    assert result.count == 1
    assert "[REDACTED]" in result.conversation.messages[0].content


def test_bridge_creates_intake_receipt_and_plan(tmp_path: Path) -> None:
    seed_repo(tmp_path)
    conversation = ChatConversation(
        title="ATLAS test conversation",
        messages=[
            ChatMessage(
                speaker=Speaker.USER,
                content="Nova decisão: o GitHub é a fonte oficial de verdade.",
            ),
            ChatMessage(
                speaker=Speaker.ASSISTANT,
                content="A decisão deve atualizar o Registry e o Knowledge Vault.",
            ),
        ],
    )

    receipt, preview = AtlasChatBridge().ingest_conversation(
        conversation=conversation,
        repository_root=tmp_path,
        apply=False,
    )

    assert receipt.message_count == 2
    assert receipt.status == "preview-only"
    assert (tmp_path / receipt.intake_path).exists()
    assert len(list((tmp_path / "docs/atlas/chat-receipts").glob("RECEIPT-*.json"))) == 1
    assert "ASSET-REGISTRY.md" in preview
