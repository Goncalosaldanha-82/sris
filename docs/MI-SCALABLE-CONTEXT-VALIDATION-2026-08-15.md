# SRIS · Scalable Mission Context validation

Date: 2026-08-15  
Release candidate: 1.7.0

## Result

The Mission archive is no longer used as the input window of a single model
request. Original sources, canonical records, reports, governed external
research and dialogue turns remain preserved. Each AI call receives a traced,
relevance-selected working set that fits the organization's input policy.

## Automated evidence

- Backend full suite: **94 passed, 35 skipped**.
- Mission Intelligence suite: **58 passed**.
- Frontend Node contract suite: **13 passed**.
- Python application modules compile successfully.
- Alembic validation on a fresh SQLite database:
  - upgrade from an empty database to `20260815_0010`;
  - downgrade from `20260815_0010` to `20260815_0009`;
  - re-upgrade to `20260815_0010`.
- `git diff --check`: no whitespace errors.

## Scale scenarios exercised

- Canonical Mission with 2,500 records and 3,500 relations.
- Simulated preserved archive with 10,000 attachments, 90 GB of source bytes
  and 120,000 retrieval chunks.
- Relevant record located at position 2,499 while the request remains inside a
  60,000-token governance budget.
- Encrypted original attachments and AES-GCM encrypted retrieval chunks.
- Organization-keyed HMAC search terms with no clear-text source vocabulary.
- Multiple attachment IDs resolved in database-safe batches.
- A preserved external-research dossier retrieved in a later archive search.
- Provider `context_length_exceeded` rejection followed by an automatic retry
  with a smaller traced profile and `truncation="disabled"`.

## Boundary of this validation

The suite uses deterministic provider doubles and a real OpenAI SDK error
object for rejection handling; it does not spend live provider credits. Live
staging still requires deployment of this release, application of the Alembic
migration and a governed institutional smoke test.

The correction deliberately does not claim infinite hardware or an infinite
model context window. A single file keeps its 20 MB security limit and the
storage tier remains finite. The corrected guarantee is that accumulated
Mission size is independent of one provider request: excess archive content is
preserved and remains retrievable instead of blocking the Mission.
