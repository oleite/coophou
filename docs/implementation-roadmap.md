# Implementation roadmap

This roadmap proves the risky Houdini assumptions before building a large distributed system.

## Phase 0 — repository and target declaration

### Deliverables

- supported Houdini version/build/platform table;
- Python and Qt versions;
- package layout and startup method;
- test commands;
- server/client entry points;
- explicit v1 operation list;
- one sample scene used by every integration test.

### Exit gate

`docs/current-state.md` contains verified evidence instead of unknown placeholders for the target environment.

## Phase 1 — HDK/HOM event probe

Build two probes where practical:

1. HOM callback tracer;
2. HDK global operator-change tracer.

Each trace records:

- event type/reason;
- node path and stable ID;
- parent path;
- event-specific index;
- undo/redo state;
- scene generation;
- callback nesting;
- timestamp and local observation order.

### Scenario matrix

Probe:

- create;
- copy;
- paste;
- duplicate;
- delete;
- subnet delete;
- undo/redo each action;
- rename;
- move;
- wire/unwire;
- supported parameter edits;
- bulk parameter changes;
- scene save/load/merge/clear;
- locked assets;
- module reload;
- application under suppression.

### Exit gate

A checked-in event matrix explains how every v1 candidate becomes a transaction without retaining invalid pointers or relying on paths alone.

No collaboration network is required yet.

## Phase 2 — portable deterministic core

**Status: complete (2026-07-17).** See `docs/phase-2-report.md`.

Implement without Houdini:

- operation and transaction schemas;
- entity references;
- canonical sequence state machine;
- pending local transactions;
- duplicate detection;
- capability handshake;
- fake scene adapter;
- fake authority and transport;
- recovery states.

Transient presence remains deferred because it is explicitly outside the Phase
2 durable-core milestone.

### Exit gate

Deterministic unit, multi-client, and seeded randomized tests pass under
duplicate, dropped, delayed, reordered, rejected, gap, reconnect,
history-unavailable, queue-overflow, and atomic mid-transaction failure
scenarios. The core imports without Houdini. This was the Phase 2 exit state;
Phase 3 is now complete below.

## Phase 3 — single-process Houdini adapter

**Status: complete for Houdini 21.0.729 / Windows (2026-07-17).** See
`docs/phase-3-report.md`.

**Architectural direction accepted by ADR 0005 (2026-07-17):** implement the
production adapter HDK/C++-first behind a narrow, versioned plain-data bridge.

Features:

- identity assignment and collision repair;
- HDK global/lifecycle capture as primary evidence;
- bounded event aggregation and targeted supported-state extraction;
- native normalization input for the frozen Phase 2 operation families;
- ordered, bounded, main-thread native application gateway;
- native remote-apply and internal-identity echo classification;
- semantic post-apply verification and truthful partial-failure reporting;
- scene generation and stale-work rejection;
- thin Python orchestration against a single-process portable authority;
- reproducible native/bridge performance measurements.

Collaboration UI, presence, physical gesture claims, snapshot recovery, and
supported undo/redo behavior are outside this phase.

Use two logical clients against one process only in tests; do not claim multi-user alpha yet.

### Exit gate

Every v1 operation passes:

- local capture and accepted native apply;
- replay;
- scripted copy/generated-subtree identity collision repair;
- scene save/load;
- cleanup/reload;
- permission failure;
- path reuse;
- echo suppression and semantic verification;
- bounded queue and main-thread latency budgets.

## Phase 4 — session authority and two-client alpha

Implement:

- session join;
- compatibility negotiation;
- canonical transaction order;
- history and resume;
- acknowledgement;
- bounded queues;
- real LAN/VPN framing and capability negotiation;
- two real Houdini clients;
- passwordless LAN discovery only after direct-address session behavior is
  trustworthy.

### Exit gate

A scripted two-client test repeatedly:

- joins;
- edits;
- disconnects;
- catches up;
- resends with original IDs;
- detects a gap;
- recovers;
- leaves cleanly.

A 30-minute artist test completes without false synchronized status or lost local work.

## Phase 5 — native packaging and measured expansion

The thin HDK bridge begins in Phase 3. Phase 5 broadens only proven needs:

- efficient native wakeup/event generation when measurements justify it;
- additional supported Houdini/platform builds;
- measured native hot-path optimization;
- capability-gated fallback conformance where useful.

### Packaging

- CMake against Houdini's provided target;
- one binary per supported API/platform/compiler combination;
- runtime `HDK_API_VERSION` check;
- package manifest chooses compatible DSO;
- fallback only when declared capabilities and conformance tests allow it.

### Exit gate

Every added build or fallback passes the same operation conformance and cleanup
contracts, reports exact capabilities, and does not move canonical state into
the DSO. DSO unload remains unclaimed unless safely testable.

## Phase 6 — recovery hardening

Implement:

- checkpoint metadata;
- safe recovery artifact;
- missing-history replay;
- authoritative snapshot path;
- snapshot compatibility/integrity validation;
- bounded deferred dependencies;
- fatal-state UX.

### Exit gate

Fault injection cannot produce a green synchronized state after a failed apply, contradictory history, or incompatible snapshot.

## Phase 7 — delight and scale

Only after correctness gates:

- transient gesture previews;
- follow collaborator;
- remote edit pulses;
- richer activity grouping;
- soft edit intent;
- reduced-motion mode;
- larger sessions;
- performance profiling and selective native optimization.

### Exit gate

UX tests show that added presence improves collaboration without lowering local editing performance or causing scene pollution.

## Features that require a new mini-roadmap

Do not add these as incidental tasks:

- expressions/keyframes;
- multiparms;
- HDA definition collaboration;
- APEX;
- cooked geometry;
- simulation state;
- collaborative branching/merging;
- server persistence across authority restart;
- internet-facing authentication;
- end-to-end encrypted sessions.

Each needs its own feasibility probe, operation contracts, conflicts, recovery, and UX design.

## Alpha definition

An alpha is not “messages appear on two machines.”

It requires:

- explicit target builds;
- v1 support matrix complete;
- event traces checked in;
- stable node identity;
- two-client convergence;
- reconnect/resume;
- clean disconnect;
- truthful UI state;
- local work preservation;
- bounded queues;
- no arbitrary code execution;
- documented known limitations.

## Beta definition

A beta additionally requires:

- automated Houdini integration coverage on supported platforms;
- install/update workflow;
- HDK compatibility checks;
- recovery snapshot path;
- diagnostic bundle;
- performance budgets met;
- real artist study;
- security review for deployment environment;
- migration policy for protocol and entity metadata.
