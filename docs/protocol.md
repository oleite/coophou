# Network protocol

This document defines recommended protocol properties. Exact field names are **Proposed** until verified or accepted through an ADR.

## Goals

The protocol should be:

- versioned;
- deterministic;
- inspectable;
- safe to validate before Houdini application;
- resilient to duplicate delivery;
- resumable after disconnect;
- bounded in memory and message size;
- independent of Houdini runtime objects.

JSON is a reasonable initial encoding. A binary encoding should only replace it after measured need and an explicit compatibility plan.

## Framing

The transport must define how one message ends and the next begins.

Acceptable approaches include:

- WebSocket message frames;
- length-prefixed TCP frames;
- newline-delimited JSON only when embedded newlines and size limits are handled safely.

Do not assume a single `recv` call returns one complete message.

A frame parser must handle:

- partial frames;
- multiple frames in one read;
- oversized declared length;
- invalid encoding;
- disconnect mid-frame;
- bounded buffering.

## Envelope

A conceptual envelope:

```json
{
  "protocol_version": 1,
  "message_type": "operation.submit",
  "message_id": "uuid",
  "session_id": "session-uuid",
  "client_id": "client-uuid",
  "connection_generation": 3,
  "payload": {}
}
```

Required envelope semantics:

- `protocol_version`: compatibility contract;
- `message_type`: selects payload schema;
- `message_id`: transport-level deduplication and diagnostics;
- `session_id`: prevents cross-session application;
- `client_id`: stable author identity for the session;
- `connection_generation`: helps reject stale responses from an old connection.

An operation also has its own `operation_id`. Message and operation identity are not interchangeable.

## Message families

### Capability negotiation

- `capability.offer`
- `capability.accepted`
- `capability.limited`
- `capability.rejected`

A capability offer should include:

- protocol version range;
- operation schema versions;
- supported operation types;
- Houdini product version/build;
- native bridge build and `HDK_API_VERSION` when present;
- Python/Qt adapter version;
- relevant installed operator/HDA/project fingerprint;
- snapshot format support;
- feature flags such as presence previews.

The authority decides the session capability intersection. A client must not emit an operation outside the accepted capability set.

### Presence

- `presence.update`
- `presence.leave`
- `presence.config`

Presence messages are lossy, bounded, rate-limited, and have a TTL. They are not part of operation history and do not require per-message acknowledgement.

Recommended conceptual message types:

### Session

- `session.join`
- `session.joined`
- `session.leave`
- `session.error`

### Operations

- `operation.submit`
- `operation.accepted`
- `operation.rejected`
- `operation.batch`
- `operation.ack`

### Resume and history

- `history.resume`
- `history.batch`
- `history.gap`
- `history.unavailable`

### Snapshot recovery

- `snapshot.request`
- `snapshot.offer`
- `snapshot.chunk` or external secured transfer reference
- `snapshot.complete`
- `snapshot.reject`

### Health

- `heartbeat.ping`
- `heartbeat.pong`
- `status.notice`

Exact names may differ. Their semantic separation should remain.

## Operation payload

Conceptual submitted operation:

```json
{
  "operation_id": "operation-uuid",
  "operation_type": "node.parameter.set",
  "operation_schema_version": 1,
  "author_client_id": "client-uuid",
  "entity_ref": {
    "entity_id": "entity-uuid",
    "entity_kind": "node",
    "last_known_path": "/obj/geo1/box1"
  },
  "dependencies": [],
  "preconditions": {},
  "data": {
    "parameter": "sizex",
    "value_kind": "float",
    "value": 2.0
  }
}
```

Conceptual accepted operation adds:

```json
{
  "canonical_sequence": 1842,
  "accepted_by": "authority-id"
}
```

The authority should not rewrite operation identity. If it normalizes payload fields, the canonical form must remain traceable to the submitted operation.

## Acknowledgements

Define what each acknowledgement means.

Possible stages:

- frame received;
- message validated;
- operation accepted into canonical history;
- operation applied by a client.

