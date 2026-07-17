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

The fake adapter must not attempt to recreate all of Houdini. It exists to test operation contracts and state machines without a license or GUI.

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
