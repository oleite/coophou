# coophou architecture

This document describes the intended system shape and the rules for evolving it. It is an architectural guide, not a claim that every component already exists.

## Status vocabulary

Every durable architectural statement should use one of these statuses when ambiguity matters:

- **Current**: verified in the repository.
- **Required**: an invariant new work must preserve.
- **Proposed**: a target design that may not yet be implemented.
- **Experimental**: implemented or explored, but not yet a stable contract.
- **Deprecated**: still present, but new code must not depend on it.
- **Unknown**: needs repository or runtime verification.

Update [docs/current-state.md](docs/current-state.md) when a proposed or unknown item becomes verified.

## System context

coophou sits between several independently failure-prone systems:

```text
Artist input
    ↓
Houdini scene and UI
    ↓
Local change capture
    ↓
Normalized operation model
    ↓
Client session and transport
    ↓
Canonical session authority
    ↓
Other client sessions
    ↓
Main-thread remote application
    ↓
Other Houdini scenes
```

A correct design must account for:

- Houdini callbacks that may be noisy, incomplete, or reentrant;
- mutable node paths;
- local edits that are already visible before server confirmation;
- duplicate, delayed, missing, or reordered network messages;
- clients disconnecting at any point;
- an interactive UI that must remain responsive;
- scene states that can no longer be repaired operation-by-operation.

## Architectural objective

### Phase 2 implemented boundary

`coophou/core/` is the Houdini-independent reference collaboration core. Its
dependency direction is models/errors → fake scene → authority/client → fake
transport. It imports no Houdini, Qt, HDK/native binding, socket, or legacy
relay module and creates no runtime singleton.

The implemented authority owns an abstract supported-state projection per
session and assigns one canonical sequence per atomic transaction. Each client
owns separate confirmed and optimistic projections. These remain the portable
reference semantics. Phase 3 now supplies one real single-process Houdini
adapter; no real network authority exists.

### Phase 3 implemented boundary

`src/native_adapter.*` and the existing owned `Watcher` implement HDK-first
capture, persistent identity, configured-root extraction, bounded queues,
main-thread application, echo classification, and post-apply verification for
the seven Phase 2 families on Houdini 21.0.729 / Windows. `src/main.cpp`
registers a narrow JSON bridge through Houdini's official HOM extension hook;
`coophou/houdini_adapter/` converts only plain records and owns portable IDs
and single-process orchestration. The native mirror retains plain supported
state, never a Houdini pointer between calls.

This is an adapter contract, not a session product. Transport, discovery,
multi-process authority wiring, UI, presence, snapshot recovery, and supported
undo remain absent.

## Feasibility position

**Required:** coophou targets a supported node-authoring subset, not arbitrary Houdini state.

**Required by ADR 0005:** the production Houdini adapter is HDK/C++-first
behind a narrow plain-data bridge:

```text
portable collaboration core
        │
versioned native Python bridge
        │
thin HDK/C++ production adapter
   ├── global/lifecycle capture and scoped extraction
   └── ordered main-thread application gateway
        │
supported Houdini scene state
```

The HDK bridge is ABI-sensitive and therefore remains small by responsibility.
It owns Houdini-specific capture, identity, extraction, supported mutation, and
verification, but not protocol, canonical ordering, recovery policy, conflict
rules, transport, presence, or user-facing models. HOM is reserved for UI,
fixtures, diagnostics, independent test oracles, and explicitly negotiated
fallbacks with separate conformance evidence.

See [docs/hdk-hom-feasibility.md](docs/hdk-hom-feasibility.md), ADR 0001, and the [operation support matrix](docs/operation-support-matrix.md).

For a supported subset of Houdini edits, all healthy clients that consume the same canonical operation history should converge to equivalent collaborative state.

“Equivalent” does not necessarily mean byte-identical `.hip` files. It means the synchronized entities and properties defined by the project contract agree.

The supported state surface must be explicit. Unsupported Houdini state should be rejected, ignored with clear policy, or reconciled through a documented mechanism. It must not be accidentally synchronized.

## Required boundaries

### Presence service

Owns transient, lossy collaboration awareness.

Responsibilities:

- collaborator identity and status;
- cursor/selection/active-node previews;
- follow mode;
- rate limiting and TTL;
- privacy preferences;
- overlay view models.

Presence never owns durable scene truth and never participates in replay or recovery.

### Overlay composition service

Owns coophou's temporary network-editor shapes.

Responsibilities:

- merge cursor, selection, follow, and edit-pulse shapes;
- rate-limit redraw;
- remove only coophou-owned overlays;
- respond to pane/network context changes;
- avoid persistent scene mutation.

Do not let separate features call `setOverlayShapes` independently and overwrite one another.

### Houdini adapter

Owns all direct interaction with Houdini scene APIs and Houdini-specific
lifecycle hooks. The production implementation uses HDK/C++; HOM use is
limited to the roles declared by ADR 0005.

Responsibilities:

- register and unregister callbacks;
- translate native Houdini objects to stable references and plain data;
- schedule remote mutation on Houdini's main thread;
- group or suppress callback echo;
- expose scene lifecycle events;
- create safe temporary snapshots when requested;
- integrate status and diagnostics with the Houdini UI.

Pure protocol and server code must not require Houdini.

### Capture and normalization

Converts low-level Houdini notifications into semantic operations.

Responsibilities:

