# Security model

coophou transports instructions that mutate a professional DCC scene. Even a prototype should enforce a narrow trust boundary.

## Threat model

The native HDK bridge increases impact: malformed data or a lifetime error can crash Houdini. Its input surface must be narrower than the Python core's, not broader.

Transient presence may expose what a user is viewing or editing. Treat cursor, selection, active parameter, and viewport pose as privacy-sensitive telemetry.

Potentially harmful inputs include:

- a malformed or compromised client;
- a stale client using an incompatible protocol;
- accidental cross-session messages;
- replayed messages;
- oversized messages;
- malicious paths or display strings;
- unsafe snapshot references;
- compromised server or network;
- arbitrary payload fields reaching Houdini APIs.

A trusted studio network reduces exposure. It does not make unsafe deserialization or remote code execution acceptable.

## Prohibited capabilities

Collaborative messages must never directly provide:

- arbitrary Python source to execute;
- pickled Python objects;
- shell commands;
- unrestricted file reads or writes;
- arbitrary environment variable access;
- unrestricted module imports;
- raw Qt object access;
- arbitrary Houdini expression evaluation outside an explicitly supported operation contract.

Do not add “temporary debug” remote execution paths.

## Input validation

### Phase-3 native bridge boundary

The installed Houdini DSO accepts only JSON objects up to 4 MiB through ten
prefixed `hou.coophou_native_*` functions. Every request validates bridge
schema version and exact fields; apply validates the complete frozen
transaction/operation shape, allowlisted operation type, configured operator
and parameter capability, IDs, bounds, preconditions, and scene generation
before mutation. Unknown fields, versions, operations, queue overflow, and
stale work fail closed. No request can provide Python, imports, callbacks,
expressions, arbitrary filesystem paths, or raw Houdini objects. Scene work is
main-thread-only. The bridge is local process plumbing and is not a network
protocol or trust grant.

Validate before Houdini application:

- protocol version;
- message type;
- session and client identity;
- field types;
- string lengths;
- collection sizes;
- numeric ranges;
- enum values;
- operation type;
- operation schema version;
- entity kind;
- path format where relevant;
- snapshot metadata and integrity;
- total frame size.

Use allowlists for operation types and fields.

## Session isolation

Capability negotiation is also a security boundary.

Reject peers that advertise unsupported:

- protocol or operation schemas;
- native bridge versions;
- Houdini builds;
- project/operator fingerprints;
- snapshot formats.

Never let a client opt itself into a capability the authority did not accept.

Every message must be bound to one collaboration session.

The server and client should reject:

- missing session ID;
- messages for another active session;
- stale responses from an old connection generation;
- unauthorized joins;
- snapshots from another session;
- sequence values outside the joined session.

Never route based only on a user-visible session name.

## Replay and duplicates

Operation IDs and message IDs help distinguish retry from replay.

Define retention sufficient to detect expected reconnect duplicates.

A duplicate with the same identity but different immutable content is a security/protocol error.

For untrusted networks, add authenticated transport and stronger replay protection.

## Serialization

Use safe parsers for plain data.

Never use:

- `pickle.loads`;
- `eval`;
- `exec`;
- unsafe YAML loaders;
- dynamic class import based on peer-provided names.

Map operation type strings through a local allowlisted registry.

## File and snapshot safety

Snapshot paths are local implementation details.

A remote peer must not be able to request:

- arbitrary local path reads;
- arbitrary overwrite destinations;
- traversal outside a controlled directory;
- execution of files after transfer.

Use:

- generated filenames;
- controlled temporary/recovery directories;
- size limits;
- integrity hashes;
- metadata validation;
- explicit cleanup;
- encryption for sensitive transfers over untrusted networks.

Do not overwrite the artist's current `.hip` path.

## Denial of service

Protect Houdini from resource exhaustion.

Bound:

- frame size;
- nesting depth;
- operations per message;
- queue lengths;
- retries;
- deferred dependencies;
- logging payload size;
- snapshot size;
- main-thread work per tick;
- client connection count.

Disconnect or degrade safely when limits are exceeded.

## Authentication and authorization

Before deployment beyond a trusted local prototype, define:

- server identity;
- encrypted transport;
- user or service identity;
- session join authorization;
- role permissions;
- session creation permissions;
- snapshot-author permissions;
- audit trail;
- credential storage and rotation.

Do not invent a custom cryptographic protocol. Use established TLS and authentication mechanisms.

## Secrets

Never place secrets in:

- source control;
- operation payloads;
- logs;
- diagnostic bundles;
- Houdini user data intended for scene persistence.

Load secrets through the deployment environment or an established secret store.

## Logging and privacy

Scene paths, node names, parameter values, and snapshots may contain confidential production information.

Support:

- payload redaction;
- configurable log verbosity;
- retention limits;
- diagnostic export review;
- no raw snapshot logging.

Security incidents should be diagnosable without routinely collecting complete scene contents.

## Security review triggers

Request explicit security review when adding:

- internet-facing transport;
- authentication;
- snapshot upload/download;
- filesystem operations;
- plugin discovery;
- dynamic operation registration;
- expression or script synchronization;
- external service integration;
- persistent server history;
- multi-tenant sessions.
