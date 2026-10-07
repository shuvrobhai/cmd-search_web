# Glossary

## Provider

The abstract platform interface that this tool targets. A Provider supplies a root directory, per-conversation state, JSONL event logs, and a known tool-call protocol. The current implementation targets **Antigravity** as the Provider, but the domain model is structured so that another Provider can be substituted without changing the core extraction logic.

## Antigravity

The current **Provider** implementation (App, IDE, CLI). Its concrete artifacts — `.gemini/antigravity*` brain paths, `ANTIGRAVITY_*` environment variables, `PLANNER_RESPONSE`/`SEARCH_WEB`/`GENERIC` record types, and the `search_web` tool name — are all Provider-level details, not intrinsic domain concepts.

## Provider Protocol

The contract a Provider must satisfy for this tool to extract search results:

1. **Root directory** — a Provider root containing per-conversation UUID directories.
2. **Active marker** — an optional `.active_session` file in the Provider root naming the current conversation UUID.
3. **Transcript** — each conversation has a `.system_generated/logs/` directory containing `transcript.jsonl` (standard) or `transcript_full.jsonl` (full).
4. **Event records** — JSONL records with at least these types:
   - `PLANNER_RESPONSE` carrying `tool_calls`, each with `name`, `args`/`arguments`, and optional `id`/`tool_call_id`.
   - `SEARCH_WEB` or `GENERIC` execution records carrying `tool_call_id`, `content`, and optional `truncated_fields`.
5. **Step indexing** — records carry `step_index` for sequential pairing fallback.
6. **Truncation signal** — the presence of `truncated_fields` on any record indicates the transcript was cut off.

Provider-specific details (paths, environment variable names, record-type strings, and the tool name `search_web`) are currently hardcoded and represent the migration surface.

## Surface

A Provider runtime context. One of `app`, `cli`, or `ide`. Each surface maps to a distinct Provider root directory.

## Brain

The Provider root filesystem directory for a given surface, where per-conversation state, transcripts, and scratch outputs are stored.

## Conversation

A single Provider conversational session, identified by a UUID. Contains a transcript, search results, and scratch outputs. Also referred to as a `conv`.

## Active Conversation

The currently running or most-recently active conversation, detected either by a `.active_session` marker or by modification time within a 10-minute window.

## Transcript

The JSONL log of a conversation's events. Two variants exist:

- **Standard transcript** — `transcript.jsonl`, the normal event log.
- **Full transcript** — `transcript_full.jsonl`, the complete/untouched event log.

The engine resolves to the full transcript when present, falling back to the standard transcript.

## Search Call

A single `search_web` tool invocation emitted by the planner (`PLANNER_RESPONSE`). Carries a `query`, optional `tool_call_id`, `timestamp`, and `step_index`.

## Search Execution Record

The execution output produced by the Provider when it fulfills a `search_web` tool call. Record types are `SEARCH_WEB` or `GENERIC`. Carries `content`, optional `tool_call_id`, and a `truncated_fields` flag when the log was cut off.

## Search Result

The processed, paired representation of a search. A `SearchResult` carries `query`, `summary`, `sources`, `timestamp`, `index`, `surface`, `conversation_id`, `is_truncated`, and `schema_version`. Distinct from a search call or search execution record.

## Source

A single citation extracted from a search execution record's content. Carries `title`, `url`, and optional `snippet`.

## Pairing

The process of matching a `Search Call` to its corresponding `Search Execution Record`. The engine supports two strategies:

- **Explicit ID pairing** — matches on `tool_call_id`.
- **Sequential pairing** — matches by `step_index` adjacency or content signature when no ID is present.

## Stabilization

The state in which a transcript file's size has stopped changing and all expected records are visible. The engine polls until stabilization or timeout.

## Truncation

A condition where a transcript record or search result has been cut off, indicated by the presence of `truncated_fields` in the JSONL record or `is_truncated=True` on a `SearchResult`.

## Export

The act of writing `SearchResult` objects to a destination (stdout or filesystem) in one of three formats: Markdown (`md`), JSON (`json`), or JSONL (`jsonl`).

## Atomic Write

A crash-safe file write pattern: content is written to a temporary file, then promoted to the target path via `os.replace`. Permissions are set to `0600` on POSIX.

## Session Ambiguity

An error condition that occurs when more than one active conversation is detected within the 10-minute window, requiring the user to disambiguate with `--conv-id`.

## Index

The zero-based position of a `SearchResult` within a conversation's ordered list of paired searches.

## Schema Version

The version of the `SearchResult` data format, currently `2.1.0`.
