---
name: cmd-search_web
description: High-efficiency CLI web research pipeline. Executes search_web, lists search history, and extracts clean Markdown notes via scripts with zero LLM context bloat.
disable-model-invocation: true
---

# Web Search Power Skill (`/cmd-search_web`)

## Overview
A script-driven, token-conserving research pipeline for Antigravity surfaces (App, CLI). It executes native `search_web`, delegates result extraction and note generation directly to local Python scripts, and returns minimal summaries without polluting the LLM conversation context[span_0](start_span)[span_0](end_span).

---

## When to Use
- Invoked explicitly via `/cmd-search_web <query>`[span_1](start_span)[span_1](end_span).
- Performing documentation searches, error code investigations, changelog tracking, or library updates without loading multi-kilobyte text payloads into the chat session[span_2](start_span)[span_2](end_span).

---

## Execution Workflow

When the user triggers `/cmd-search_web <query>`, follow these 3 steps strictly:

### Step 1: Execute Native Search
Run the native `search_web` harness tool with precise, keyword-targeted parameters[span_3](start_span)[span_3](end_span):
- Include library names, exact error codes, function signatures, or versions[span_4](start_span)[span_4](end_span).
- **Never dump the full raw output into the chat response.**

### Step 2: Trigger Out-of-Band Script Export
Immediately run the extraction script via bash (`run_command`) to read the disk transcript and generate a structured note[span_5](start_span)[span_5](end_span):

```bash
# If running inside active session with environment variable set:
python3 .agents/skills/cmd-search_web/scripts/export_search.py --auto --index -1

# Or explicitly pass the active session ID:
python3 .agents/skills/cmd-search_web/scripts/export_search.py --conv-id "$ANTIGRAVITY_CONV_ID" --index -1


Step 3: Return Lean Confirmation

Return a concise, 2–3 bullet summary to the user in chat, followed by the generated file path:

⚬ Core Insight: 1–2 key points directly answering the search prompt.
⚬ Reference File: Markdown link to the generated note in scratch/search_web/.

CLI Helper Commands

Task	Command
List past searches	python3 .agents/skills/cmd-search_web/scripts/list_searches.py --auto
Export specific search	python3 .agents/skills/cmd-search_web/scripts/export_search.py --auto --index <N>
Export all as JSONL	python3 .agents/skills/cmd-search_web/scripts/export_search.py --auto --all --format jsonl
Custom destination	python3 .agents/skills/cmd-search_web/scripts/export_search.py --auto --output-dir docs/research/

Error Handling Matrix

Exit Code	Cause	Agent Action
10 (ERR_DATA_TRUNCATED)	Log truncated on disk	Re-run with --allow-truncated or notify user of lossy log state.
11 (ERR_AMBIGUOUS_SESSION)	Multiple recent active sessions	Run list_searches.py or inspect active conversation UUID to pass --conv-id.
12 (ERR_POLL_TIMEOUT)	I/O buffer flush delayed	Retry once with --timeout 10.0.
13 (ERR_INDEX_OUT_OF_BOUNDS)	Search index not found	Run list_searches.py --auto to show available indices.
14 (ERR_FILE_EXISTS)	Target note already exists	Pass --force if updating an existing research document.
19 (ERR_NO_TRANSCRIPT)	Invoked from IDE surface	Inform the user that the IDE surface lacks JSONL transcripts; run via App or CLI (agy).