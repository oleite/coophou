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

Implement without Houdini:

- operation and transaction schemas;
- entity references;
- canonical sequence state machine;
- pending local operations;
- duplicate detection;
- capability handshake;
- fake scene adapter;
- fake authority and transport;
- recovery states;
- transient presence model.

### Exit gate

Property-based and multi-client tests converge under duplicate, dropped, delayed, reordered, rejected, and reconnect scenarios.

## Phase 3 — single-process Houdini adapter

Implement the HOM adapter first unless probe results justify immediate native capture.

Features:

- identity assignment and collision repair;
- capture and normalization;
- ordered main-thread application gateway;
- remote echo suppression;
- scene generation;
- local undo/redo policy;
- collaboration panel;
- overlay composition service;
- event-loop queue draining.

Use two logical clients against one process only in tests; do not claim multi-user alpha yet.

### Exit gate

Every v1 operation passes:

- fresh apply;
- replay;
- undo/redo;
- copy/paste;
- scene save/load;
- cleanup/reload;
- permission failure;
- path reuse;
- UI latency budgets.

## Phase 4 — session authority and two-client alpha

Implement:

- session join;
- compatibility negotiation;
- canonical transaction order;
- history and resume;
- acknowledgement;
- bounded queues;
- lossy presence;
- two real Houdini clients.

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

## Phase 5 — thin HDK bridge

Move only proven needs into a versioned DSO:

- global OP capture if it materially improves coverage;
- scene lifecycle capture;
- efficient native wakeup/event generator;
- bounded native queues;
- narrow HOM extension or equivalent bridge API.

### Packaging

- CMake against Houdini's provided target;
- one binary per supported API/platform/compiler combination;
- runtime `HDK_API_VERSION` check;
- package manifest chooses compatible DSO;
- HOM-only fallback when capability allows.

### Exit gate

The native bridge produces the same observation contracts as HOM, passes the same trace tests, unloads/cleans up safely where supported, and does not own canonical state.

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
