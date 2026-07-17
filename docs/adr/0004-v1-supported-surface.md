# ADR 0004: Limit v1 to ordinary node-graph authoring

- **Status:** Proposed
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
- simple unanimated, unexpressed parameter tuples;
- selected allowlisted node flags after probe validation.

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
