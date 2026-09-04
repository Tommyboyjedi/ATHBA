# Behavior Planner qualification corpus V1

## Input invariant

The Behavior Planner receives one component-level requirement expressed as
ordinary behavioral prose. Its job is to decompose that broader behavioral
description into smaller behavioral requirements while preserving the source
meaning and traceability.

The component requirement is not:

- a numbered or bulleted pre-decomposition into micro-behaviors;
- a Tester scenario;
- test code;
- a code snippet;
- method-call syntax;
- assertions;
- a RED frontier;
- a list of test hints; or
- instructions for how the behavior should be tested.

Repository, path, and schema metadata supplied mechanically by ATHBA is not
itself part of the human behavioral requirement.

The previous three-line, API-shaped SignalBoard qualification input is retained
only as historical evidence. It is not a valid BPQ-V1 Behavior Planner
qualification fixture and must not be used for new planner qualification runs.

## Frozen corpus

The canonical source is
`qualification_fixtures/behavior_planner_qualification_v1.json`, loaded only by
`core.development.behavior_planner_qualification.load_behavior_planner_qualification_v1`.
It contains exactly these three cases:

| ID | Component | UTF-8 requirement-text SHA-256 |
| --- | --- | --- |
| BPQ-V1-A | ReservationBook | 6a88d231bc489d24507b0b9a7abbc61bd6e13e418a0d65567490da25c72eea36 |
| BPQ-V1-B | SignalBoard | c46ce04d165b64d2459fdd821475289925496dc7541584230d60f4858ec9aa88 |
| BPQ-V1-C | ParcelLocker | 65fe74ab5a04edd6b3e1cecd6a93da5b2b05ad45d973b131f712c8a4678d78bd |

The stable corpus SHA-256 is 523dc088007cdcd10484daa7cb272fdbdab4a37a306a5369bbeac1ff676d85cb. It is the SHA-256 of the UTF-8 canonical
JSON serialization with `corpus_version` and ordered cases containing `id`,
`component_name`, and `requirement_text`, no extra whitespace, and no ASCII
escaping.

BPQ-V1 is the permanent, exclusive canonical corpus. It may not be edited,
replaced, superseded, expanded, or supplemented. No successor version, alternate
fixture, or auxiliary corpus may be introduced for Behavior Planner
qualification.

The loader and deterministic regression tests make accidental mutation loud.
They do not prevent an intentional, reviewed source-control change; they make
any such change fail loudly so it can be rejected before it is treated as a
qualification corpus.

## Qualification protocol: recorded, not executed

When explicitly authorised, the next Behavior Planner qualification will use
BPQ-V1's three fixtures, with three independent repetitions per fixture, for
nine semantic runs total. Each repetition loads the exact requirement text from
the frozen fixture. There is no fixture rewriting, prompt tuning, or
model/configuration change between repetitions. No SignalBoard or ReservationBook
end-to-end application proof is part of this planner qualification.

Each future result must record the corpus version, fixture id, requirement-text
SHA-256, ATHBA git head, planner prompt/version identity then available,
model/execution provenance, raw planner output or evidence reference, and
deterministic validation result.

This task freezes the exact component `requirement_text` corpus only. It does not
claim that the complete rendered internal Behavior Planner prompt is frozen
forever. Once the planner output responsibility/schema is agreed, that prompt
must receive its own explicit version and hash before semantic qualification.

## Historical status

The Observation Resolver experiment was introduced in `0505e11` and corrected in
`c5ac723`. Subsequent review determined that it placed a new LLM semantic
decision in the wrong layer, so both commits were explicitly reverted. Its
semantic-qualification results are historical evidence only; they are not
evidence that local-primary is generally unqualified for Behavior Planning,
Tester work, or other roles. The deterministic Behavior Contract static lint
that predates the experiment remains retained.
