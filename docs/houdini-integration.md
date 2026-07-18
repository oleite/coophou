# Houdini integration

This document covers requirements at the boundary between coophou and SideFX Houdini.

## Prime directive

## Adapter strategy

The default architectural direction is:

- an HDK/C++-first production adapter for supported observation, identity,
  scoped extraction, application, and verification;
- a narrow, versioned, bounded plain-data bridge to the portable core;
- HOM for PySide6 UI, fixtures, diagnostics, independent test oracles, and
  explicitly capability-gated fallback behavior;
- one native ordered main-thread application gateway.

The HDK bridge must not own protocol, canonical ordering, conflict rules,
recovery policy, transport, presence, or UI models.

See [hdk-hom-feasibility.md](hdk-hom-feasibility.md), ADR 0001, and ADR 0005.

## Implemented Phase-3 adapter

`src/native_adapter.cpp` is the Houdini-specific implementation for the exact
21.0.729 Windows target. The installed `CoopHou.dll` registers ten prefixed
JSON functions on `hou` through `HOMextendLibrary`; this is a language bridge,
not HOM scene application. `coophou/houdini_adapter/bridge.py` performs lazy
plain-data calls, `projection.py` normalizes the configured native root to the
synthetic Phase-2 root, and `orchestrator.py` owns operation/transaction IDs and
single-process portable confirmation.

The native adapter holds a bounded supported-state mirror, ID lookup data,
tombstones, affected scopes, expected-echo/internal-identity classification,
capture/apply queues, and scene generation. Callbacks mark evidence and copy
pre-delete IDs; an explicit settle reads the configured supported scope once,
repairs new collisions, coalesces final values, diffs against the mirror, and
emits plain operation candidates without operation IDs. Native application
prevalidates the whole transaction against a staged abstract snapshot, applies
in order on the main thread, extracts again, and returns success only after a
semantic comparison.

This implementation deliberately has no automatic event-loop drain yet. Phase
3 tests call settle/apply drains explicitly; Phase 4 may add one bounded native
wakeup owner when real session transport exists. No networking wait or Python
callback occurs per raw HDK event.

Houdini is an interactive application with thread-affine APIs and complex event behavior. Treat integration code as an adapter around the collaboration core, not as the place where protocol and recovery policy accumulate.

## Thread affinity

### HDK event-loop integration

`FS_EventGenerator` is the preferred native integration point when an HDK bridge needs to wake Houdini efficiently.

A portable design is:

1. network worker writes plain messages to a bounded queue;
2. a pipe/socket/event signal wakes an `FS_EventGenerator`;
3. `processEvents()` runs on Houdini's event loop;
4. it schedules or drains a bounded application slice;
5. Houdini returns to ordinary UI processing.

A HOM fallback may drain a bounded queue through one `hou.ui.addEventLoopCallback` or one-shot `postEventCallback`.

Do not register one idle callback per feature.

Assume:

- `hou` scene reads and writes that participate in synchronization belong on Houdini's main thread;
- Qt widget access belongs on the UI thread;
- networking, framing, compression, and durable queue work must not block the main thread.

A background worker may:

- receive bytes;
- validate basic framing;
- deserialize plain data;
- enqueue work;
- write outgoing bytes;
- maintain heartbeat timing.

It must not mutate Houdini scene state.

### Main-thread scheduling

Use one well-defined scheduling gateway. It should:

- accept plain-data application requests;
- reject work for stale scene/session generations;
- preserve canonical order;
- surface exceptions;
- avoid unbounded per-frame work;
- permit shutdown without applying stale queued operations.

Do not scatter several incompatible timer and event-loop mechanisms across modules.

## Callback lifecycle

Every callback registration needs:

- an owner;
- an idempotent `start`;
- an idempotent `stop`;
- stored registration handles or exact removal information;
- scene-generation awareness;
- tests for repeated initialization.

Lifecycle events to handle explicitly:

- package load;
- UI creation;
- collaboration connect;
- collaboration disconnect;
- `.hip` clear;
- `.hip` load;
- `.hip` save;
- Python module reload;
- panel close;
- Houdini exit.

Do not assume process exit is the only cleanup path.

## Event capture

### Global HDK capture

