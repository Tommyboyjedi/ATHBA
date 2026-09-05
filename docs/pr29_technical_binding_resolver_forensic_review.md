# PR29 TechnicalBindingResolver forensic semantic review

## 1. Executive conclusion

No resolver, fixture, prompt, schema, test, or qualification run was changed for this review; no model call was made.

The evidence does **not** establish that local-primary is incapable of the intended technical-selection role. It establishes that the three qualifications did not hold one stable semantic definition of `technical binding`, and that v3 R4's empty gold answer is not valid under v3's actual prompt.

At minimum, `ApprovalService.approve` is a reasonably defensible selection for R4 under the requested relationship. The behavior occurs *when an approval is completed* and the supplied identifier is `ApprovalService.approve`. V1 and v2 raw rationales independently made exactly that trigger/participant connection. V3's phrase “genuinely belong to this behavior” did not limit selection to a method that already implements the new audit write, nor to a method that must be modified. Therefore `[]` silently imposed a narrower relation than the model was asked to resolve.

`ApprovalService.reject` is ambiguous, not clearly correct: the v3 input supplied only the identifier, no repository description, and the behavior says an approval is completed rather than a rejection is processed. Its selection does not rescue the empty gold; `approve` alone is enough to make the negative invalid under the actual prompt.

## 2. Exact semantic contracts actually used

| Version | Request and candidate representation | Exact semantic wording | Output and validator |
| --- | --- | --- | --- |
| v1 | One behavior with ref, summary, observable outcome, source refs/clauses; candidates carry `technical_ref`, `kind`, `qualified_identifier`, `origin`, `repository_evidence`, and evidence refs; inherited role constraints are supplied. | “You are resolving technical bindings for ONE behavioral requirement.” Rules include “select only supplied technical candidates”, “return no_binding_required when no supplied candidate is required”, and “preserve every inherited mandatory binding constraint”. | Exact object fields `status`, `behavior_ref`, `bindings`, `rationale`, `evidence_refs`; each binding is a candidate ref plus role (`subject`, `action`, `observation`, `state`, `error`, `other`). Resolved requires nonempty bindings and evidence; non-resolved statuses forbid bindings. |
| v2 stage 1 | The v1 behavior and full candidate records, including repository evidence and evidence refs. | “Does this ONE behavior require one or more supplied existing technical candidates?” Rules include “binding_required only if supplied candidates genuinely apply” and “no_binding_required if none apply”. | Exact object fields `status`, `behavior_ref`, `rationale`, `evidence_refs`; stage 1 forbids technical refs. |
| v2 stage 2 | Same full behavior/candidate input, inherited constraints, and stage-1 status. | “Select supplied technical refs that genuinely belong to this ONE behavior.” | Exact fields `behavior_ref`, `selected_technical_refs`, `rationale`, `evidence_refs`; selected refs must be supplied, unique, nonempty, and include inherited mandatory refs. The schema itself does **not** require an owner class. |
| v3 | One behavior with `behavior_ref`, summary, and observable outcome; candidates carry only `technical_ref` and `qualified_identifier`; optional mandatory refs. | “You are mapping ONE behavior to existing technical candidates. Return only candidate refs that genuinely belong to this behavior. Select only from the supplied refs. If none apply, return an empty selected_refs list. Do not invent anything.” | Exact fields `behavior_ref` and `selected_refs`; refs must be supplied and unique, mandatory refs must be present, and an empty list is valid. Owner expansion is deterministic after selection. |

The v1 word “required”, the v2 words “genuinely apply” and “genuinely belong”, and the v3 words “genuinely belong” are not equivalent to one another or to a direct-implementation-only relation. No version defines them operationally.

## 3. Raw qualification evidence

### Evidence roots

| Version | Root | Result |
| --- | --- | --- |
| v1 prequalification | `evidence/pr29_technical_binding_resolver_prequalification_20260904T200000Z` | 0 model calls; readiness false because configured mypy hung. |
| v1 qualification | `evidence/pr29_technical_binding_resolver_qualification_20260904T205500Z` | 12 runs; 9 mechanical, 6 semantic passes, 3 repairs. |
| v2 qualification | `evidence/technical-binding-resolver-v2-20260904T213248Z` | 12 runs; 6 mechanical, 0 semantic passes, 6 stage-1 repairs. |
| v3 qualification | `evidence/technical-binding-resolver-v3-20260904T215432Z` | 12 runs; 12 mechanical, 9 semantic passes, 0 repairs. |

### R4: exact prompts, candidates, and raw outputs

All three R4 repetitions within each completed qualification had byte-identical raw semantic outputs; the hashes below are SHA-256 over the stored response text. This records every R4 raw output without normalising any model text.