- filter unsupported events;
- coalesce redundant event bursts when safe;
- capture before/after information required by the operation;
- attach stable entity identity;
- avoid network and recovery work inside Houdini callbacks.

Capture should describe what changed, not decide global order.

### Operation model

Defines plain-data edit contracts.

Responsibilities:

- operation type registry;
- payload validation;
- operation IDs;
- entity IDs and references;
- dependencies or preconditions;
- serialization compatibility;
- deterministic application semantics;
- inversion metadata when rollback requires it.

An operation must not contain a live `hou.Node`, `hou.Parm`, Qt object, callback, thread primitive, or socket.

### Client session

Coordinates local and canonical state.

Responsibilities:

- connection lifecycle;
- outgoing queue;
- incoming canonical stream;
- acknowledgement tracking;
- optimistic-operation tracking;
- sequence-gap detection;
- reconnect and resume;
- application scheduling;
- recovery state;
- user-visible health.

The client session is a state machine, not a bag of flags.

### Session authority

Establishes canonical order and session membership.

Responsibilities:

- accept or reject protocol-valid messages;
- assign monotonically increasing canonical sequence values;
- broadcast accepted transactions;
- support resume from a known sequence;
- retain enough history or provide an authoritative snapshot path;
- prevent cross-session data leakage;
- expose deterministic errors.

The authority should not need Houdini installed.

### State recovery

Repairs clients that cannot continue normal streaming.

Responsibilities:

- detect missing history;
- classify apply failures;
- defer resolvable dependencies;
- roll back and replay when safe;
- compare or install authoritative snapshots;
- transition to a visible fatal state when repair cannot be trusted.

Recovery should not be hidden inside socket reconnect callbacks.

### Presentation

Shows human-readable collaboration state.

Responsibilities:

- distinguish transport and synchronization health;
- surface actionable failure details;
- avoid modal interruption for routine reconnect;
- permit safe disconnect, retry, or reconciliation actions;
- never display “synchronized” optimistically.

Presentation must not own protocol truth.

## Dependency direction

Prefer this dependency direction:

```text
UI ───────────────┐
Houdini adapter ──┼──> client/application orchestration
                  │
transport ────────┘
                         ↓
                 operation model
                         ↓
                  shared utilities
```

The operation model must remain independent of Houdini, UI, and concrete transport.

The server may depend on the operation and protocol model, but not on client UI or Houdini adapters.

Avoid cycles such as:

- callbacks importing the full client singleton;
- protocol models importing `hou`;
- UI widgets directly mutating canonical sequence state;
- server code importing client modules for shared constants.

## State ownership

Each piece of state should have one authoritative owner.

Examples:

| State | Owner |
|---|---|
| Current socket | transport/client session |
| Connection generation | client session |
| Last confirmed sequence | client session/recovery state |
| Canonical next sequence | session authority |
| Applied accepted transaction IDs | application/recovery store |
| Houdini entity lookup cache | Houdini adapter |
| Remote-apply suppression depth | Houdini application context |
| UI label text | presentation layer |
| Protocol version | shared protocol model |

Duplicated cached state must have an explicit invalidation strategy.

## Data model guidance

Prefer explicit immutable or append-only records for network history and state transitions.

Useful conceptual records include:

- `Operation`
- `Transaction`
- `EntityRef`
- `MessageEnvelope`
- `AcceptedTransaction`
- `RejectedTransaction`
- `PendingLocalTransaction`
- `ApplyResult`
- `RecoveryCheckpoint`
- `ClientHealth`

Names may differ in the repository. Their responsibilities should not collapse into one mutable dictionary.

## State machines

### Capability state

```text
UNKNOWN
  → NEGOTIATING
  → COMPATIBLE
  → LIMITED
  → INCOMPATIBLE
```

A client may join only with the intersection of capabilities accepted by session policy. Unsupported operation types cannot be emitted merely because a local Houdini API exposes them.

### Presence

```text
ABSENT
  → ACTIVE
  → IDLE
  → STALE
  → ABSENT
```

Presence expiry must not affect durable synchronization health.

At minimum, model these state machines explicitly.

### Transport

```text
DISCONNECTED
  → CONNECTING
  → CONNECTED
  → DISCONNECTING
  → DISCONNECTED
```

Failures may transition from any active state to `DISCONNECTED`.

### Synchronization

```text
UNKNOWN
  → JOINING
  → CATCHING_UP
  → SYNCHRONIZED
  → DEGRADED
  → RECONCILING
  → SYNCHRONIZED | FATAL
```

Transport may be connected while synchronization is `CATCHING_UP`, `DEGRADED`, or `FATAL`.

### Local operation

```text
CAPTURED
  → QUEUED
  → SENT
  → ACCEPTED
  → CONFIRMED
```

Alternative outcomes:

```text
SENT → REJECTED
SENT → RETRY_PENDING
ACCEPTED → RECONCILIATION_REQUIRED
```

The precise implementation may combine states, but transitions and invariants must remain observable.

## Architectural change policy

Use an ADR when changing:

- canonical ordering authority;
- stable identity strategy;
- operation schema compatibility;
- optimistic application policy;
- rollback or snapshot strategy;
- supported conflict semantics;
- transport security model;
- undo behavior;
- storage of operation history.

A refactor that preserves contracts does not require an ADR. A change in durable behavior does.

See [docs/adr/README.md](docs/adr/README.md).
