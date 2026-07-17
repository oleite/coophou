# AGENTS.md

This is the entry point for humans and AI coding agents working on **coophou**, an experimental collaborative editing system for SideFX Houdini.

coophou observes a deliberately supported subset of Houdini edits, normalizes them into explicit operations, establishes canonical session order, and applies accepted remote operations in other Houdini sessions.

The product succeeds only when it is both:

1. **trustworthy** — clients converge or visibly stop and recover; and
2. **pleasant** — ordinary Houdini work remains local-feeling, responsive, quiet, and reversible.

## Instruction precedence

When instructions disagree, follow them in this order:

1. Safety and security requirements.
2. Synchronization and user-experience invariants in this file.
3. A closer `AGENTS.md` for the edited directory.
4. Accepted Architecture Decision Records in `docs/adr/`.
5. Focused documents linked below.
6. Existing local conventions in the code being changed.

Do not mistake proposed architecture for implemented fact. Status labels are defined in [ARCHITECTURE.md](ARCHITECTURE.md).

## Read before changing code

Choose the documents relevant to the work:

- [ARCHITECTURE.md](ARCHITECTURE.md): system boundaries and dependency direction.
- [docs/current-state.md](docs/current-state.md): facts verified in the repository versus open questions.
- [docs/hdk-hom-feasibility.md](docs/hdk-hom-feasibility.md): what Houdini's public HDK/HOM APIs support and where experiments are still required.
- [docs/operation-support-matrix.md](docs/operation-support-matrix.md): the deliberately narrow v1 synchronization surface.
- [docs/synchronization-model.md](docs/synchronization-model.md): identity, transactions, ordering, idempotency, and application.
- [docs/houdini-integration.md](docs/houdini-integration.md): callbacks, the thin HDK bridge, main-thread application, undo, scene lifecycle, and snapshots.
- [docs/protocol.md](docs/protocol.md): message contracts, capability negotiation, durable operations, and transient presence.
- [docs/recovery-and-conflicts.md](docs/recovery-and-conflicts.md): reconnect, rollback, replay, conflicts, and preservation of artist work.
- [docs/user-experience.md](docs/user-experience.md): collaboration panel, presence, overlays, latency budgets, accessibility, and user journeys.
- [docs/implementation-roadmap.md](docs/implementation-roadmap.md): staged proof plan and release gates.
- [docs/testing.md](docs/testing.md): unit, fake-scene, HDK/HOM probe, fault-injection, convergence, and UX testing.
- [docs/operations-and-observability.md](docs/operations-and-observability.md): health states, logs, metrics, diagnostics, and incident handling.
- [docs/security.md](docs/security.md): trust boundaries and prohibited capabilities.
- [CONTRIBUTING.md](CONTRIBUTING.md): implementation and review workflow.
- [docs/glossary.md](docs/glossary.md): canonical terminology.

## Architectural position

### Houdini integration is hybrid

- Keep protocol, operation, ordering, recovery, and most tests in portable code.
- Treat **HOM** as the fastest prototyping and UI layer.
- Treat the **HDK** as a thin, version-specific native bridge for global event observation, efficient main-loop wakeups, and only measured native hot paths.
- Never put business rules or canonical-session logic inside an ABI-sensitive HDK DSO.
- Build and package the HDK bridge per supported Houdini/platform/compiler combination.

### Do not claim API coverage without a probe

Public APIs expose the required categories of hooks, but exact event order, payload, duplication, undo behavior, and copy/paste behavior must be measured for every supported Houdini version.

Before supporting an operation type:

1. add it to the HDK/HOM event probe;
2. record callback traces for create, edit, undo, redo, copy, paste, delete, scene save/load, and remote application;
3. add contract tests;
4. update the support matrix.

## Non-negotiable synchronization invariants

1. **Meaningful edits are explicit operations.** Routine full-scene replacement is not normal synchronization.
2. **Canonical order comes from one session authority.** Wall clocks and socket arrival order are not global order.
3. **Operation IDs survive retries and reconnects.**
4. **Duplicate delivery is safe.**
5. **Collaborative identity is not only a Houdini path.**
6. **A deleted entity's old path can never redirect an operation to a replacement node.**
7. **Remote application cannot echo as a new local edit.**
8. **Known canonical sequence gaps block normal advancement.**
9. **Connected and synchronized are different states.**
10. **Failed application cannot advance confirmed state.**
11. **Recovery actions are explicit: defer, retry, replay, reconcile, preserve work, or stop.**
12. **Durable operations and transient presence are separate channels.**
13. **Canonical transactions are accepted as units; partial local application requires reconciliation.**

## Non-negotiable Houdini invariants

