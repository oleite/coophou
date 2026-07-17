# Recovery and conflict handling

Normal streaming is only one part of collaboration. coophou must define what happens when assumptions fail.

## Recovery principles

## User experience during recovery

Routine transport loss should be non-modal.

The panel must state:

- whether local editing is still allowed;
- whether new edits are queued, local-only, or blocked;
- whether work has been preserved;
- what coophou is doing;
- which action is recommended.

Before replacing the local scene or installing a snapshot, preserve a local recovery artifact when possible and obtain an explicit user action unless session policy has already authorized automatic repair.

1. Never hide divergence.
2. Prefer deterministic repair over best-effort guessing.
3. Retry only failures that are safe and plausibly transient.
4. Keep recovery bounded.
5. Preserve user work or create a safe recovery artifact before destructive repair.
6. Separate transport reconnect from scene reconciliation.
7. A client may remain connected while requiring recovery.

## Failure classification

Classify failures before choosing an action.

### Duplicate

The operation ID was already processed.

Action:

- verify the duplicate matches the same canonical operation;
- no-op safely;
- retain diagnostics.

A conflicting payload with the same ID is protocol corruption, not a harmless duplicate.

### Sequence gap

A canonical sequence is missing.

Action:

- stop normal advancement;
- request missing history;
- enter `CATCHING_UP` or `DEGRADED`;
- bound buffering of later messages.

### Missing dependency

A required earlier entity or schema is unavailable.

Action:

- defer only if missing history can plausibly resolve it;
- record dependency and deadline;
- request history if appropriate;
- reconcile when bounded deferral expires.

### Precondition failure

The target exists but does not match the operation's expected state.

Action depends on conflict policy:

- reject;
- apply canonical overwrite;
- roll back and replay;
- reconcile from snapshot.

Never retarget to a similar object.

### Unsupported application

The protocol operation is valid, but the current Houdini version or scene context cannot apply it.

Action:

- mark client incompatible or degraded;
- do not acknowledge successful application;
- require upgrade, exclusion, or reconciliation.

### Internal exception

Unexpected code failure.

Action:

- capture diagnostic context;
- stop advancing confirmed sequence;
- attempt only a proven safe retry;
- otherwise reconcile or enter fatal state.

## Reconnect flow

Recommended conceptual sequence:

1. Transport disconnects.
2. Client freezes or records new local operations according to explicit offline policy.
3. A new connection generation begins.
4. Client joins the same session with last confirmed sequence and pending operation IDs.
5. Authority returns missing history or snapshot requirement.
6. Client applies missing accepted operations in canonical order.
7. Pending local operations are matched, resent with original IDs, rebased, rejected, or recovered.
8. Client verifies no gaps and no unresolved application failures.
9. Synchronization state becomes `SYNCHRONIZED`.

Do not reset sequence counters or operation IDs during reconnect.

## Offline local edits

The product must choose one policy.

### Disallow edits while disconnected

Simplest correctness model. UI should clearly lock or pause collaboration capture.

### Allow and queue edits

Better continuity, but requires:

- preserved local ordering;
- pre-state/inverse data;
- rebase against missed canonical operations;
- conflict policy;
- bounded queue;
- clear UI showing unconfirmed work.

### Fork session

Disconnected edits create a new branch/session to merge later.

Powerful but significantly more complex.

The current choice must be explicit. Do not accidentally allow offline edits because callbacks continue firing.

## Optimistic rollback strategies

### Inverse operation

Apply a captured inverse.

Suitable when:

- inverse is well-defined;
- no later dependent operations make it unsafe;
- Houdini mutation is deterministic.

Risks:

- deletion restoration;
- generated names;
- asset definitions;
- expressions/keyframes;
- side effects not represented in operation state.

### Checkpoint plus replay

Restore a local checkpoint, then replay accepted canonical history and still-valid local pending operations.

Suitable when:

- checkpoints are cheap enough;
- replay is deterministic;
- all supported state is represented.

