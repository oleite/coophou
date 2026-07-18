# ADR 0003: Represent local undo and redo as new collaborative transactions

- **Status:** Proposed
- **Date:** 2026-07-17
- **Owners:** coophou maintainers
- **Supersedes:** None
- **Superseded by:** None

## Context

This ADR intentionally remains **Proposed** after Phase 2. The portable core
does not interpret undo/redo, and Phase 1 did not prove reliable gesture
boundaries across the supported operation surface. Phase 3 must not treat this
policy as accepted without the required Houdini probes and contract tests.

Putting remote edits on a user's local undo stack allows Ctrl+Z to undo another collaborator's work. A true server-side semantic undo is substantially more complex.

Houdini already performs local undo/redo correctly for the local scene and emits change notifications for many affected properties.

## Decision

For v1:

- apply remote operations with undo creation disabled;
- leave ordinary local Houdini Ctrl+Z/Ctrl+Y behavior intact;
- capture the resulting state changes;
- group them into a new collaborative transaction labeled as undo or redo when detectable;
- submit that transaction to canonical history.

Undo does not erase history. It creates a new state transition.

## Consequences

### Positive

- local keyboard behavior remains familiar;
- remote changes do not clutter the local stack;
- no server-side history surgery;
- other clients receive the resulting state.

### Negative

- undo may overwrite a later remote value;
- structural undo may generate bulk callbacks;
- exact transaction boundaries require HDK/HOM probing;
- unsupported undo results may require reconciliation.

## Conflict behavior

If the local undo produces valid supported operations, canonical order decides the result.

If it produces unsupported or ambiguous bulk state:

- preserve local work;
- pause confirmation;
- request reconciliation or ask the user to fork/leave.

Never ignore a local undo that changed the scene.

## Testing

Every v1 operation must test:

- edit;
- remote edit afterward;
- local undo;
- local redo;
- callback grouping;
- echo suppression;
- reconnect with pending undo transaction;
- activity feed wording.
