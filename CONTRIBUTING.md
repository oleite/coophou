# Contributing to coophou

This guide describes how to make changes without weakening synchronization correctness or Houdini stability.

## Start with repository discovery

For Houdini-facing changes, also verify:

- the exact API/build in the event-probe fixture;
- whether the path uses HOM, HDK, or fallback;
- callback ownership and removal;
- native ABI/package selection;
- capability negotiation impact;
- whether the change is durable scene state or transient presence.

Before coding, verify:

- supported Python and Houdini versions;
- package and source layout;
- server entry point;
- Houdini installation or package-loading method;
- test runner and configuration;
- formatting, linting, and type-checking tools;
- whether integration tests require a Houdini license;
- environment variables and local config;
- generated files that must not be edited.

Record stable findings in [docs/current-state.md](docs/current-state.md).

Do not invent commands from this guide. Use the repository's actual configuration.

## Keep patches narrow

A good change should usually affect one primary responsibility:

- event capture;
- operation schema;
- entity resolution;
- sequencing;
- transport;
- application;
- recovery;
- UI;
- tests or diagnostics.

When a change crosses boundaries, explain why the boundary crossing is required.

Avoid mixing:

- protocol migrations with formatting sweeps;
- synchronization fixes with UI redesign;
- callback-lifecycle fixes with unrelated module moves;
- dependency upgrades with behavior changes.

## Design note for risky changes

Before implementing a risky synchronization change, write a short design note in the issue, pull request, or commit description:

1. Problem and observed failure.
2. Current behavior.
3. Desired behavior.
4. Invariants affected.
5. Local optimistic timeline.
6. Remote canonical timeline.
7. Duplicate and reconnect behavior.
8. Failure and recovery behavior.
9. Test plan.
10. Compatibility or migration impact.

Use an ADR for durable architectural decisions.

## Coding practices

### Plain data at boundaries

At operation and protocol boundaries:

- use explicit fields;
- validate early;
- avoid implicit defaults that change semantics;
- preserve unknown optional fields only when compatibility requires it;
- do not serialize runtime objects;
- include diagnostic context without making paths authoritative.

### Exceptions

Catch exceptions where the code can add context or choose a recovery action.

Do not use:

```python
try:
    ...
except Exception:
    pass
```

Prefer:

- domain-specific exceptions;
- a structured `ApplyResult`;
- logging with operation and entity identifiers;
- an explicit transition to deferred, rejected, reconciliation-required, or fatal state.

### Cleanup

Every registration or resource acquisition must have a symmetric release path.

Test repeated:

- initialize;
- connect;
- disconnect;
- reload;
- initialize again;
- change scene;
- shut down.

Cleanup should be idempotent.

### Compatibility

Do not add syntax, APIs, or dependencies unsupported by the project's declared Houdini Python version.

Keep server and pure-Python tests runnable without Houdini where practical.

## Testing workflow

For each change:

1. Add or identify a failing focused test.
2. Implement the smallest correct behavior.
3. Run focused unit tests.
4. Run related fake-adapter or state-machine tests.
5. Run broader tests.
6. Run Houdini integration tests when the changed contract crosses the adapter.
7. Test at least one failure path manually when automation cannot cover it.

See [docs/testing.md](docs/testing.md).

## Documentation updates

Update the document that owns the changed contract:

| Change | Document |
|---|---|
| Component boundary | `ARCHITECTURE.md` |
| Verified repository fact | `docs/current-state.md` |
| Operation lifecycle or identity | `docs/synchronization-model.md` |
| Houdini callbacks, undo, snapshots | `docs/houdini-integration.md` |
| Message field or protocol behavior | `docs/protocol.md` |
| Retry, replay, conflict, reconciliation | `docs/recovery-and-conflicts.md` |
| Test obligation or harness | `docs/testing.md` |
| Logs, states, runbooks | `docs/operations-and-observability.md` |
| Trust boundary | `docs/security.md` |
| Durable architectural choice | `docs/adr/` |

## Review checklist

### Artist experience

- [ ] Local input does not wait on the network.
- [ ] Presence does not dirty the scene.
- [ ] No routine reconnect modal was added.
- [ ] Activity is grouped by user intent.
- [ ] Overlays are temporary and owned centrally.
- [ ] Accessibility does not depend on color.
- [ ] Leave/disconnect restores ordinary Houdini behavior.
- [ ] Failure wording explains what happened to local work.

### HDK/HOM feasibility

- [ ] The event trace is checked in or updated.
- [ ] Raw Houdini pointers do not outlive callbacks.
- [ ] The HDK bridge remains thin.
- [ ] Runtime API/bridge compatibility is checked.
- [ ] HOM fallback behavior is explicit.
- [ ] All target Houdini builds were tested or the capability is disabled.

### Correctness

- [ ] The supported behavior is explicit.
- [ ] Local and remote paths have equivalent semantics.
- [ ] Duplicate delivery is safe.
- [ ] Sequence gaps cannot be skipped silently.
- [ ] Entity resolution cannot redirect to a reused path.
- [ ] Callback echo is suppressed safely.
- [ ] Failure produces an explicit recovery state.

### Houdini

- [ ] No `hou` mutation occurs off the main thread.
- [ ] No UI access occurs off the UI thread.
- [ ] Callbacks and timers clean up.
- [ ] Reinitialization does not duplicate observers.
- [ ] Undo behavior is defined.
- [ ] The artist's working file is not overwritten.

### Network and security

- [ ] Input shape and limits are validated.
- [ ] Retries retain message and operation identity.
- [ ] No arbitrary remote code execution is introduced.
- [ ] Session boundaries are enforced.
- [ ] Queues and retries are bounded.

### Tests and diagnostics

- [ ] A regression test covers the bug or new contract.
- [ ] Failure injection is included where relevant.
- [ ] Logs include operation, entity, client, and sequence context.
- [ ] User-visible health cannot falsely show synchronized.
- [ ] Documentation is updated.

## Commit and pull-request description

Use language that explains behavior, not only implementation.

Good:

> Preserve operation IDs across reconnect so duplicate detection remains valid after resend.

Weak:

> Refactor queue stuff.

Mention:

- the invariant;
- the failure mode;
- the test;
- any migration or compatibility consequence.