`OP_Director::addGlobalOpChangedCallback` is the primary production evidence
source for broad supported operator changes. `OP_Node::addOpInterest` is
available for targeted observations.

Do not assume the callback reason maps one-to-one to the desired operation. Feed it through the event probe and normalization layer.

Do not enqueue raw `OP_Node*` values. During the callback, resolve all information needed after return. Deletion and scene replacement invalidate pointers.

### HOM diagnostics and fallback

`hou.OpNode.addEventCallback` is session-local and may be used by probes,
fixtures, independent test oracles, or an explicitly capability-gated fallback.
Production capture must not depend on it.

HOM callbacks can report:

- `ChildCreated`/`ChildDeleted`;
- `NameChanged`;
- `PositionChanged`;
- `InputRewired`;
- `ParmTupleChanged`;
- selected flag and network-item changes.

A bulk parameter event may provide `parm_tuple=None`; request a bounded node diff instead of guessing.

Both HDK and HOM callbacks are implementation signals, not semantic operations.

Capture code should:

1. receive the callback;
2. exit quickly if collaboration is inactive or the event is a known remote echo;
3. copy safe immediate identity and event context, including pre-delete data;
4. attach scene/session generation and mark a bounded affected scope when a
   settle read is required;
5. enqueue evidence for native aggregation and supported-state extraction;
6. return control to Houdini.

Avoid:

- socket I/O inside callbacks;
- waiting for server acknowledgement;
- full-scene scans for every event;
- broad exception suppression;
- operations whose payload contains `hou` objects.

## Event normalization

One user gesture may produce multiple callbacks. Normalize based on semantic intent.

Questions for every captured event:

- Is it supported?
- Does it describe a final state or an intermediate state?
- Is before-state required?
- Could it be an echo of remote application?
- Does it depend on another event?
- Can it be coalesced without changing semantics?
- Is the target identity stable?
- Does Houdini emit a corresponding event for undo and redo?

Maintain a table of callback-to-operation mappings in the repository.

## Stable identity in Houdini

### v1 node identity decision

ADR 0002 proposes persistent user data as the v1 carrier.

Use a namespaced key and store only a UUID or versioned small string. Internal identity writes:

- are applied with metadata-capture suppression;
- should not appear in the activity feed;
- must not be interpreted as arbitrary custom-data collaboration.

After copy/paste, scan only the newly created transaction scope for duplicate IDs and replace them before submission.

The identity mechanism must be persistent enough for the supported collaboration lifecycle.

Possible storage locations should be evaluated for:

- save/load persistence;
- copy/paste behavior;
- node duplication;
- locked digital assets;
- editable nodes inside assets;
- deletion;
- undo/redo;
- performance;
- visibility to artists;
- namespace collision.

A node user-data field may be appropriate, but it is a design choice requiring verification and an ADR.

### Identity cache

If entity ID to `hou` object/path resolution is cached:

- the Houdini adapter owns the cache;
- rename updates path metadata;
- deletion invalidates the entity;
- parent deletion invalidates descendants;
- scene load resets the cache;
- undo/redo invalidates or repairs affected entries;
- cache misses may trigger bounded lookup;
- identity mismatch never falls back silently to a reused path.

## Remote-apply context

All remote mutation must enter a scoped context.

The context should be:

- exception-safe;
- nesting-safe;
- limited to one scene/session generation;
- observable in logs;
- capable of distinguishing expected echoes from unrelated local events.

Conceptual behavior:

```python
with remote_apply_context(
    operation_id=operation.id,
    entity_ids=operation.affected_entity_ids,
    scene_generation=current_scene_generation,
):
    apply(operation)
```

Do not leave suppression active while waiting for network I/O.

## Undo and redo

ADR 0003 proposes the v1 behavior:

- remote apply runs with undo creation disabled;
- local Houdini undo/redo remains available;
- resulting callbacks become a new collaborative transaction;
- the transaction is labeled as undo/redo when the adapter can prove that context.

This must be validated through the HDK/HOM event probe. Bulk or unsupported undo results require reconciliation.

Alternative future models include:

### Remote edits excluded from local undo

Advantages:

- avoids undoing another artist's work locally;
- simpler canonical behavior.

Risks:

- Houdini APIs may still create undo entries unless explicitly controlled;
- artists may find mixed history confusing.

