# Glossary

Use these terms consistently in code and documentation.

## Accepted operation

An operation validated by the session authority and assigned canonical sequence.

## Application

The act of mutating a client's Houdini scene to realize an accepted operation.

## Callback echo

A local Houdini callback triggered as a side effect of applying a remote operation.

## Canonical history

The ordered sequence of accepted operations for one collaboration session.

## Canonical sequence

The monotonically increasing position assigned by the session authority.

## Capture

## Capability set

The operation, protocol, adapter, snapshot, and presence features accepted for one client in one session.

## Composite transaction

One canonical user intent containing multiple ordered operations, such as a pasted subtree or undo action.

Observation of a local Houdini change and extraction of enough data to normalize it.

## Checkpoint

A recoverable state associated with a specific canonical sequence.

## Client

One coophou participant, usually associated with one Houdini session.

## Connection generation

A local monotonically increasing identifier distinguishing a new transport connection from stale messages belonging to an older one.

## Convergence

The property that healthy clients consuming the same canonical history reach equivalent synchronized state.

## Deferred operation

An accepted operation temporarily held because a dependency is expected to become available.

## Entity

A synchronized logical object such as a Houdini node.

## Entity ID

A stable coophou identity that does not depend solely on the current Houdini path.

## Entity reference

Plain data used to identify an entity, usually including entity ID, kind, and diagnostic last-known path.

## Event

A low-level notification from Houdini or another runtime source. An event is not automatically a collaborative operation.

## Fatal divergence

A state where coophou can no longer prove or safely restore synchronization automatically.

## Health state

A modeled condition of transport, synchronization, recovery, or pending local work.

## Idempotent

Safe to apply repeatedly without changing the result after the first successful application.

## Last-known path

The most recent Houdini path associated with an entity, carried for diagnostics or constrained lookup. It is not authoritative identity.

## Local optimistic operation

A local edit visible in Houdini before the session authority confirms its canonical position.

## Message

A framed network envelope carrying a protocol payload.

## Message ID

Identity of one transport message. Distinct from operation ID.

## Normalization

Conversion from one or more runtime events into a semantic plain-data operation.

## Operation

A semantic collaborative edit with explicit identity, target, payload, and apply behavior.

## Operation ID

Stable identity of one logical operation across retry, reconnect, and canonical acceptance.

## Pending local operation

## Presence

Ephemeral, lossy information about a collaborator's cursor, selection, location, or activity. Presence is not canonical scene state.

## Preview

A transient gesture update shown to peers before or between durable commits.

A captured local operation not yet fully confirmed in canonical history.

## Precondition

A required target-state condition checked before applying an operation.

## Protocol version

The compatibility version for message envelope and session behavior.

## Rebase

Adjustment or re-evaluation of pending local operations after newly accepted remote operations precede them canonically.

## Reconciliation

A recovery process used when normal streaming cannot prove or restore equivalent state.

## Recovery artifact

A local file preserving artist work before potentially destructive repair.

## Remote-apply context

A scoped context that applies a remote operation while preventing expected callback echo from becoming a new operation.

## Replay

Applying accepted canonical history from a known checkpoint.

## Session

One isolated collaboration history and membership scope.

## Session authority

The component responsible for accepting operations and assigning canonical order.

## Snapshot

A full scene recovery representation associated with a checkpoint.

## Synchronization surface

The explicitly supported subset of Houdini state and edits that coophou promises to synchronize.

## Transport health

Whether communication is connected and functioning. This does not prove synchronized state.
