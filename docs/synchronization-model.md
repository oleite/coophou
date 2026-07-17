# Synchronization model

This document defines the conceptual model that coophou implementations should preserve.

## Goal

For every supported operation, clients that begin from a compatible checkpoint and successfully consume the same canonical operation sequence should converge to equivalent synchronized state.

This guarantee requires more than broadcasting callbacks. It requires identity, ordering, idempotency, dependency handling, and recovery.

## Terms

See [glossary.md](glossary.md) for canonical definitions.

The most important distinction is:

- a **Houdini event** is an observation emitted by the DCC;
- an **operation** is a validated semantic collaborative edit;
- a **message** is a transport envelope;
- an **accepted operation** is an operation assigned canonical session order.

Do not serialize raw callback arguments as the protocol contract.

## Operation requirements

## Transaction requirements

Several Houdini gestures produce many callbacks but represent one user intent.

A canonical transaction contains:

- stable `transaction_id`;
- author and session;
- one or more ordered operations;
- optional user-facing label;
- local observation range;
- atomic acceptance result;
- canonical sequence range or one transaction sequence;
- capability requirements.

Examples:

- paste subtree;
- delete subtree;
- one undo/redo action;
- one coalesced node drag;
- one parameter gesture.

The authority accepts or rejects a transaction as a unit.

Clients should pre-validate every operation. If local application fails halfway through a transaction, do not pretend the transaction was atomic: block sequence advancement and reconcile.

Every operation should define:

- stable `operation_id`;
- `operation_type`;
- authoring `client_id`;
- collaborative `session_id`;
- target `entity_ref`;
- payload;
- schema version or protocol version;
- preconditions when necessary;
- dependencies when necessary;
- canonical sequence after acceptance;
- diagnostic last-known path;
- deterministic apply semantics;
- idempotent replay behavior;
- failure classification.

Timestamps may aid diagnostics. They must not decide canonical order by themselves.

## Stable entity identity

### Why paths are insufficient

A Houdini path can change because of:

- rename;
- reparenting;
- deletion;
- recreation at the same path;
- copy and paste;
- namespace or subnet changes;
- asset instantiation.

An operation that only carries `/obj/geo1/node1` can affect the wrong node after path reuse.

### Entity reference shape

A conceptual entity reference may contain:

```json
{
  "entity_id": "stable-coophou-id",
  "entity_kind": "node",
  "last_known_path": "/obj/geo1/node1",
  "parent_entity_id": "optional-parent-id"
}
```

`entity_id` is authoritative. `last_known_path` is diagnostic or a constrained lookup hint.

### Resolution rules

A resolver should return a typed result:

- `FOUND_EXACT`;
- `NOT_FOUND`;
- `DELETED`;
- `AMBIGUOUS`;
- `IDENTITY_MISMATCH`;
- `UNSUPPORTED_KIND`.

Never fall back silently from identity mismatch to a same-named path.

### Copy and duplication

The project must choose and document whether copied Houdini objects:

- receive new collaborative IDs immediately;
- preserve IDs until capture detects collision;
- are unsupported until normalized.

Duplicate IDs must never remain authoritative for two live entities in one collaborative state.

## Canonical order

The session authority assigns a monotonically increasing sequence to accepted operations.

Conceptually:

```text
accepted[1], accepted[2], accepted[3], ...
```

Clients track at least:

- `last_received_sequence`;
- `last_applied_sequence`;
- `last_confirmed_sequence`;
- pending local operation IDs.

These may collapse in a simpler implementation, but a gap must remain detectable.

### Sequence handling

When receiving canonical sequence `N`:

- if `N == last_applied + 1`, it is eligible for normal processing;
- if `N <= last_applied`, treat it as duplicate or replay and verify operation identity;
- if `N > last_applied + 1`, enter catch-up or degraded state and request missing history;
- if the same sequence maps to a different operation ID, treat it as protocol corruption or authority inconsistency.

Do not apply later operations across a known gap unless the protocol explicitly proves they are independent and the recovery design supports it.

## Local optimistic lifecycle

A local Houdini edit is already visible before network confirmation. coophou therefore needs an explicit optimistic model.

Recommended conceptual flow:

```text
Houdini edit
  → callback observation
  → normalized operation
  → local pending record
  → send
  → accepted/rejected
  → canonical confirmation
```

A pending record should preserve:

- operation ID;
- captured pre-state or inverse information when needed;
- local observation order;
- affected entity IDs;
- send attempts;
- server result;
- canonical sequence when accepted.

### Confirmation

When the canonical stream returns the client's own operation:

