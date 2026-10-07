# ADR-0002: Polling-Based Transcript Stabilization

## Status

Accepted

## Context

The engine must wait until a conversation's transcript file has finished writing before it attempts to pair and extract search results. If extraction runs before the transcript stabilizes, records may be incomplete or missing.

## Decision

Use a **polling loop** that re-reads the transcript file until its size stops changing (stabilization) and the expected number of `SearchResult` records is available, or until a configurable timeout expires.

Polling interval: 0.1 seconds. Default timeout: 5.0 seconds.

## Rationale

- **Simplicity** — polling requires no external dependencies (e.g., `watchdog`, `inotify`) and works identically on Linux, macOS, and Windows.
- **Portability** — an event-driven approach would require platform-specific filesystem notification mechanisms or Provider support for change events.
- **Predictability** — the timeout gives users a clear, tunable bound on extraction latency.

## Alternatives Considered

- **Filesystem notifications (inotify / FSEvents / ReadDirectoryChangesW)** — rejected due to platform-specific code, extra dependencies, and the fact that the current Provider does not expose a notification API.
- **Longer fixed sleep before extraction** — rejected because it adds unnecessary latency when the transcript is already stable and provides no guarantee of completeness.

## Consequences

- Extraction latency is bounded by the timeout, not by actual transcript completion.
- A busy system with slow I/O may hit the timeout and return partial results.
- The poll loop consumes a small amount of CPU while waiting.
