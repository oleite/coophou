# Phase 2 report — portable deterministic collaboration core

Date: 2026-07-17

## Result

Phase 2 is complete as a portable reference core. No Phase 3 integration was
started. `coophou.core` imports and its tests run in ordinary Python without
Houdini, Qt, HDK/native bindings, sockets, the legacy relay, or environment
startup hooks.

## Implemented structure and boundaries

- `errors.py`: versioned structured error details and typed domain failures.
- `models.py`: frozen version-1 records, strict validation, explicit operation
  variants, and deterministic JSON-compatible serialization.
- `scene.py`: stable-ID fake scene, hierarchy, derived paths, tombstones,
  parameters, connections, semantic snapshots, and staged atomic apply.
- `authority.py`: isolated sessions, capability validation, canonical
  projection, transaction deduplication, bounded history, and resume.
- `client.py`: explicit synchronization states, confirmed and working scenes,
  pending replay, canonical gaps, rejection, and reconnect generations.
- `transport.py`: bounded manually scheduled submit/response/broadcast/resume
  queues with drop, duplication, reordering, disconnect, and cleanup controls.

Only standard-library dataclasses, enums, collections, JSON, and validation are
used. There is no global runtime singleton.

## Version-1 records and operation contracts

Every record has an explicit version and exact field set. IDs are bounded opaque
strings. Unknown versions, fields, value shapes, and operation types fail
closed. Immutable semantic content is compared directly through deterministic
serialized records; cross-language canonical hashing is deferred.

The seven operations are:

1. ordinary-node create with new ID, live parent, type, final name/position,
   and supported initial raw tuples;
2. copied-subtree create with repaired unique IDs, parent-before-child order,
   and explicit connections after endpoint creation;
3. subtree delete with exact stable-ID deletion set and retained tombstones;
4. rename by entity ID with optional expected current name;
5. final coalesced position with optional expected previous position;
6. destination input set for connect or disconnect with exact expected source;
7. complete homogeneous raw parameter tuple set, including menu tokens as
   strings, with optional expected previous tuple.

Paths are diagnostics only. There is no generic mutation dictionary or
executable/dynamic payload field.

## Sequencing, authority projection, and atomicity

An accepted transaction receives exactly one monotonically increasing sequence
within its session. Its operation tuple retains deterministic submitted order.
Rejection neither mutates the canonical projection nor consumes a sequence.
Identical transaction-ID retry returns the remembered result; different content
under the same ID is rejected.

The authority owns one abstract `FakeScene` per session. Canonical validation
and application occur on a clone; invariant validation completes before swap.
Injected failure between operations leaves the authority scene unchanged. The
explicit initial checkpoint is a synthetic `root` entity, or a supplied scene
cloned identically into authority and clients.

## Confirmed and optimistic client state

`confirmed_scene` is the successfully applied contiguous canonical prefix.
`working_scene` is reconstructed from that checkpoint plus remaining pending
local transactions in submission order. Local submission updates only working
state. Own canonical acceptance updates confirmed state once and removes the
matching pending record. Rejection removes only its matching record and rebuilds
the working projection.

A known gap blocks advancement. Conflicting sequence mappings are fatal. If a
remaining pending transaction is invalid after canonical apply or rejection, it
is preserved and state becomes `RECONCILIATION_REQUIRED`; the client never
claims synchronization. New offline edits are disallowed. Reconnect increments
connection generation, ignores old deliveries, resumes strictly after the last
confirmed sequence, and retries pending content with original IDs. Retention
loss also enters `RECONCILIATION_REQUIRED` because snapshots are outside Phase
2.

## Verification and fault results

Final verification passed 88 ordinary-Python tests: 78 Phase 2 core tests and
10 preserved Phase 1 probe/fixture tests. The existing native/Phase 1 CTest
suite also passed 6 of 6 tests.

The ordinary-Python suite covers model round trips, malformed/unsafe payloads,
all operation families, tombstones and path reuse, atomic apply, authority
deduplication and session isolation, optimistic confirmation/rejection/rebase,
gaps, stale generations, bounded queues/history, and multi-client semantic
convergence. Deterministic seeded schedules add repeated submit ordering,
duplicate retry, and broadcast reordering without sleeps or threads.

Fault cases include dropped and duplicate submits, dropped acknowledgements,
disconnect before delivery, disconnect after acceptance, reordered and
duplicate canonical delivery, sequence gaps, rejected optimistic work,
conflicting duplicate IDs, stale generations, truncated history, queue
overflow, and injected mid-transaction failure. An adverse winner-broadcast
before loser-rejection case intentionally stops the loser in
`RECONCILIATION_REQUIRED` rather than discarding its optimistic edit.

## Known limitations

- No HOM, HDK, Qt, real Houdini scene, sockets, framing, relay, presence, UI,
  `.hip` checkpoint, snapshot recovery, undo/redo, merge, authentication, or
  migration machinery exists here.
- Tombstones live for the in-memory session; production retention is deferred.
- Bounded deduplication/history beyond the resumable window requires a future
  checkpoint/snapshot policy.
- Raw parameter support has no real Houdini template verification yet.
- Sibling-name policy rejects collisions; it does not emulate Houdini's unique
  name generation.
- Reconciliation has a truthful terminal model but no automated recovery UI or
  artifact preservation in Phase 2.

## Recommended Phase 3 milestone

Build one single-process HOM adapter against these unchanged contracts: assign
and repair persistent node IDs; normalize only the seven proven Phase 1 event
families; route all fake-core-to-Houdini mutation through one bounded ordered
main-thread gateway with scoped echo suppression and scene-generation checks;
and add real Houdini contract tests for fresh apply, replay, rejection,
copy/paste, delete/path reuse, save/load, callback cleanup, and failure. Keep the
legacy relay disconnected, leave undo/redo proposed, and do not add multi-user
networking until this adapter converges with the portable fake-scene semantics.
