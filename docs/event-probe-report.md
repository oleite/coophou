# Phase 0/1 Houdini event-probe report

## Scope and target

This report stops at evidence gathering. It defines no synchronization protocol, canonical server, persistent operation schema, recovery snapshot, or collaboration UI.

Verified target:

- Houdini 21.0.729, `HDK_API_VERSION=21000693`;
- Windows `10.0.26200`, x86-64;
- Houdini Python 3.11.7;
- Qt/PySide 6.5.3;
- MSVC 19.44.35228, toolset 14.44.35207;
- Windows SDK 10.0.26100.0.

Each scenario ran in a fresh headless `hython` process against an empty scene. HOM and HDK wrote the same trace schema under `tests/fixtures/events/houdini-21.0.729/hdk-api-21000693/windows/`. The generated side-by-side sequence table is in `docs/event-probe-comparison.md`.

## Scenario result

All 15 scripted scenarios completed through both adapters:

- create; create and immediately modify;
- copy one node; copy a connected subtree;
- delete one node; delete a subnet;
- rename; scripted move; connect/disconnect;
- integer, float, toggle, string, menu-token, and tuple parameters;
- undo/redo of create, delete, rename, move, parameter, connect, and disconnect candidates;
- save, load, merge, and clear;
- locked-HDA permission boundary;
- temporary remote-application suppression;
- repeated start/stop and Python module reload.

The move and copy scenarios used HOM scripting (`setPosition` and `hou.copyNodesTo`), not physical Network Editor dragging or clipboard UI. Those interaction traces remain unverified.

## Important findings

### Creation and paste

A simple object-node create produced one HOM `ChildCreated`, but 27 total HDK observations. The native stream included `OP_CHILD_CREATED` plus repeated parameter-visibility, parameter-enable, input, and spare-parameter notifications. These are initialization noise, not 27 user operations.

Create followed immediately by a tuple modification produced `ChildCreated` followed by three component-level parameter callbacks in both adapters. Creation needs a bounded settle/collection point before a semantic transaction can be formed.

Copying one node and copying a connected subtree duplicated the persistent `coophou.entity_id` values. Copy also emitted transient and final paths, rename, flag, appearance, input, and wiring events. Path cannot identify the copied entity, and collision repair must precede submission.

Recommended boundary: one create transaction for an ordinary node after allowlisted initialization settles; one atomic topologically ordered transaction for a copied subtree, including new IDs and internal wires.

### Deletion

HOM emitted `BeingDeleted` and then parent `ChildDeleted`. The node path remained available, but user data was already cleared in the immediate callback. The HOM probe recovered the stable ID from its main-thread plain-data cache. HDK emitted `OP_NODE_PREDELETE` with the stable ID, followed by `OP_NODE_DELETED` without it and parent `OP_CHILD_DELETED`.

Subnet deletion emitted descendant pre-delete/delete events before the parent sequence. Treating each callback as an independent delete would expose invalid intermediate state.

Recommended boundary: capture IDs and descendant tombstones at pre-delete, then submit one root delete transaction. Never resolve a later delete by the old path.

### Rename and position

The simple rename produced one HOM `NameChanged` with `old_name` and the final node path, and one HDK `OP_NAME_CHANGED`. Stable ID is still the target; the path is diagnostic.

One scripted `setPosition()` produced two HOM `PositionChanged` and two HDK `OP_UI_MOVED` observations, one involving parent-network noise. A physical drag may be much noisier.

Recommended boundary: one final rename; one coalesced final node position per gesture, after filtering parent/network noise.

### Connections

Connect and disconnect each produced one destination rewire callback per adapter. HOM supplied destination `input_index`; the probe's callback-time read distinguished the connected source/output from `null` after disconnect. The callback did not supply a trustworthy before-source.

Recommended boundary: one destination-input operation carrying cached expected source and callback-time final source/output. Precondition failure must not silently replace an unrelated wire.

### Parameters

