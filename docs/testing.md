# Testing strategy

Synchronization code must be tested as a distributed state machine, not only as individual callback functions.

## Test layers

### 0. HDK/HOM event-probe fixtures

Before operation contract tests, capture real event traces from every supported Houdini build.

Store sanitized fixtures containing:

- scenario;
- adapter type;
- Houdini/build/platform;
- event sequence;
- null/bulk payload cases;
- undo/redo state;
- scene generation;
- expected transaction grouping.

An API symbol existing is not proof that a gesture can be normalized safely.

Current Phase-1 fixtures use:

```text
tests/fixtures/events/
  schema-v1.json
  houdini-21.0.729/hdk-api-21000693/windows/
    hom/<scenario>.jsonl
    hdk/<scenario>.jsonl
```

Run one fixture in a fresh Houdini process with:

```powershell
& "$env:HFS/bin/hython.exe" scripts/run_event_probe.py --adapter hom --scenario create_node
& "$env:HFS/bin/hython.exe" scripts/run_event_probe.py --adapter hdk --scenario create_node
```

Generate the side-by-side report with:

```powershell
python scripts/compare_event_traces.py <hom-fixture-dir> <hdk-fixture-dir> --output docs/event-probe-comparison.md
```

The pure fixture test validates required fields, adapter/scenario consistency, and strictly increasing local observation numbers.

### 1. Pure unit tests

Run without Houdini.

Cover:

- operation schema validation;
- serialization round trips;
- stable ID validation;
- duplicate detection;
- canonical sequence transitions;
- message framing;
- version compatibility;
- pending-operation state;
- retry policy;
- dependency queues;
- error classification;
- health-state transitions.

These tests should be fast and deterministic.

Phase 2 implements these tests in `test_core_models.py`,
`test_core_scene.py`, `test_core_authority_client.py`, and
`test_core_transport_convergence.py`. They run under standard-library
`unittest` in ordinary Python; no property-testing dependency was added.

### 2. Fake scene adapter

Implement a small in-memory model with the minimum semantics needed to test collaboration:

- entities with stable IDs;
- parent/child relationships;
- names and paths;
- parameters;
- connections;
- deletion and path reuse;
- rename;
- copy/duplicate;
- scene generation;
- apply suppression.

The implemented `FakeScene` intentionally models only the seven accepted
families. Transaction application is clone/apply/validate/swap, its semantic
snapshot is stable JSON-compatible data, and applied transaction replay memory
is bounded. It does not attempt to recreate Houdini cooking or UI state.

### 3. Transport simulation

Use an in-process or fake transport capable of:

- duplicate delivery;
- dropped messages;
- delayed delivery;
- reordered delivery;
- partial frames;
- reconnect;
- stale connection generation;
- server rejection;
- history truncation;
- backpressure.

Tests should control the scheduler or clock. Avoid real sleeps.

`DeterministicTransport` uses an explicit bounded event list with manual
deliver, drop, duplicate, and reorder controls. It creates no ports, threads,
clocks, or sleeps. Tests cover old connection generations, reconnect/resume,
queue overflow, unavailable retained history, and failures injected between
transaction operations.

### 4. Multi-client convergence tests

Create several fake clients and a fake or real session authority.

Assert that after consuming the same canonical history:

- synchronized state is equivalent;
- applied sequences match;
- no unresolved pending operations remain;
- duplicate application did not mutate state;
- entity identity remains stable across rename and path reuse.

Compare semantic state, not object identity or incidental dictionary order.

### 5. Houdini integration tests

When Houdini is available, verify the adapter against actual behavior.

Cover:

- callback registration and removal;
- callback events emitted by supported edits;
- main-thread application;
- remote echo suppression;
- scene generation changes;
- undo/redo policy;
- save/load persistence of entity IDs;
- copy/paste identity behavior;
- module reload;
- panel close and Houdini shutdown;
- temporary snapshot safety.

Keep the number of Houdini-dependent tests focused because they are slower and harder to run.

Phase 3 adds three concrete layers:

- `tests/test_native_adapter.cpp`: DSO capabilities, strict bridge schema,
  persistent identity, bounded queues, supported snapshot extraction, native
  apply/replay/echo classification, stale generation, and partial-failure
  evidence against real HDK nodes;
- `tests/test_houdini_adapter.py`: ordinary-Python bridge and orchestrator
  parsing, ID ownership, serialization, and native-snapshot normalization;
- `tests/houdini_phase3_contract.py`: fresh-`hython` capture and application
  contracts for every v1 family, with native snapshots compared against
  `FakeScene` in both directions.

Run the exact target suite with:

```powershell
$env:HFS = 'C:\Program Files\Side Effects Software\Houdini 21.0.729'
cmake -S . -B build
cmake --build build --config RelWithDebInfo
ctest --test-dir build -C RelWithDebInfo --output-on-failure
python -m unittest discover -s tests -p 'test_*.py' -v
& "$env:HFS\bin\hython.exe" tests/houdini_phase3_contract.py
```

