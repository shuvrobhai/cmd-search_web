# ADR-0002: Polling-Based Transcript Stabilization

## Status

Accepted

## Context

The engine must wait until a conversation's transcript file has finished writing before it attempts to pair and extract search results. If extraction runs before the transcript stabilizes, records may be incomplete or missing.

## Decision

Use a **polling loop** operating against an abstract **`TranscriptSource`** seam that re-reads transcript records until size/record count stabilizes and expected `SearchResult` records are visible, or until a configurable timeout expires.

- **Seam**: The loop accepts `conv_dir: Path | TranscriptSource`.
- **Adapters**:
  1. `JsonlAdapter`: Filesystem adapter polling until file size is invariant across intervals (`curr_size == last_size and curr_size > 0`).
  2. `MemoryTranscriptSource`: In-memory adapter enabling instant, zero-I/O testing of stabilization and extraction without disk dependencies.
- **Pure Extraction**: Decoupled via `extract_searches(source, ...)` for callers that do not require polling.
- **Timing**: Polling interval: 0.1 seconds. Default timeout: 5.0 seconds.

## Rationale

- **Simplicity** — polling requires no external dependencies (e.g., `watchdog`, `inotify`) and works identically on Linux, macOS, and Windows.
- **Portability** — an event-driven approach would require platform-specific filesystem notification mechanisms or Provider support for change events.
- **Testability & Seams** — decoupling file resolution from polling allows `poll_and_extract_searches` and `extract_searches` to be tested completely in memory with zero filesystem access.
- **Predictability** — the timeout gives users a clear, tunable bound on extraction latency.

## Alternatives Considered

- **Filesystem notifications (inotify / FSEvents / ReadDirectoryChangesW)** — rejected due to platform-specific code, extra dependencies, and the fact that the current Provider does not expose a notification API.
- **Longer fixed sleep before extraction** — rejected because it adds unnecessary latency when the transcript is already stable and provides no guarantee of completeness.

## Consequences

- Extraction latency is bounded by the timeout, not by actual transcript completion.
- A busy system with slow I/O may hit the timeout and return partial results.
- The poll loop consumes a small amount of CPU while waiting.
- The `TranscriptSource` protocol is a real, two-adapter seam (`JsonlAdapter` and `MemoryTranscriptSource`), enabling fast unit testing without disk I/O.
