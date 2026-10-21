# EXECUTION PROGRESS & REPORTING

The following rules complement the existing project instructions.

They do not replace existing architecture, testing, database, security, Git, or Definition of Done rules.

Their purpose is to provide continuous visibility during substantial implementations, migrations, regression testing, builds, and validation work.

---

## 1. CONTINUOUS EXECUTION VISIBILITY

For substantial or long-running tasks, do not wait until the end to report execution status.

Provide concise progress reports whenever a meaningful milestone occurs, including:

- a major implementation phase completes;
- a test batch completes;
- a long-running operation starts or finishes;
- a migration completes;
- a build completes;
- browser validation completes;
- an unexpected problem is discovered;
- an unexpected problem is corrected;
- a test or validation step fails;
- human intervention becomes necessary;
- the task changes from implementation to validation;
- final validation begins.

Do not report every small command.

Report meaningful execution milestones only.

---

## 2. REQUIRED EXECUTION STATE

Throughout substantial work, maintain enough verified information to answer:

- What has been completed?
- What has been validated?
- What is currently running?
- What remains?
- What problems have been discovered?
- What requires human attention?

Do not rely on memory alone when exact command output or test results are available.

Do not invent metrics.

---

## 3. PROGRESS REPORT FORMAT

Use concise status updates such as:

```
## Execution Status

**Progress:** 7/10 regression batches

**Completed:**
- unit
- access
- tenant
- clients
- operations
- orders

**Running:**
- personnel

**Remaining:**
- onboarding
- review
- platform

**Accumulated results:**
- Tests executed: 776
- Failed: 0

**Findings:**
- No new findings.

**Human intervention:**
- None.
```

Adapt the report to the task rather than mechanically including empty sections.

The most important information should be immediately visible:

- DONE
- RUNNING
- REMAINING
- RISKS / FINDINGS

---

## 4. REGRESSION BATCH TRACKING

When a regression suite is large, divide it into logical batches when doing so is compatible with the project's existing test architecture.

Execute batches sequentially when this improves observability and failure isolation.

For every batch record:

- batch name;
- number of tests;
- result;
- exit code when available;
- duration.

Maintain a cumulative ledger.

Example:

| Batch | Tests | Result | Duration |
|---|---:|---|---:|
| unit | 209 | exit 0 | 42 s |
| access | 139 | exit 0 | 7:36 |
| tenant | 79 | exit 0 | 2:57 |
| clients | 55 | exit 0 | 3:28 |
| operations | 143 | exit 0 | 15:23 |
| orders | 151 | exit 0 | 38:13 |

After each completed batch, report:

- completed batch;
- batch result;
- batch duration;
- cumulative test count;
- cumulative failures;
- currently running batch;
- remaining batches.

Example:

> Regression is running sequentially and has completed 6 of 10 batches.
>
> All completed batches exited 0. 776 tests have been executed so far.
>
> `personnel` is currently running. `onboarding`, `review`, and `platform` remain.

---

## 5. ACCEPTANCE CRITERIA TRACKING

When the task defines acceptance criteria or implementation identifiers such as `AC-01`, `AC-02`, `AC-18` or `FC-RATE-1`, `FC-RATE-2`, `FC-RATE-3`, track their execution state explicitly.

Use:

- `PENDING`
- `IN PROGRESS`
- `IMPLEMENTED`
- `VALIDATED`
- `BLOCKED`

**Do not treat `IMPLEMENTED` and `VALIDATED` as equivalent.**

A criterion becomes `VALIDATED` only when appropriate evidence exists. Examples of evidence:

- focused automated tests;
- regression tests;
- API verification;
- database verification;
- permission verification;
- migration verification;
- static analysis;
- successful build;
- browser validation.

Maintain evidence alongside status when practical.

Example:

| Criterion | Status | Evidence |
|---|---|---|
| FC-RATE-1 | VALIDATED | model + migration + tests |
| FC-RATE-2 | VALIDATED | API + permissions + tests |
| FC-RATE-3 | IMPLEMENTED | browser validation pending |

---

## 6. VALIDATION EVIDENCE

Record concrete validation results instead of using vague statements.

Prefer:

```
Focused tests: 24/24 PASS
TypeScript: 0 errors
ESLint: 0 errors
Regression: 776 executed, 0 failures so far
Build: PASS
Browser validation: PENDING
```

Avoid statements such as:

- Everything looks good.
- Tests seem fine.
- It should work.
- Almost finished.

If something has not been executed, explicitly use `PENDING`, `NOT RUN` or `NOT APPLICABLE`.

**Never convert missing evidence into PASS.**

---

## 7. MIGRATION EVIDENCE

When the task involves schema or data migrations, include migration evidence in progress and final reports.

When applicable, record:

- migration/revision identifier;
- migration execution result;
- current migration head;
- number of migration heads;
- records evaluated;
- records modified;
- records skipped;
- records requiring human review;
- ambiguous values encountered.

Example:

