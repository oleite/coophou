# ADR 0001: Keep the HDK bridge thin

- **Status:** Accepted
- **Date:** 2026-07-17
- **Owners:** coophou maintainers
- **Supersedes:** None
- **Superseded by:** None

## Context

coophou needs deeper event coverage and efficient integration with Houdini's main loop, but HDK DSOs are ABI-sensitive and must be built for supported Houdini/platform/compiler combinations.

Putting protocol, recovery, or canonical-session logic in the DSO would make product iteration and compatibility unnecessarily expensive.

## Decision

Use a thin HDK bridge only for:

- global operator-change observation;
- scene lifecycle observation;
- efficient event-loop wakeup;
- bounded native queues;
- measured native hot paths that cannot meet budgets through HOM.

Keep these in portable code:

- protocol;
- operation/transaction schemas;
- canonical ordering;
- pending local state;
- conflict policy;
- recovery;
- presence;
- UI models;
- most tests.

The bridge emits plain observations through a narrow versioned interface. It never owns canonical state.

## Consequences

Phase 2 implements the operation, transaction, authority, client recovery, and
fault-simulation logic in `coophou/core/`. Importing that package in ordinary
Python loads no `hou`, Qt, socket, or native-binding dependency. This is direct
evidence that the portable/native boundary in this decision is workable; the
Phase 1 DSO remains an observation probe and owns no canonical state. ADR 0005
extends this decision by making the thin native bridge the production Houdini
adapter for supported capture and application while preserving this ownership
boundary.

### Positive

- product logic remains testable without Houdini;
- native and any capability-gated fallback adapters can share contracts;
- ABI rebuilds affect a small component;
- native crashes have a smaller blast radius;
- platform packaging is manageable.

### Negative

- language-boundary queue and binding code is required;
- some event normalization may need a round trip into portable code;
- every native build or fallback adapter requires conformance tests.

## Compatibility

Package one DSO per supported `HDK_API_VERSION`, platform, and compatible
compiler family. Refuse unsupported native loading. Use a HOM fallback only
where explicit capabilities and independent conformance evidence prove the
requested operation surface.

## Testing

- native operation conformance against the portable contract and preserved
  event-probe evidence;
- runtime API-version rejection;
- queue overflow;
- scene replacement with queued observations;
- start/stop/reload cleanup;
- native bridge absence and capability-gated fallback behavior.