Do not use a generic `ack` whose meaning differs by call site.

The session authority normally acknowledges **acceptance**, not successful Houdini application on all peers.

Clients should track local application separately.

## Resume

A reconnecting client should send:

- session ID;
- client ID;
- last confirmed canonical sequence;
- last known checkpoint/snapshot ID;
- pending local operation IDs;
- protocol version;
- a new connection generation.

The authority responds with one of:

- missing accepted operation range;
- no missing operations;
- history unavailable, snapshot required;
- session no longer exists;
- incompatible protocol;
- client identity rejected.

A client must not declare synchronized until missing history is applied and pending local operations are resolved.

## Versioning

### Protocol version

Increment for incompatible envelope or session behavior.

### Operation schema version

May evolve individual operation types without changing all protocol messages.

Compatibility rules must state:

- which older versions can be read;
- which versions can be emitted;
- whether unknown optional fields are preserved;
- behavior for unknown operation types;
- migration of stored history;
- mixed-version session policy.

Reject incompatible versions before Houdini mutation.

## Validation

Validate in layers.

### Frame validation

- maximum frame size;
- valid encoding;
- valid JSON or chosen encoding;
- no trailing unparsed data unless framing allows it.

### Envelope validation

- known protocol version;
- known message type;
- required IDs;
- session/client consistency;
- field count and string length limits.

### Payload validation

- known operation type;
- operation schema version;
- allowed entity kind;
- numeric bounds;
- collection lengths;
- path length;
- payload-specific constraints;
- no forbidden fields.

### Application validation

- entity identity resolution;
- preconditions;
- dependencies;
- Houdini support;
- scene generation;
- canonical sequence.

Passing protocol validation does not guarantee the operation can be applied.

## Error model

Use stable machine-readable error codes plus human-readable detail.

Example categories:

- `PROTOCOL_UNSUPPORTED_VERSION`
- `PROTOCOL_INVALID_MESSAGE`
- `SESSION_NOT_FOUND`
- `SESSION_MISMATCH`
- `OPERATION_UNKNOWN_TYPE`
- `OPERATION_INVALID_PAYLOAD`
- `OPERATION_DUPLICATE_CONFLICT`
- `HISTORY_GAP`
- `HISTORY_UNAVAILABLE`
- `ENTITY_NOT_FOUND`
- `ENTITY_IDENTITY_MISMATCH`
- `DEPENDENCY_MISSING`
- `PRECONDITION_FAILED`
- `APPLICATION_UNSUPPORTED`
- `RECONCILIATION_REQUIRED`
- `INTERNAL_ERROR`

Do not leak sensitive stack traces to remote peers. Preserve detailed local logs.

## Limits and backpressure

Use separate limits for durable and transient traffic.

Under load:

1. drop superseded cursor and gesture previews;
2. coalesce later presence state;
3. preserve durable operation order;
4. stop accepting new durable local work before allowing an unbounded queue;
5. surface degraded state truthfully.

Define limits for:

- frame size;
- operations per batch;
- outstanding unacknowledged messages;
- outgoing queue;
- deferred dependency queue;
- resend attempts;
- snapshot size;
- heartbeat timeout;
- history retention.

When limits are exceeded, transition explicitly to throttled, degraded, rejected, or recovery-required behavior.

Unbounded queues can freeze Houdini and are protocol correctness risks.

## Heartbeats

Heartbeats detect transport liveness.

They do not prove:

- canonical history is complete;
- remote operations applied;
- scenes are equivalent;
- callbacks are active;
- local pending operations are confirmed.

Keep heartbeat state separate from synchronization state.

## Authentication and confidentiality

A local prototype may initially use a trusted network, but the protocol must not assume trust internally.

Before use across untrusted networks, define:

- transport encryption;
- server authentication;
- client/session authentication;
- authorization to join a session;
- replay protection;
- snapshot confidentiality;
- secret storage;
- audit policy.

See [security.md](security.md).