```
Migration: 59de4e2ff04d
Result: PASS
Alembic heads: 1

75 orders evaluated
68 initialized from baseline
3 require human confirmation
0 free-text values automatically interpreted
```

**Never silently interpret ambiguous business data merely to complete a migration.**

Report it for human review when appropriate.

---

## 8. UNEXPECTED FINDINGS

During implementation and validation, report meaningful problems discovered outside the immediate expected change.

Do not hide incidental findings inside the final summary.

For each significant finding document:

- **Problem** — what was discovered.
- **Impact** — what behavior or users were affected.
- **Cause** — one of `CONFIRMED`, `LIKELY`, `UNVERIFIED`. Do not present assumptions as confirmed facts.
- **Correction** — what was changed.
- **Operational action** — anything that must also happen elsewhere: execute bootstrap; run migration; update configuration; seed permissions; deploy changes; manually review records; update another environment.

Example:

> `jobopenings.viewpayrate` existed in the application capability definitions but was not seeded in the development database.
>
> As a result, users could not see pay rates even though the UI supported them.
>
> The bootstrap was executed and `viewpayrate` and `updatepayrate` are now present for the intended roles.
>
> Operational action: the same bootstrap must be executed in the shared environment. The local correction does not modify that environment.

---

## 9. HUMAN INTERVENTION

Keep human-review items separate from engineering failures. Examples include:

- ambiguous data;
- business-rule decisions;
- production approval;
- deployment approval;
- missing credentials;
- manual data confirmation;
- unavailable external dependencies.

Report them explicitly.

Example:

```
Human review required: 3 records
Engineering failures: 0
```

---

## 10. FAILURE REPORTING

Never hide a failed command, test, migration, build, or validation behind an overall success statement.

When something fails, report:

- WHAT FAILED
- WHY IT FAILED, if confirmed
- IMPACT
- ACTION TAKEN
- CURRENT STATUS

If the root cause is unknown, say so. Do not invent an explanation.

After correcting a failure, report **both**:

- that the original failure occurred;
- that the subsequent validation passed.

---

## 11. FINAL EXECUTION REPORT

At the end of substantial work, provide a consolidated execution report. Use the following structure when applicable:

```markdown
# Final Execution Report

## Status

**Result:** COMPLETED / COMPLETED WITH PENDING ITEMS / BLOCKED

**Scope:** [ticket / feature / AC / FC]

---

## Implementation

### [Feature / criterion]
- implemented change
- relevant technical details

---

## Acceptance Criteria

| Criterion | Status | Evidence |
|---|---|---|
| AC-01 | VALIDATED | ... |
| AC-02 | VALIDATED | ... |

---

## Regression

| Batch | Tests | Result | Duration |
|---|---:|---|---:|
| unit | ... | exit 0 | ... |
| access | ... | exit 0 | ... |

**Total tests:** X
**Failures:** X
**Result:** PASS / FAIL

---

## Technical Validation

- Focused tests: ...
- TypeScript: ...
- ESLint: ...
- Build: ...
- Migration: ...
- Database verification: ...
- Browser validation: ...

---

## Migration / Data Evidence

- Revision: ...
- Heads: ...
- Records evaluated: ...
- Records modified: ...
- Human review: ...

---

## Additional Findings

### Finding 1

**Problem:** ...

**Impact:** ...

**Cause:** CONFIRMED / LIKELY / UNVERIFIED

**Correction:** ...

**Operational action:** ...

---

## Remaining Work

- ...

---

## Git

**Commit:** `hash`
**Message:** `...`
**Push:** performed / not performed

---

## Next Step

State the natural next step without automatically starting work outside the current scope.
```

If nothing remains: *No known pending work remains inside the requested scope.*

Omit sections that genuinely do not apply.

**Never fabricate values simply to complete the template.**

---

## 12. COMPLETION REPORTING RULE

Do not report a substantial task as COMPLETED merely because implementation has finished.

Distinguish between:

- `IMPLEMENTATION COMPLETE`
- `VALIDATION IN PROGRESS`
- `FULLY VALIDATED`

If required validation remains, report `COMPLETED WITH PENDING VALIDATION`, or the equivalent status appropriate to the situation.

---

## 13. SCOPE BOUNDARY

Progress reporting does not authorize additional scope.

Once the requested feature, ticket, AC, or FC has been implemented and the required validation completed:

- provide the final execution report;
- identify any remaining operational action;
- identify the natural next step;
- stop.

Do not automatically begin another independent feature.

Example:

> FC-RATE is implemented and validated.
>
> No failures remain in the requested scope.
>
> Shared environment still requires the permission bootstrap.
>
> ERP06 was not started.

---

## 14. REPORTING QUALITY STANDARD

Execution reports must be:

- concise;
- factual;
- quantitative when possible;
- based on actual command/test output;
- explicit about failures;
- explicit about pending work;
- explicit about human intervention;
- clear about local versus shared/production environments.

At any point during substantial execution, the current status should make this immediately understandable:

**What is done → what passed → what is running → what remains → what was discovered → what needs attention.**
