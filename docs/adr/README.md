# Architecture Decision Records

Use Architecture Decision Records for durable choices that future contributors must understand.

## When to write an ADR

Write an ADR before or with a change to:

- canonical ordering;
- stable entity identity;
- operation schema compatibility;
- optimistic application;
- conflict policy;
- recovery and snapshots;
- undo semantics;
- transport security;
- operation-history storage;
- supported Houdini state boundaries.

Do not use ADRs for routine refactors that preserve behavior.

## Statuses

- Proposed
- Accepted
- Superseded
- Deprecated
- Rejected

Never rewrite history to make an old decision look current. Add a new ADR that supersedes it.

## Naming

## Current proposed decisions

- [0001: Keep the HDK bridge thin](0001-thin-hdk-bridge.md)
- [0002: Use persistent node user data as the v1 identity carrier](0002-persistent-node-user-data-identity.md)
- [0003: Represent local undo and redo as new collaborative transactions](0003-v1-undo-policy.md)
- [0004: Limit v1 to ordinary node-graph authoring](0004-v1-supported-surface.md)

Use sequential names:

```text
0001-stable-entity-identity.md
0002-canonical-session-order.md
```

The repository should choose whether numbering begins with these future decisions or whether existing decisions are backfilled.

## Template

Copy [template.md](template.md).

A useful ADR includes:

- context and problem;
- decision;
- alternatives considered;
- synchronization invariants affected;
- consequences;
- migration;
- test and observability requirements;
- security implications;
- status and date.

## Decision quality

An ADR should answer:

- Why is this decision needed?
- What failure does it prevent?
- What becomes harder?
- How will clients migrate?
- How will we know the decision works?
- How can it be superseded safely?

Avoid ADRs that merely say “use library X” without explaining the architectural consequence.
