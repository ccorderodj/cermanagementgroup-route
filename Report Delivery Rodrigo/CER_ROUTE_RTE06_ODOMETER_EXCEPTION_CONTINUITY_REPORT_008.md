# CER Route — Temporary Odometer Exception Continuity

**Report 008** · branch `feature/rte06-odometer-exception-autoapproval` ·
2026-10-02

Option B as CER approved it. Implemented strictly within the authorised scope;
nothing on the "do not change" list was touched.

---

## 1. Current behaviour (before this delta)

The supervisor taps *"I can't take a photo"*, picks one of four closed reasons
and optionally adds a note. That creates a request in `requested` and leaves the
evidence in `exception_requested`.

**The day then waits** for someone holding `route.records.adjust` to approve it.
Once approved, the supervisor types the reading and it lands as
`manual_exception_confirmed` with method `manual_no_photo`.

---

## 2. Chosen temporary mechanism

A single new capability, deliberately narrow:

```text
route.odometer.selfapprove
```

When the caller holds it, the exception they request for **their own** work
session is approved in the same transaction that creates it. Nothing else
changes.

| | |
|---|---|
What it grants | Only that the requester's own odometer exception skips the wait |
What it does **not** grant | Reviewing or deciding anyone else's exception, the admin queue, or anything `route.records.adjust` carries |
Scope | Per company and per role, by construction — roles belong to a tenant |
Default | **Not seeded to any role.** Installing this code changes nobody's behaviour |
START / END | Both |

### How it is represented, and why

- **`decided_by` stays NULL**, `decided_at` is set. There was no person.
  Recording the supervisor would say they approved themselves; recording an
  admin would invent one. The column was already nullable, and "decided without
  a decider" is exactly what happened.
- **Audit emits a second event with its own action**, `auto_approve`, whose
  summary names the capability it acted under. Reusing `approve` would make an
  automatic decision indistinguishable from a person's the moment anyone read
  the trail — which is the condition CER attached to accepting `decided_by =
  NULL`.
- **The exception stays an exception.** Same closed reason, same requester,
  same timestamps, and the reading still enters as `manual_no_photo`.
- **Nothing is fabricated.** Approval opens the door; it does not walk through
  it. Until the supervisor types a reading, `confirmed_reading` and
  `captured_at` are both null — asserted in the tests.

### Changed files

| File | Change |
|---|---|
`app/core/rbac/catalog.py` | The capability, with its rationale and the note that it is not seeded to any role |
`app/routers_api/odometer/router.py` | `has_permissions([...])` reports whether the caller holds it; the decision is the server's, nothing about it comes from the request body |
`app/routers_api/odometer/service.py` | `request_exception(..., auto_approve)` applies the approval inside the same transaction and records the distinct audit event |

**No frontend change.** The screens already had the `exception_approved` state,
because that is what admin approval produced — the banner already reads
*"Odometer ready to enter"* and the capture screen already offers the reading
field. Auto-approval produces that same state, so the interface works unchanged.
No new UX, as CER required.

No migration, no change to Work Session or Trip states, to the normal photo
path, to OCR, or to any existing capability.

---

## 3. Evidence

`tests/integration/test_odometer_exception_autoapproval.py`

| CER's required validation | Test | Result |
|---|---|---|
With the capability → auto-approval works | `test_con_la_capacidad_la_excepcion_se_autoaprueba` | passed |
START works | same, parametrized `start` | passed |
END works | same, parametrized `end` | passed |
Without it → still requires Admin | `test_sin_la_capacidad_sigue_esperando_al_administrador` | passed |
Audit distinguishes automatic from human | `test_la_auditoria_distingue_la_automatica_de_la_humana` | passed |
Exception remains `manual_no_photo` | `test_la_lectura_sigue_entrando_como_manual_sin_foto` | passed |
Removing the capability restores prior behaviour | `test_retirar_la_capacidad_restaura_el_flujo_anterior` | passed |

```
6 passed in 12.74s     exit 0
```

These tests discriminate without needing a mutation run: the suite exercises
**both** states of the same switch. If auto-approval did not work, the first
would fail; if it were always on, the second and the last would.

### Regression

| Area | Result |
|---|---|
Odometer flow, END work behaviour, exception flow, maker-checker, role authority | **76 passed, exit 0** (1 min 24 s) |
Capability catalogue + public surface nets | **21 passed, exit 0** |
Typecheck / lint / build | `NOT APPLICABLE` — no frontend file changed in this delta |

Nothing was weakened, skipped, xfailed or removed.

---

## 4. Rollback / deactivation

**Revoke the capability from the role.** Nothing else — no deployment, no code
change, no migration.

The next exception requested by that role goes back to `requested` and waits for
an admin, which is the pre-existing flow. This is exercised by
`test_retirar_la_capacidad_restaura_el_flujo_anterior`: it grants, confirms
auto-approval, revokes, and confirms the very next request waits again.

Exceptions already auto-approved before the revocation stay as they are — they
are facts that happened, and the audit says how. They remain distinguishable
forever by `decided_by IS NULL` together with the `auto_approve` audit event.

### Operational action required to activate

The local work does **not** turn anything on. In each environment:

1. `uv run python -m app.db.scripts.bootstrap` — seeds the new capability into
   the `permission` table. It is idempotent and does not touch existing grants.
2. Grant `route.odometer.selfapprove` to the **supervisor** role **in the CER
   tenant only**, from the roles and permissions screen. That grant goes through
   the existing change-approval path, so the activation is audited too.

Until step 2 happens, behaviour is identical to today everywhere.

### One thing worth knowing

`has_permissions` returns true for platform superusers, as it does for every
capability. A platform administrator acting inside a tenant would therefore also
auto-approve. That is pre-existing platform-privilege behaviour, not a widening
introduced here, and `Users.is_superuser` remains outside the tenant capability
model.

---

## 5. Status

```text
COMPLETE — temporary measure in place, OFF until granted
```

Scope limit respected: no change to the normal photo + confirmed-reading flow,
the general approval model, existing administrative capabilities, Work Session
or Trip states, OCR, other roles, other tenants, or RTE07.