| Version | Exact prompt wording | R4 supplied candidates | Raw-output hash for R4-1/R4-2/R4-3 | Parsed/validator outcome |
| --- | --- | --- | --- | --- |
| v1 | “You are resolving technical bindings for ONE behavioral requirement.” | `R4-approval-service` / `ApprovalService`; `R4-approve` / `ApprovalService.approve` / “Completes approval.”; `R4-reject` / `ApprovalService.reject` / “Rejects approval.” | semantic `f99b34e9ec83cd3779b9646410619f011a7b8a2969f3289902c56cb970059800`; repair `dc4744e9d117178b590fc45438b0340bf7b8f63311a7fb368197468f60bb663e` | Semantic response selected service plus `R4-approve` twice; validation rejected duplicate binding. Repair replaced the duplicate with invented `R4-audit-timestamp`; validation rejected the invented ref. Parsed terminal result was `protocol_failure`. |
| v2 | “Does this ONE behavior require one or more supplied existing technical candidates?” and “binding_required only if supplied candidates genuinely apply”. | Same three v1 candidates and evidence records. | semantic and repair `955beb18396ab611294c8d4aa809313b651972072fa995090a5b1b779518dc8b` | Raw response was `binding_required` and cited `R4-approve` as an evidence ref. Validation rejected it because evidence refs must be supplied evidence refs; repair preserved the same result. Stage 2 did not run. |
| v3 | “Return only candidate refs that genuinely belong to this behavior.” and “If none apply, return an empty selected_refs list.” | `R4-approve` / `ApprovalService.approve`; `R4-reject` / `ApprovalService.reject`. | semantic `4553e07c5391dd9495f1edc71e6382246e6be3d850cb7c3195a51ddbb756953e` | Raw JSON selected `R4-approve` and `R4-reject`; it parsed and passed deterministic validation. No repair occurred. Gold expected `[]`, so semantic qualification failed. |

The exact representative stored raw responses were:

```json
// v1 semantic R4-1/R4-2/R4-3
{"behavior_ref":"R4-record-audit-timestamp","bindings":[
 {"role":"subject","technical_ref":"R4-approval-service"},
 {"role":"action","technical_ref":"R4-approve"},
 {"role":"observation","technical_ref":"R4-approve"}],
 "status":"resolved"}
```

The v1 repair retained the service and approve bindings but substituted an unsupplied `R4-audit-timestamp` for the duplicate. Its rationale said `approve` “completes the approval, which triggers the recording of the audit timestamp as the observable outcome.”

```json
// v2 stage-1 semantic and repair, all R4 repetitions
{"behavior_ref":"R4-record-audit-timestamp","evidence_refs":["R4-approve"],
 "rationale":"The 'ApprovalService.approve' method is the existing technical candidate that performs the completion of an approval, making it the relevant component to handle this logic.",
 "status":"binding_required"}

// v3 semantic, all R4 repetitions
{"behavior_ref":"R4-record-audit-timestamp","selected_refs":["R4-approve","R4-reject"]}
```

The v1 R4 output is protocol-invalid, but its semantic explanation is still forensic evidence of the relation it understood. V2 is likewise protocol-invalid because it used a technical ref where its schema required an evidence ref; that does not make its applicability judgment disappear.

### Representative R1–R3 comparison

| Case | Frozen expectation | Observed result relevant to semantics | Why it matters |
| --- | --- | --- | --- |
| R1 | publish and get-latest (plus `SignalBoard` before v3) | v3 selected publish + get-latest 3/3. | These are distinct write and read path participants. They do not denote one pre-existing direct audit-style operation. This makes the corpus broader than direct implementation ownership. |
| R2 | find-customer (plus `CustomerRepository` before v3) | v1 selected the correct repository and find method but used `action` where the frozen role was `observation`; v2 selected only find-customer 3/3; v3 selected it 3/3. | The method is a retrieval surface/participant. The v2 owner-class expectation was not expressed by the stage-2 selection prompt and was later removed by deterministic owner expansion. |
| R3 | update (plus `ReservationBook` before v3) | v2 selected only update 3/3; v3 selected it 3/3. | `R3-update` was explicitly inherited mandatory. It is not an independent discovery test of the relation; it tests compliance with an externally mandated identity. |

## 4. R4 semantic analysis

### Independent judgment before consulting the frozen gold

- `ApprovalService.approve`: **reasonably defensible, and strongly so** under v3. The behavior is conditioned on approval completion and the supplied identifier is the method named `approve`. It is a trigger and likely execution participant; it may also be a modification target. It is not proven to already implement the new audit write, but the prompt never required that narrower proof.
- `ApprovalService.reject`: **ambiguous**. The word `reject` does not directly match “an approval is completed”, and v3 supplies no repository explanation. It may nevertheless be read as another terminal approval-decision path. The prompt's broad “genuinely belong” language gives the model no criterion that excludes it.

### Is `[]` a valid R4 gold answer?

No, not for the actual v3 prompt. `[]` would be a valid gold answer only for the unstated relation “none of these supplied methods directly implements the new audit-timestamp operation” or, possibly, “none is an authorized modification target under a separately supplied repository fact.” It does **not** prove “none of the supplied existing technical elements apply” under `genuinely belong`.

V1 and v2 reinforce this finding rather than contradict it: both independently linked `approve` to completion and to the timestamp behavior. Their protocol errors are real, but their shared semantic interpretation is a reasonable reading of the text presented.

## 5. Cross-case consistency

The corpus does not hold one definition stable across R1–R4.

