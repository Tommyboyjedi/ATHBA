# PR23 local-coder minimal tool audit

## Qualified versus current

PR14 qualified NotaMG/eqaq-v2 Qwen3.5 4B on RTX 2060 6 GB with context 16,368, max_num_seqs=1, JCode v0.79.1 (993da322e), and minimal tool profile; classification was qualified_with_constraints. Current installed JCode is v0.80.0 (c3ccfa051) at /home/tomp/.jcode/builds/versions/0.80.0/jcode, reached through /home/tomp/.local/bin/jcode. Rack AI still configures local-coder with minimal, provider/profile local-coder, model NotaMG/eqaq-v2, and context 16,368. The session did not alter JCode or Rack AI configuration.

The installed binary exposes both --tool-profile and --tools. Rack AI's actual invocation supplies --tool-profile minimal and no explicit --tools argument.

## Captured installed-runtime schema

A disposable loopback-only proxy captured the outbound OpenAI-compatible request from the installed binary under the actual minimal configuration. The exact advertised names were agentgrep, apply_patch, bash, edit, ls, multiedit, patch, read, write.

There were nine tool schemas (7,374 bytes serialized). grep was not advertised; agentgrep, read, ls, and edit/patch tools were advertised.

## Preserved Latch execution

The Latch run selected local-coder, invoked JCode with --tool-profile minimal and no --tools, and first called read. It then called grep with query class Latch; JCode rejected it as Tool grep is not allowed and exited immediately. No source/revision existed; no later in-invocation opportunity existed. Rack AI terminalized the packet, although the old ATHBA state incorrectly called one submission exhaustion.

## Direct requalification

| Trial | Task | Result |
| --- | --- | --- |
| 1 | Truthful no-change repository inspection | pass; deterministic check and empty tracked diff |
| 2 | Single-file arithmetic repair | pass; minimal tools only; deterministic pytest pass |
| 3 | Repeat single-file repair | pass; minimal tools only; deterministic pytest pass |

All had 300-second bounds, a disposable Git fixture, disposable JCODE_HOME, and a loopback-only network guard. No trial attempted grep.

## Classification

TOOL_NOT_ADVERTISED_MODEL_CALLED. The model invented grep; this is a model-originated failed submission, not evidence to add grep. grep is text search, not filesystem access: ls discovers paths, read accesses contents, agentgrep searches repository source, and edit/write/patch mutate. PR14 already qualified minimal navigation and repair without dedicated grep.

No Rack AI/JCode restoration change is justified by this evidence and no tool policy changed.