### Remote edits grouped in local undo

Advantages:

- visible local history.

Risks:

- local undo may diverge from canonical state unless undo itself emits collaborative inverse operations.

### Collaborative undo

Undo requests become canonical operations referencing prior accepted operations.

Advantages:

- shared semantics.

Risks:

- substantially more complex;
- inverse operations may not be safe after later dependent edits.

The current policy must be recorded in `current-state.md` and an ADR. New operation types must follow it.

## Houdini names and implicit behavior

Avoid depending on Houdini-generated names where the name affects synchronized state.

For node creation, consider capturing or deriving:

- operator type;
- intended parent entity;
- stable entity ID;
- exact requested name;
- final canonical name;
- position;
- initialization parameters that affect state.

When Houdini changes a requested name to avoid collision, the canonical result must be propagated explicitly.

## Parameter semantics

A parameter is not always a scalar value.

Distinguish:

- raw value;
- evaluated value;
- expression text;
- expression language;
- keyframes;
- channel references;
- multiparm instances;
- tuple components;
- menu token versus label;
- time-dependent values;
- disabled or hidden state;
- spare parameter schema.

Do not synchronize an evaluated number when the artist changed an expression.

## Connections and structural edits

Connection operations should identify:

- source entity;
- source output index or named output;
- destination entity;
- destination input index;
- ordered versus unordered semantics;
- pre-existing connection precondition.

Structural edits may invalidate later operations. Preserve canonical order and classify missing dependencies rather than guessing.

## Scene generations

Introduce a monotonically increasing local `scene_generation` whenever a new `.hip` state replaces the old one.

Queued work should carry the generation it belongs to.

Reject or discard stale work after:

- opening a different scene;
- clearing the scene;
- installing an authoritative snapshot;
- disconnecting and joining another collaboration session.

This prevents late callbacks or queued remote operations from mutating a new scene.

## Snapshots

### `.hip` format caution

Houdini scene files are CPIO-based archive-like containers; text save mode makes their members inspectable, but it does not create a safe merge format.

Do not:

- diff or merge text `.hip` files as ordinary source text;
- make archive member order part of protocol semantics;
- treat a text-mode save as an operation log.

Prefer an explicit operation history plus a checkpointed recovery snapshot.

### Safe snapshot API choice

A plain `hou.hipFile.save(temp_path)` has Save As semantics and may retarget the current scene path. Do not use it blindly for background checkpoints.

Evaluate and test a save-copy strategy such as `hou.hipFile.saveAsBackup()` or an equivalent HDK path that preserves:

- current scene name;
- recent-file list;
- dirty state semantics;
- autosave behavior;
- user callbacks;
- `$HIP`-dependent paths.

The chosen method requires an ADR and integration tests on all target builds.

A snapshot is a recovery artifact, not the ordinary synchronization protocol.

Snapshot creation must:

- use a unique temporary path;
- avoid overwriting the working file;
- preserve the artist's current file name and dirty state when possible;
- record Houdini version and protocol/checkpoint metadata;
- report failure;
- clean up according to a retention policy;
- avoid exposing arbitrary filesystem paths to remote peers.

Snapshot installation must:

- require an explicit recovery state;
- stop or isolate callbacks;
- invalidate scene generation;
- reset identity caches;
- validate session and checkpoint;
- replay accepted operations after the checkpoint;
- surface failure as fatal or user-action-required.

Houdini scene files are archive-like containers; do not assume that “ASCII mode” makes arbitrary textual merging safe.

## UI integration

### Network-editor overlays

Presence should use a single overlay composition owner around `hou.NetworkEditor.setOverlayShapes`.

Do not use actual node colors, comments, selection, or flags for passive presence.

Do not globally push a custom network-editor event context unless implementing an explicit user-invoked interaction mode such as follow or annotation. Passive cursor display needs observation, not event consumption.

The UI should remain responsive and show separate states for:

- transport;
- synchronization;
- recovery;
- local pending operations;
- fatal errors.

Routine reconnect should not create repeated modal dialogs.

Provide actionable details such as:

- last confirmed sequence;
- pending count;
- failed operation ID;
- affected node path;
- recovery action.

Do not expose raw stack traces as the only artist-facing explanation.