`tests/houdini_phase3_benchmark.py` is a reproducible benchmark-style Houdini
integration test. It reports external JSON-bridge distributions plus native
callback-handler and extractor counters for 10/100/1000-node scans, a
1000-node callback burst, move/parameter coalescing, copy/delete, native
subtree apply/post-verification, and bridge state calls:

```powershell
& "$env:HFS\bin\hython.exe" tests/houdini_phase3_benchmark.py
```

The benchmark is also registered in CTest with a 120-second timeout. It has no
machine-specific latency pass threshold; regression review compares the JSON
measurements and the bounded-work invariants instead of making a noisy CI host
the product performance contract.

## Required scenario matrix

Also run the matrix through:

- HOM capture;
- HDK capture when available;
- native bridge absent/fallback;
- each supported Houdini API version;
- reduced-motion UI;
- presence disabled;
- three collaborators with stale presence;
- slow authority and high-latency connection;
- pane/network context changes while overlays are visible.

At minimum, maintain tests for:

1. Two clients edit different scalar parameters.
2. Two clients edit the same scalar parameter.
3. Create entity, then edit it.
4. Rename entity, then target it by stable ID.
5. Delete entity, then replay deletion.
6. Delete entity, recreate the old path, then receive an old edit.
7. Connect and disconnect the same endpoints.
8. Duplicate operation delivery.
9. Duplicate message with conflicting payload.
10. Canonical sequence gap.
11. Out-of-order delivery.
12. Disconnect and catch up.
13. Resend pending operation with original ID.
14. Server rejects optimistic local operation.
15. Missing dependency becomes available.
16. Missing dependency expires.
17. Remote apply raises an exception.
18. Suppression context exits after an exception.
19. Scene changes while remote work is queued.
20. Repeated initialize/disconnect/reload does not duplicate callbacks.
21. Snapshot checkpoint plus replay.
22. Snapshot integrity or compatibility failure.
23. Bounded queue overflow.
24. Incompatible protocol or operation schema version.

## Operation contract tests

Every operation type should have a reusable contract test suite.

### Capture

- correct callback becomes correct semantic operation;
- unsupported callback is ignored or rejected explicitly;
- before-state is captured when required;
- no live Houdini object leaks into payload.

### Validate

- valid payload accepted;
- required fields enforced;
- bounds enforced;
- unknown required version rejected.

### Apply

- fresh application produces expected state;
- replay is safe;
- wrong identity fails;
- missing dependency is classified;
- precondition failure follows policy.

### Recover

- inverse or replay behavior works;
- operation remains traceable in logs;
- failure does not advance confirmed sequence.

## Property-based testing

Property-based tests are particularly useful for pure models.

Candidate properties:

- serialize/deserialize preserves operation semantics;
- applying an idempotent operation twice equals applying once;
- canonical sequence never decreases;
- a client cannot become synchronized with a known gap;
- retry never changes operation ID;
- deleting an entity prevents an old operation from targeting path reuse;
- suppression depth returns to its prior value after any exception;
- bounded queues never exceed configured limits.

Use generated operation sequences on the fake scene model.

## Deterministic scheduling

Concurrency tests should use a controllable scheduler where possible.

Avoid tests that depend on:

- arbitrary `sleep`;
- machine speed;
- race probability;
- real network timing;
- UI focus.

Expose explicit hooks or queues so a test can advance:

- message receive;
- canonical acceptance;
- main-thread apply;
- acknowledgement;
- reconnect.

## Fault injection

Provide fault points at layer boundaries:

- fail send before bytes written;
- fail after send before acknowledgement;
- duplicate accepted response;
- disconnect after canonical acceptance;
- fail entity resolution;
- fail halfway through a multi-step apply;
- fail checkpoint creation;
- corrupt snapshot metadata;
- exhaust history retention;
- close scene during replay.

Fault injection should be opt-in and deterministic.

## Test naming

Name tests by behavior and failure mode.

Good:

```text
test_old_parameter_edit_does_not_target_node_that_reused_deleted_path
test_reconnect_resends_pending_operation_with_same_id
test_remote_apply_context_restores_suppression_depth_after_exception
```

Weak:

```text
test_sync_2
test_node_stuff
```

## Regression policy

Every synchronization bug fix must add the smallest test that would have prevented the bug.

The test should fail for the original reason, not because of unrelated implementation details.

## Manual verification checklist

## UX test checklist

- local edit latency feels identical with collaboration on and off;
- cursor/selection presence never changes scene dirty state;
- activity items are grouped by gesture/transaction;
- remote edit pulses do not obscure node names or wires;
- leaving removes overlays and callbacks;
- reconnect uses no routine modal;
- follow mode stops immediately;
- colors have text/icon alternatives;
- failed recovery gives a plain explanation and preserves work;
- a 30-minute session does not leak callbacks, timers, native interests, or overlay shapes.

For releases or major adapter changes:

- start two Houdini sessions;
- join the same collaboration session;
- perform each supported operation;
- disconnect one client;
- make accepted edits;
- reconnect and catch up;
- trigger at least one conflict;
- verify UI state transitions;
- reload Python modules;
- open another `.hip`;
- disconnect and close Houdini;
- inspect logs for leaks, duplicate callbacks, and false synchronized status.

Record Houdini version, operating system, and protocol version.
