# ADR 0005: Use an HDK-first production adapter

- **Status:** Accepted
- **Date:** 2026-07-17
- **Owners:** coophou maintainers
- **Supersedes:** None
- **Superseded by:** None

## Context

The Phase 1 probes established that Houdini's global HDK callbacks provide the
strongest callback-time evidence for the supported scene changes. In
particular, `OP_NODE_PREDELETE` can preserve identity before Houdini invalidates
the node, while HOM may have already cleared node user data by
`BeingDeleted`. The same probes also established that raw callbacks are noisy,
that one gesture may produce many events, and that callback reasons do not map
one-to-one to durable operations.

The earlier roadmap proposed a HOM-first Phase 3 adapter and deferred a native
bridge. That split would make the production capture and application paths
different from the path whose deletion and lifecycle behavior was verified.

## Decision

Production capture and supported scene application are HDK/C++-first.

The native adapter owns only Houdini-specific work:

- global operator and scene-lifecycle observation;
- callback-time identity and pre-delete capture;
- bounded event aggregation and coalescing;
- targeted supported-state extraction for final values, compound-operation
  completion, verification, and recovery boundaries;
- persistent entity-ID assignment, lookup, tombstones, and copy-collision
  repair;
- one ordered, bounded, main-thread application gateway;
- native apply context and echo classification;
- plain-data bridge validation, queues, capabilities, and diagnostics.

A narrow, versioned native Python bridge connects that adapter to the portable
core. Bridge records contain plain serialized data only. Python may construct
the existing frozen Phase 2 operations and transactions, generate their IDs,
and run the portable client/authority orchestration. Native code does not own
canonical order, protocol policy, conflict policy, recovery policy, transport,
presence, or UI models.

HDK global and lifecycle callbacks are primary capture evidence. Scoped native
state inspection is used to settle noisy event bursts and verify results; it is
not a routine full-scene replacement protocol. HOM callbacks and HOM scene
mutation are diagnostic, test-oracle, fixture, or explicitly negotiated
fallback tools only. The production adapter must not route its real capture or
application work through Python HOM behind the bridge.

This decision extends ADR 0001. “Thin” describes responsibility and ABI blast
radius, not a prohibition on the Houdini-specific logic required to implement
the seven supported operation families correctly.

## Bridge and locking boundary

The preferred target is one installed DSO exposing prefixed functions from
`HOMextendLibrary`. Calls validate a bridge schema version and exchange bounded
JSON-compatible plain data. Houdini scene access occurs only on Houdini's main
thread under the appropriate Houdini/HOM synchronization contract. Python API
access uses Houdini's interpreter lock independently. No live Houdini pointer,
Python object, Qt object, callback, or lock crosses a queue boundary.

Unknown bridge versions, operation types, stale scene generations, invalid
identities, overflows, and unexpected partial application fail closed with
structured errors.

## Consequences

### Positive

- capture, pre-delete identity, application, and verification share one
  Houdini-native implementation;
- callback-time evidence and scene-generation changes remain available before
  object invalidation;
- bounded aggregation can coalesce noisy native events without making HOM the
  semantic source of truth;
- the portable core and its ordinary-Python tests remain isolated from Houdini
  and the ABI-sensitive DSO;
- one native apply context can classify expected echoes and internal identity
  writes across every supported operation family.

### Negative

- Phase 3 requires more C++ schema, extraction, validation, and test-fixture
  code than a HOM prototype;
- each supported Houdini build requires a compatible DSO and real-Houdini
  contract tests;
- native partial-apply evidence and reconciliation reporting must be explicit;
- capability-gated fallback behavior cannot be assumed to match native
  coverage without separate conformance evidence.

## Compatibility

Package one DSO per supported `HDK_API_VERSION`, platform, and compatible
compiler family. Runtime capabilities report the Houdini version/build,
`HDK_API_VERSION`, platform, bridge schema version, and supported operation
families. A fallback is available only when its capability declaration and
conformance tests prove the requested operation surface.

## Testing

- native schema, queue, aggregation, identity, suppression, and lifecycle unit
  tests;
- DSO load and bridge round-trip tests in the exact supported Houdini build;
- local-capture and remote-application contract tests for all seven Phase 2
  operation families;
- duplicate, stale-generation, path-reuse, copy-collision, failure-boundary,
  reload, cleanup, and queue-overflow tests;
- semantic post-apply extraction and structured mismatch evidence;
- representative callback, settle, apply, verification, and serialization
  performance measurements.

Physical mouse drag, interactive clipboard behavior, DSO unload, and undo-stack
semantics remain unclaimed until separately exercised on the supported build.