14. **Do not read, evaluate, or mutate shared Houdini node/parameter state from networking threads.**
15. **Do not access Qt widgets from non-UI threads.**
16. **All scene mutation goes through one ordered main-thread application gateway.**
17. **Every callback, interest, timer, event generator, thread, socket, and panel has deterministic idempotent cleanup.**
18. **Scene replacement increments a scene generation and invalidates stale queued work.**
19. **Do not overwrite or retarget the artist's working `.hip` file for rollback.**
20. **Do not parse or merge text-mode `.hip` files as the collaboration protocol.**
21. **Undo behavior is intentional, documented, and tested.**
22. **Do not remove callbacks owned by Houdini or another tool.**
23. **Do not hijack a network-editor event context globally for passive presence UI.**

## Non-negotiable user-experience invariants

24. **Local input never waits for the network.**
25. **No routine network interruption opens a modal dialog.**
26. **The UI never says “synchronized” while history, application, or local confirmation is incomplete.**
27. **Presence is optional, ephemeral, lossy, and never dirties the `.hip` file.**
28. **Remote cursors, selections, and edit pulses use overlays—not persistent node colors or comments.**
29. **A user can leave collaboration without closing Houdini or losing local work.**
30. **Potentially destructive recovery preserves a local recovery artifact first when possible.**
31. **Remote activity is understandable: who changed what and where, without overwhelming the artist.**
32. **Animations and high-frequency gestures are coalesced or previewed so the UI remains smooth.**
33. **Accessibility does not depend on color alone; labels, icons, and text remain available.**
34. **A feature is not complete until a two-artist workflow feels better than exchanging `.hip` files.**

## v1 scope guard

The recommended v1 supports only the operations marked **v1 candidate** in [docs/operation-support-matrix.md](docs/operation-support-matrix.md).

Do not silently expand v1 to:

- cooked geometry or simulation state;
- HDA definition editing;
- locked asset internals;
- spare-parameter schemas or multiparms;
- keyframes, expressions, takes, or animation layers;
- APEX graphs;
- network boxes, sticky notes, or dots before stable identity is solved;
- viewport state, selections, display options, or pane layouts as durable scene operations.

Experiments may exist behind disabled capability flags. Unsupported state must remain explicit.

## Required change workflow

Before editing:

1. Locate the current implementation and tests; do not infer module names from these documents.
2. Classify the change: capture, normalization, identity, transaction, ordering, transport, application, recovery, presence, or UI.
3. State the invariant and user journey being preserved.
4. Trace local optimistic, canonical, and remote-apply timelines.
5. Consider duplicates, gaps, reordering, rejection, reconnect, and scene replacement.
6. Consider rename, copy/paste, deletion, parent deletion, and path reuse.
7. Consider callback echo, undo/redo, module reload, and shutdown.
8. Identify a focused failing test or event-probe trace.
9. Verify the API on every supported Houdini version/build.

While editing:

- Keep Houdini callbacks tiny.
- Move only plain data across thread and language boundaries.
- Preserve operation, transaction, entity, session, sequence, and scene-generation identifiers.
- Use state machines rather than interacting booleans.
- Bound queues, retries, history, deferred dependencies, and main-thread work per tick.
- Fail closed when identity or preconditions are uncertain.
- Keep passive presence separate from scene mutation.
- Prefer overlays that can be removed without changing the scene.

After editing:

1. Run focused tests, then the broader suite.
2. Run the event probe if callback behavior changed.
3. Test duplicate initialization and cleanup.
4. Test one failure and one reconnect path.
5. Check latency and queue metrics.
6. Verify artist-facing wording and non-modal behavior.
7. Update the support matrix and owning document.
8. Add or update an ADR for durable decisions.

## Security invariants

- Never execute arbitrary network-provided Python.
- Never use pickle or unsafe deserialization on network input.
- Validate protocol version, message type, size, schema, session, and capability before application.
- Do not expose unrestricted shell, filesystem, environment, import, expression, or asset-library operations.
- Treat names, paths, labels, and presence strings as untrusted input.

## Definition of done

A collaboration change is done only when:

- the supported behavior and unsupported boundary are explicit;
- local, canonical, and remote paths are covered;
- duplicates, gaps, reconnect, scene replacement, and cleanup are considered;
- HDK/HOM behavior is verified rather than assumed;
- main-thread and ABI boundaries remain narrow;
- relevant convergence and regression tests pass;
- the UI remains responsive and truthful;
- failure preserves or clearly protects artist work;
- documentation and capability negotiation match the code;
- no unrelated architectural churn is included.

When uncertain, choose the implementation that is easiest to explain, disable, and recover during a real production session.