The probe preserved raw and evaluated forms. Notable examples:

- toggle raw value `on`, evaluated value `1`;
- menu raw token `mesh`, evaluated index `2`;
- fixed tuple changes emitted intermediate component states before `(2, 3, 4)`.

No tested gesture produced `parm_tuple=None`, so bulk callback normalization is still unresolved and remains explicitly `bulk_or_ambiguous` in the schema.

Recommended boundary: one simple raw tuple set per gesture/undo block after coalescing component callbacks. Use menu tokens, never display labels or evaluated integer indices. Expressions, animation, multiparms, spare schemas, and bulk-unknown changes remain outside v1.

### Undo and redo

The scripted candidate actions emitted corresponding reverse/forward event bursts. The native probe marked 45 observations as `undo_or_redo` using `UTperformingUndoRedo`; tested HOM exposes no documented callback-time distinction, and the native API does not distinguish undo from redo in this probe.

Recommended boundary: one transaction per local undo-stack action only after a boundary/correlation source is proven. Do not infer undo solely from matching inverse values.

### Scene lifecycle and suppression

Save/load/merge/clear produced matching before/after lifecycle events. Load nested a clear. The probe advances scene generation once for the complete replacement and does not advance it for save or merge.

The temporary HOM suppression context remained active across all three tuple-component callbacks and restored depth after exceptions in unit tests. The native observer cannot yet see Python suppression metadata.

Recommended boundary: clear/load are generation barriers, not scene operations. Merge must either normalize to bounded create transactions or require reconciliation. A future shared application gateway must make suppression/correlation visible to whichever adapter captures events.

### Locked HDA boundary

After `matchCurrentDefinition()`, the test asset was locked, its internal node reported `isEditableInsideLockedHDA() == false`, and mutation raised `hou.PermissionError`.

Recommended boundary: reject locked-internal edits. HDA definition editing and locked internals remain unsupported.

## HOM/HDK division suggested by evidence

HOM currently provides the safer semantic starting point for Phase 3: named parameter tuples with raw values, input indices plus readable final connections, `old_name`, editability checks, and easy scoped suppression metadata.

HDK provides broader lifecycle/global coverage, pre-delete identity, and undo/redo-in-progress detection, but its event stream is much noisier and all `void *data` meanings remain unverified. Keep it as a thin observation source; do not move transaction or protocol rules into the DSO.

## Unresolved ambiguities

- actual UI drag cadence and mouse-release boundary;
- clipboard paste ordering and the exact event-loop turn when a copied subtree is complete;
- every HDK `void *data` payload meaning and nullability;
- reliable HOM undo-versus-redo labeling and transaction boundary;
- generation of a real `parm_tuple=None` bulk callback;
- allowlisted node-flag semantics independent of create/copy noise;
- native visibility of remote-application suppression;
- DSO unload/reload behavior;
- behavior on Linux, macOS, and other Houdini builds;
- larger queues and performance under interactive artist workloads.

## Recommended initial v1 boundary

Proceed only with ordinary node-graph authoring:

1. create one ordinary node after bounded initialization collection;
2. create one copied subtree as an atomic topological transaction after ID repair;
3. delete one node/subtree as one tombstoned transaction;
4. rename one node;
5. coalesce a node move to the final position;
6. connect or disconnect one destination input with an expected-source precondition;
7. set one simple, raw, unanimated/unexpressed parameter tuple.

Keep node flags out of the first contract until isolated probes prove an allowlist. Treat clear/load as generation barriers, merge as reconciliation-sensitive, presence as separate, and every excluded family in the support matrix as unsupported.

## Exact next milestone

After human review accepts these boundaries, execute Phase 2 only: build the portable deterministic core without Houdini—versioned operation/transaction schemas, stable entity references, fake scene/authority/transport, canonical sequence and pending-local state machines, idempotency, gap detection, duplicate handling, and fault/reconnect tests. Do not connect these probes to the legacy relay during that milestone.
