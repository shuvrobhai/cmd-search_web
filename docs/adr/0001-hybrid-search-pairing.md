# ADR-0001: Hybrid Search Call Pairing

## Status

Accepted

## Context

The engine must match each search tool call (emitted by the planner as a planner-response record) to its corresponding execution output (an execution record) in order to build a Search Result.

Provider transcripts do not guarantee the presence of a stable `tool_call_id` across all record types. In some transcripts, the planner emits calls with IDs; in others, it emits calls without IDs, relying on sequential `step_index` ordering instead.

## Decision

Use a **hybrid pairing algorithm** that attempts both strategies in sequence:

1. **Explicit ID pairing** — if a `tool_call_id` is present on both the call and the execution record, match them directly.
2. **Sequential pairing** — if no ID match is found, match by `step_index` adjacency or by content signature (`"The search for"` / `"Created At:"`).

## Rationale

- **ID pairing** is robust and unambiguous, but fails when the Provider omits `tool_call_id` from either side of the pair.
- **Sequential pairing** works when IDs are absent, but is fragile if records from other tool calls are interleaved between the planner response and the execution output.
- The hybrid approach covers both transcript shapes without requiring a single canonical format from the Provider.

## Consequences

- Pairing complexity is higher than a single-strategy approach.
- Sequential matching may produce false positives in heavily interleaved transcripts.
- Future changes to the Provider's record format may require revisiting both strategies.
