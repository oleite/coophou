# ADR NNNN: Decision title

- **Status:** Proposed
- **Date:** YYYY-MM-DD
- **Owners:** Names or roles
- **Supersedes:** None
- **Superseded by:** None

## Context

Describe the current behavior, failure mode, constraints, and why a durable decision is required.

Separate verified facts from assumptions.

## Decision drivers

- Correctness requirement
- Houdini constraint
- Recovery requirement
- Performance requirement
- Compatibility requirement
- Security requirement

## Decision

State the decision precisely.

Define:

- authoritative owner of state;
- data contract;
- ordering or lifecycle behavior;
- failure behavior;
- compatibility boundary;
- migration boundary.

## Invariants affected

List the invariants in `AGENTS.md` and focused documents that this decision preserves, changes, or introduces.

## Alternatives considered

### Alternative A

Benefits, drawbacks, and reason not selected.

### Alternative B

Benefits, drawbacks, and reason not selected.

## Consequences

### Positive

- ...

### Negative

- ...

### Risks

- ...

## Migration

Explain how existing clients, stored history, scenes, IDs, snapshots, and tests move to the new decision.

State whether mixed versions may share a session.

## Failure and recovery behavior

Explain behavior under:

- duplicate delivery;
- sequence gaps;
- reconnect;
- rejection;
- application failure;
- incompatible client;
- snapshot recovery.

## Testing

List required unit, fake-adapter, multi-client, Houdini integration, and failure-injection tests.

## Observability

List new logs, identifiers, metrics, health states, and artist-facing messages.

## Security and privacy

Describe trust-boundary changes, input validation, confidentiality, and data retention.

## Open questions

- ...

## Follow-up work

- ...
