# ADR 0004: Limit v1 to ordinary node-graph authoring

- **Status:** Accepted
- **Date:** 2026-07-17
- **Owners:** coophou maintainers
- **Supersedes:** None
- **Superseded by:** None

## Context

Houdini contains many graph systems, runtime simulations, asset definitions, animation systems, and opaque custom data. Attempting to synchronize all state would make correctness and recovery unprovable.

## Decision

v1 supports only the operations marked **v1 candidate** in `docs/operation-support-matrix.md`:

- node/subtree create;
- node/subtree delete;
- rename;
- network position;
- input connect/disconnect;
- simple unanimated, unexpressed parameter tuples.

Node flags are not part of the accepted v1 durable surface. Adding any flag is
an expansion requiring its own probe evidence and capability update.

Transient presence is separate.

## Explicit exclusions

- cooked geometry and simulation;
- APEX;
- HDA definition edits and locked internals;
- expressions/keyframes/takes;
- multiparms and spare schemas;
- network boxes/sticky notes/dots before identity is solved;
- personal workspace state.

## Consequences

Phase 2 provides strict portable contracts for exactly these seven families:
ordinary-node create, copied-subtree create, subtree delete, rename, final
position, destination-input connect/disconnect, and complete simple raw
parameter tuple. No generic mutation payload is available. Houdini adapter
support still depends on Phase 3 capture/application probes; accepting this ADR
does not claim those integrations are complete.

The first release can be genuinely reliable and enjoyable for procedural node-network collaboration, but it must label unsupported edits honestly.

Unsupported edits may:

- remain local with a visible warning;
- pause collaboration;
- require a fork;
- be rejected by capability policy.

They may not be silently dropped while the UI remains green.

## Expansion rule

Every new operation family needs:

- API/event probe;
- identity;
- schema;
- transaction boundary;
- idempotency;
- conflict policy;
- undo;
- recovery;
- UX;
- performance;
- security;
- tests;
- an updated capability bit.