- match by operation ID, not by payload resemblance;
- do not apply it twice if the local edit already produced equivalent state;
- validate that canonical placement does not require rebase or replay;
- advance confirmation state only after local state is consistent.

### Rejection

A rejected optimistic operation requires one documented action:

- local rollback through a proven inverse;
- restore checkpoint and replay accepted history;
- authoritative snapshot reconciliation;
- visible fatal divergence requiring user action.

“Log and continue” is not sufficient if the local scene still contains the rejected edit.

## Remote application lifecycle

Recommended flow:

1. Decode and validate the envelope.
2. Validate operation schema and supported type.
3. Verify session and canonical sequence.
4. Detect duplicates and gaps.
5. Resolve dependencies.
6. Schedule application on Houdini's main thread.
7. Enter remote-apply suppression.
8. Resolve entity references.
9. Check operation preconditions.
10. Apply deterministically.
11. Record the operation ID and sequence.
12. Exit suppression in `finally`/context-manager cleanup.
13. emit diagnostics and health transitions.

Application and acknowledgement order must be explicit. Do not acknowledge successful local application before it actually succeeds.

## Callback echo suppression

A remote operation may generate Houdini callbacks. Those callbacks must not produce a second collaborative operation.

Use a scoped context carrying at least:

- suppression depth;
- currently applying operation ID;
- affected entity IDs when useful;
- connection/session generation.

A nesting-safe conceptual interface:

```python
with remote_apply_context(operation_id, entity_ids):
    result = apply_operation(operation)
```

A single global Boolean fails when:

- operations nest;
- callbacks are asynchronous;
- exceptions leave the flag set;
- two sessions or scene generations overlap.

Suppression should ignore only expected echoes. It should not hide unrelated local edits that happen during a long operation.

## Idempotency

Each operation type needs an explicit replay rule.

Examples:

### Create node

Replay succeeds when the entity ID already resolves to a compatible node created by the same logical operation. It fails on identity collision or incompatible type.

### Delete node

Replay is a no-op when the entity is already authoritatively deleted. It must not delete a new node that reused the old path.

### Set parameter

Replay is a no-op when the same target property already has the intended semantic value. Expression language, keyframes, raw values, and evaluated values must not be conflated.

### Connect nodes

Replay is a no-op when the exact logical endpoints and input index are already connected. It fails if the index is occupied by an incompatible canonical connection unless conflict policy says otherwise.

## Dependencies and preconditions

Operations may depend on:

- entity creation;
- parent existence;
- parameter schema;
- prior disconnect;
- digital asset definition;
- multiparm instance creation;
- canonical sequence.

Represent dependencies explicitly where canonical sequence alone is insufficient.

Classify an unmet condition as:

- **deferred**: likely resolvable after missing accepted operations arrive;
- **rejected**: operation is invalid for canonical state;
- **reconciliation required**: local state may be divergent;
- **fatal**: state or protocol cannot be trusted.

Bound deferred queues by count, age, and sequence range.

## Coalescing

## Durable operations versus transient previews

Durable operations:

- enter canonical history;
- require identity and schema validation;
- are replayed and recovered;
- must be idempotent.

Transient previews:

- use the presence channel;
- may be dropped;
- expire;
- never advance canonical state;
- never repair scene state;
- never dirty the `.hip`.

A node-drag preview may animate a remote ghost, but the final node position still requires a durable operation.

High-frequency Houdini events may be coalesced only when semantics are preserved.

Safe candidates may include intermediate UI drag values for the same scalar parameter, if the product explicitly wants final-value collaboration.

Unsafe coalescing may include:

- create then delete when another operation references the entity;
- disconnect then reconnect with changed input order;
- expression edits collapsed into evaluated values;
- operations crossing undo boundaries;
- operations from different authors after canonical acceptance.

Coalescing should happen before canonical acceptance or through an explicitly designed protocol feature.

## Determinism

Operation application should not depend on:

- dictionary iteration order across unsupported runtimes;
- local selection;
- active network editor;
- viewport state;
- current node;
- local time;
- random IDs generated during replay;
- environment-dependent defaults;
- implicit Houdini naming when the resulting name is part of synchronized state.

Capture or negotiate any value that affects collaborative state.

## Supported-state contract

For each operation type document:

1. Captured Houdini source.
2. Plain-data payload.
3. Stable target identity.
4. Preconditions.
5. Apply algorithm.
6. Replay behavior.
7. Conflict behavior.
8. Undo behavior.
9. Recovery behavior.
10. Tests.

An operation type is not complete until this contract exists.