- R1 treats both publish and read as bound: an execution path / dependency / observation-surface reading.
- R2 treats find as bound: a retrieval surface or direct implementation reading.
- R3 treats update as bound chiefly because it is explicitly mandatory: an externally mandated interface reading.
- R4 expects no binding even though approve is a trigger and likely execution participant: a direct-new-operation or modification-target-only reading.

Those are different relationships. The v2 expectation that the model also select owner classes, followed by v3 deterministic owner expansion, is independent evidence that ownership was being mixed into selection rather than defined at the boundary.

## 6. Failure reclassification

| Apparent result | Forensic classification | Reason |
| --- | --- | --- |
| v1 R2 | MIXED | Correct repository and method selection, but role mismatch against a role taxonomy whose operational meanings were not defined; this is not evidence that subset selection failed. |
| v1 R4 | MIXED | Semantically defensible trigger/participant selection, plus real model protocol failures: duplicate binding then invented audit ref in repair. The negative expectation is also ambiguous. |
| v2 R1 | VALIDATOR/SCHEMA_PROBLEM | Stage 1's applicability content was positive, but the model put technical refs in `evidence_refs`; no selection stage ran. |
| v2 R2 | TEST_EXPECTATION_AMBIGUOUS | Model selected find-customer; frozen gold additionally demanded the owner class without a stage-2 owner rule. V3 later derived the owner mechanically. |
| v2 R3 | TEST_EXPECTATION_AMBIGUOUS | Model selected the mandatory update ref; frozen gold additionally demanded the owner class without a stage-2 owner rule. |
| v2 R4 | MIXED | Defensible `binding_required` interpretation plus an evidence-ref protocol failure; the empty applicability gold uses a narrower relation than “genuinely apply”. |
| v3 R1 | SEMANTIC_PASS | Exact 3/3 under the frozen v3 gold. |
| v3 R2 | SEMANTIC_PASS | Exact 3/3 under the frozen v3 gold. |
| v3 R3 | SEMANTIC_PASS | Exact 3/3 under the frozen v3 gold, with mandatory update supplied. |
| v3 R4 | TEST_EXPECTATION_INCORRECT | Exact output shape and supplied refs, but the expected empty set is incompatible with the prompt's broad belonging relation; it is not a clear model semantic failure. |

## 7. What the evidence proves about local-primary

The previous broad “Gemma capability ceiling” conclusion is **not supported** for technical subset selection. Local-primary selected the v3 R1–R3 subsets exactly in all repetitions and made a reasonable R4 approval-participation selection under the language it received.

There is narrower negative evidence: v1 did not reliably satisfy the added role-classification contract, v1 and v2 produced protocol-invalid structures in R4, and v3 did not infer the unstated direct-operation-only restriction. None of these is a clean failure of a single, unambiguous technical-binding semantic relation.

## 8. The precise relationship ATHBA needs

ATHBA must first name the consumer contract. At the existing planning boundary, the likely useful relationship is **MODIFY_TARGET**: a supplied repository method or owner that is expected to require a change to make the behavioral requirement true. It must be defined with a repository fact that distinguishes a mere trigger/participant from a modification location.

This cannot be inferred safely from names alone. It must remain distinct from:

- **MUST_PRESERVE_INTERFACE** — an inherited or external technical identity that must remain present;
- **EXECUTION_PARTICIPANT** — code participating when the behavior occurs;
- **TRIGGERED_BY** — code/event that causes the behavior to occur;
- **OBSERVED_THROUGH** — a read/API surface that demonstrates the behavior;
- **IMPLEMENTED_BY** — code already directly providing the behavior; and
- **DEPENDS_ON** — an element required by the behavior path.

If the downstream consumer instead needs execution-path planning, it should request `EXECUTION_PARTICIPANT` explicitly and R4 approve should be included. It must not call either relationship merely “binding”.

## 9. Is technical binding overloaded?

Yes. The fixtures and prompts conflate at least ownership, implementation, modification target, trigger, participant, observation surface, dependency, and preservation constraint. This explains why R1 can require two path methods, R2 can require a retrieval method, R3 can be forced by inheritance, and R4 can still be labelled a negative despite an approval trigger.

## 10. Valid negative cases and recommended next experiment

A valid negative for **MODIFY_TARGET** or **EXECUTION_PARTICIPANT** must supply candidates with no credible connection to the behavior. For example, under an explicitly named `EXECUTION_PARTICIPANT` relation:

```text
Behavior: An existing customer can be found using their customer identifier.
Candidates:
- SignalBoard.publish
- ReservationBook.cancel
Expected: []
```

Neither candidate retrieves a customer, triggers customer lookup, observes its result, nor is a plausible path participant. This is unlike R4, whose `ApprovalService.approve` is textually tied to the stated trigger.

Recommended next experiment (analysis only): write a short contract that selects exactly one named relation, supplies only the evidence necessary for that relation, includes both positive and genuinely unrelated negatives, and keeps owner expansion and inherited preservation deterministic. Do not reuse R4 as a negative unless the contract explicitly says direct implementation or authorized modification target and supplies the facts needed to establish that restriction.
