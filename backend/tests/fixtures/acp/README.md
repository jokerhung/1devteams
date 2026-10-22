# Real ACP captures

`claude.ndjson` and `codex.ndjson` contain sanitized **agent stdout**, one original JSON-RPC message
per line. Matching `.client.ndjson` files contain messages sent by the spike client, in send order.
They share a stable ID mapping. Request IDs are scoped to their direction; agent request ID `0`
is valid. Chunk boundaries, config catalogs and unknown extension notifications are retained.

Codex is a completed file-creation/permission/cancellation capture. Claude is an
initialize/new/model-selection/cancellation capture while its configured inference gateway was down;
it is **not** evidence of working Claude tools. See `docs/specs/ACP_SPIKE_NOTES.md` at repo root.

These are evidence for Phase 1 fake-agent scenarios, not hand-authored success fixtures.
Do not add credentials, unsanitized paths, real session IDs or account details.
