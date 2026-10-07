# ADR-0001: Hybrid Search Call Pairing

## Status

Accepted

## Context

The engine must match each search tool call (emitted by the planner as a planner-response record) to its corresponding execution output (an execution record) in order to build a Search Result.

Provider transcripts do not guarantee the presence of a stable `tool_call_id` across all record types. In some transcripts, the planner emits calls with IDs; in others, it emits calls without IDs, relying on sequential `step_index` ordering instead.

## Decision

Use a **hybrid pairing algorithm** that attempts both strategies in sequence, parameterized by a **Provider Protocol Seam** (`ProviderConfig`):

1. **Explicit ID pairing** — if a `tool_call_id` is present on both the call and the execution record, match them directly.
2. **Sequential pairing** — if no ID match is found, evaluate through `match_and_consume_sequential_call`, checking `step_index` adjacency (`step_index == last_call['step_index'] + 1`) or matching configured search content signatures (`"The search for"` / `"Created At:"`).

All record types (`planner_record_types`, `execution_record_types`), tool names (`tool_name`), and content signatures (`search_signatures`) are injected via `ProviderConfig` (defaulting to `ANTIGRAVITY_PROVIDER`), eliminating hardcoded literals from the pairing loop.

## Rationale

- **ID pairing** is robust and unambiguous, but fails when the Provider omits `tool_call_id` from either side of the pair.
- **Sequential pairing** works when IDs are absent, but is fragile if records from other tool calls are interleaved between the planner response and the execution output.
- The hybrid approach covers both transcript shapes without requiring a single canonical format from the Provider.
- Isolating sequential matching into `match_and_consume_sequential_call` and schema identifiers into `ProviderConfig` provides locality, making both heuristics independently testable and configurable across Providers.

## Consequences

- Pairing complexity is managed via modular strategy functions rather than monolithic loops.
- `ProviderConfig` provides an explicit migration seam: new Providers or schema evolutions can be configured without modifying the core extraction engine.
- Heuristic fallback risks (interleaved false positives) are documented and guarded with targeted unit tests.