### Authoritative snapshot

Install a snapshot from the authority, then replay after its checkpoint.

Suitable when:

- history is unavailable;
- local state is deeply divergent;
- operation-by-operation repair is unsafe.

### User-assisted recovery

Preserve local work, disconnect from collaboration, and ask the user to choose a new session or export changes.

Necessary when automatic recovery cannot be trusted.

## Checkpoints

A recovery checkpoint should bind:

- session ID;
- canonical sequence;
- protocol version;
- Houdini version;
- snapshot identifier or local artifact;
- integrity hash when possible;
- creation time for diagnostics;
- scene generation.

A checkpoint without sequence metadata is insufficient for deterministic replay.

## Snapshot authority

Choose who may author an authoritative snapshot:

- server from a canonical scene service;
- designated host client;
- elected healthy client;
- session creator.

If a client supplies snapshots, define:

- eligibility;
- integrity verification;
- sequence consistency;
- malicious or stale snapshot handling;
- transfer security.

Do not accept whichever snapshot arrives first.

## Concurrent edit conflicts

Conflict policy should be per operation family.

### Scalar parameter values

A simple initial policy is canonical last-writer-wins by accepted sequence.

This is deterministic but may overwrite an artist's recent local optimistic value. UI may need to surface the overwrite.

### Expressions and keyframes

Treat as structured state. Do not reduce to evaluated scalar values.

A canonical overwrite may be acceptable initially, but payload must preserve expression/keyframe semantics.

### Node rename

Canonical order can decide the final name. Name collisions require the authority or application contract to define the exact canonical resulting name.

### Delete versus edit

Deletion should normally dominate later edits targeting the deleted entity unless those edits were canonically ordered before deletion.

Do not apply a later edit to a new node at the reused path.

### Connect versus disconnect

Use exact endpoints, input index, and canonical order. Detect incompatible occupancy instead of silently replacing unless replacement is the documented rule.

### Concurrent structural edits

Operations such as subnet movement, digital asset edits, multiparm schema changes, or parent deletion may require reconciliation rather than naive last-writer-wins.

Start with a narrow supported surface.

## Rebase of pending local operations

When remote accepted operations arrive before a local pending operation's canonical position, determine whether the local operation remains valid.

Possible outcomes:

- unchanged and still valid;
- payload can be deterministically transformed;
- precondition fails and operation is rejected;
- rollback/replay is required;
- full reconciliation is required.

Transform logic must be operation-specific and tested. Do not build a generic “fix paths and retry” rebase.

## Recovery state machine

Recommended states:

```text
HEALTHY
  → GAP_DETECTED
  → FETCHING_HISTORY
  → REPLAYING
  → HEALTHY
```

Alternative paths:

```text
REPLAYING → SNAPSHOT_REQUIRED
SNAPSHOT_REQUIRED → INSTALLING_SNAPSHOT
INSTALLING_SNAPSHOT → REPLAYING | FATAL
GAP_DETECTED → FATAL
APPLICATION_FAILED → RECONCILIATION_REQUIRED
RECONCILIATION_REQUIRED → REPLAYING | INSTALLING_SNAPSHOT | USER_ACTION | FATAL
```

Every state needs:

- entry reason;
- allowed user actions;
- allowed network processing;
- timeout or bound;
- exit conditions;
- logging.

## Data preservation

Before destructive reconciliation:

- preserve the artist's current work to a uniquely named local recovery artifact when possible;
- do not overwrite the current working path;
- record operation and sequence context;
- tell the user where recovery data was stored;
- avoid sharing that path remotely.

Recovery artifacts need a cleanup and privacy policy.

## Fatal state

Enter a visible fatal state when:

- sequence history contradicts itself;
- stable identity cannot be trusted;
- snapshot integrity fails;
- application repeatedly fails after a proven recovery path;
- protocol versions are incompatible;
- local state cannot be preserved safely.

Fatal means collaboration stops. It does not mean Houdini should crash or discard artist work.
