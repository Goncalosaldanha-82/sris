# ATLAS Chat Bridge v0.1

## What it does

The bridge receives conversation content and passes it into the ATLAS Knowledge Engine.

It:

1. accepts Markdown, TXT or structured JSON transcripts;
2. parses user/assistant/system messages;
3. redacts common secrets and tokens;
4. creates a governed chat intake;
5. stores the original intake under `docs/atlas/chat-inbox/`;
6. invokes the ATLAS Knowledge Engine;
7. creates a receipt under `docs/atlas/chat-receipts/`;
8. previews or applies the resulting knowledge assets;
9. can run as a watched-folder service;
10. can run as a local HTTP API.

## Critical truth

This bridge cannot invisibly read the live ChatGPT conversation by itself.

For direct live capture, ChatGPT must send the conversation to the bridge through a supported connector, browser extension, local helper or export action. v0.1 supplies the receiving, redaction, normalization and processing layer.

## Fastest practical workflow

1. Select conversation text.
2. Copy it.
3. Run:

```powershell
.\scripts\ATLAS_CAPTURE_CLIPBOARD.ps1
```

The transcript is saved and processed automatically.

Use `-Apply` only after previewing the process:

```powershell
.\scripts\ATLAS_CAPTURE_CLIPBOARD.ps1 -Apply
```

## Watched folder

Start:

```cmd
scripts\START_ATLAS_CHAT_WATCHER.cmd
```

Drop `.md`, `.txt` or `.json` transcripts into:

```text
docs/atlas/chat-drop/
```

The watcher automatically processes them and moves them to:

```text
docs/atlas/chat-drop/processed/
```

## Local API

Run:

```bash
uvicorn app.atlas_chat_bridge.api:app --host 127.0.0.1 --port 8787
```

Health:

```text
GET http://127.0.0.1:8787/health
```

Ingest:

```text
POST http://127.0.0.1:8787/ingest
```

For basic protection, set:

```text
ATLAS_CHAT_BRIDGE_KEY=<your-secret>
ATLAS_REPOSITORY_ROOT=C:\Users\barba\Documents\GitHub\sris
```

## Governance

- no automatic merge;
- no direct modification of protected branches;
- secret redaction before repository storage;
- human review remains mandatory;
- transcript content is treated as provisional until approved.
