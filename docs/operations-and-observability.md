# Operations and observability

A collaboration system is only maintainable when failures can be diagnosed without reproducing the exact artist session.

## Health dimensions

Track these separately.

### Transport health

Examples:

- disconnected;
- connecting;
- connected;
- reconnecting;
- backpressured;
- closed by peer;
- protocol error.

### Synchronization health

Examples:

- unknown;
- joining;
- catching up;
- synchronized;
- degraded;
- reconciliation required;
- fatal.

### Local work health

Examples:

- no pending operations;
- pending confirmation;
- retrying;
- rejected local work;
- preserved recovery artifact.

A single green “connected” indicator is insufficient.

## Structured logging

Logs should be structured or consistently key-value formatted.

Include when relevant:

- session ID;
- client ID;
- connection generation;
- message ID;
- operation ID;
- operation type;
- canonical sequence;
- entity ID;
- last-known Houdini path;
- scene generation;
- retry count;
- queue size;
- recovery state;
- duration;
- error code.

Avoid logging entire snapshots or large payloads by default.

## Log levels

### DEBUG

- callback observed;
- event normalized;
- message framed;
- queue transitions;
- entity resolution details;
- suppression context entry and exit;
- state-machine transitions.

### INFO

- session join/leave;
- connection established/lost;
- catch-up start/finish;
- snapshot checkpoint;
- synchronized state reached;
- supported version negotiation.

### WARNING

- duplicate message;
- deferred dependency;
- slow main-thread apply;
- queue nearing limit;
- reconnect attempt;
- transient heartbeat failure;
- unsupported optional state skipped by policy.

### ERROR

- rejected operation;
- sequence gap;
- failed apply;
- identity mismatch;
- invalid message;
- snapshot failure;
- callback cleanup failure.

### CRITICAL

- contradictory canonical history;
- unrecoverable divergence;
- snapshot integrity failure;
- security boundary violation;
- state machine impossible transition.

## Correlation

A single artist action may produce:

- Houdini callback;
- normalized operation;
- submit message;
- accepted operation;
- remote application on several clients.

Preserve operation ID across these records.

Use message ID for each transport envelope and canonical sequence after acceptance.

## Metrics

### Phase-3 native adapter diagnostics

`hou.coophou_native_capture_state()` now exposes bounded, content-free native
diagnostics: capture/apply queue sizes and overflow flags, reconciliation
state, scene generation, events seen/ignored, expected remote echoes and
internal identity events suppressed, settle count, mirrored-node/tombstone
counts, callback-handler nanosecond total/max, and supported-snapshot
extraction count/total/max. These counters contain no parameter values or node
names.

Capture records carry capture sequence, scene generation, affected scopes,
and cumulative event/settle counts. Apply results preserve correlation,
transaction, operation, operation-index, and scene-generation context. Queue
overflow, stale generation, schema failure, prevalidation failure, semantic
mismatch, and unexpected partial application have stable structured error
codes. Normal production operation no longer prints an unbounded HDK trace;
probe stdout is explicit opt-in.

The Phase-3 benchmark consumes these counters. They are local diagnostics, not
proof of transport or synchronization health, and no UI status is implemented
in this phase.

Additional Houdini and UX metrics:

- callback duration by event type and adapter;
- observation-to-normalization latency;
- event-loop wakeup delay;
- main-thread apply slice duration;
- overlay composition/redraw duration;
- presence messages sent/dropped/coalesced;
- gesture durable commits;
- capability mismatch count;
- HDK bridge load/rejection/fallback;
- stale scene-generation work discarded;
- recovery artifacts created.

Alert on sustained main-thread slices above the release budget, not only on network errors.

Even a local prototype benefits from counters and timings.

Recommended metrics:

- captured operations by type;
- accepted and rejected operations;
- duplicate operations;
- sequence gaps;
- reconnect count;
- catch-up duration;
- pending local count;
- outgoing and incoming queue depth;
- deferred dependency count and age;
- operation apply duration by type;
- main-thread scheduling delay;
- snapshot creation/install duration;
- callback registrations;
- active worker/thread count;
- fatal reconciliation count.

Metrics must not expose private scene content.

## Tracing operation timelines

Provide a diagnostic view or log query that reconstructs:

```text
captured
→ queued
→ sent
→ accepted at sequence N
→ received
→ scheduled
→ applied
→ confirmed
```

For failure:

```text
received
→ apply attempted
→ entity mismatch
→ sequence blocked
→ reconciliation required
```

Do not overwrite earlier status in a way that destroys the timeline.

## Artist-facing status

A useful Houdini panel should show:

- collaboration session;
- transport state;
- synchronization state;
- last confirmed sequence;
- pending local operation count;
- catch-up progress;
- latest actionable error;
- safe actions such as reconnect, preserve work, or leave session.

Use plain language:

> Connected, applying 14 missed edits.

> Collaboration paused because node identity could not be verified. Your local scene was preserved.

Avoid:

> Error 500.

## Diagnostic bundles

A user-triggered diagnostic export may include:

- recent structured logs;
- protocol and application versions;
- Houdini and Python versions;
- health-state history;
- operation metadata with payload redaction;
- queue statistics;
- callback registration counts;
- snapshot/checkpoint metadata without the scene unless explicitly included.

Never include credentials or unrestricted environment dumps.

## Incident runbook

### Client is connected but not synchronized

1. Check last confirmed and last received sequence.
2. Look for a gap or failed operation.
3. Check pending local operations.
4. Check main-thread application queue.
5. Check scene generation mismatch.
6. Request history or reconciliation.
7. Do not force the status indicator to green.

### Operations are duplicated

1. Compare operation IDs and canonical sequences.
2. Verify resend preserves operation ID.
3. Verify applied-operation retention.
4. Check reconnect replay boundaries.
5. Confirm duplicate apply is idempotent.
6. Treat same ID/different payload as corruption.

### Remote edits loop between clients

1. Inspect remote-apply suppression context.
2. Verify callback observes operation ID/entity scope.
3. Check nested application and exception cleanup.
4. Check asynchronous callback timing.
5. Disable collaboration before the loop freezes Houdini.
6. Add a regression test.

### Client freezes Houdini

1. Inspect main-thread queue depth.
2. Look for network waits or `sleep` on the main thread.
3. Measure operation application duration.
4. bound per-tick work.
5. coalesce only semantically safe events.
6. preserve failure visibility while throttling.

### Node receives an edit intended for a deleted node

1. Stop synchronization.
2. Inspect entity ID and path reuse.
3. Verify resolver did not use path-only fallback.
4. preserve the scene.
5. reconcile from a trustworthy checkpoint.
6. add path-reuse regression coverage.

## Data retention

Define retention for:

- client logs;
- server logs;
- operation history;
- applied operation IDs;
- checkpoints;
- recovery artifacts;
- diagnostic bundles.

Retention must balance recovery needs, disk usage, and scene confidentiality.
