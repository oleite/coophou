# Attached sketch audit

This audit maps the original sketch to the engineering roadmap. Phase 0/1 subsequently validated and corrected it against Houdini 21.0.729 on Windows. Items below marked complete describe the current probe; later architecture remains unimplemented.

## Preserve

The sketch contains several useful foundations:

- a CMake HDK plugin and reusable native core target;
- real Houdini/gtest initialization through `MOT_Director`;
- a global `OP_Director` watcher experiment;
- a HOM callback experiment;
- a multi-Houdini launcher;
- main-thread remote apply through `hou.ui.postEventCallback`;
- undo suppression for remote application;
- an early network cursor overlay experiment.

Do not discard these merely to create a cleaner architecture diagram.

## Refactor first

### `coophou/client/sender.py`

Convert this file from a synchronization sender into a temporary HOM event-probe adapter.

Phase-1 disposition — **complete**:

- remove only coophou-owned event-loop and node callbacks;
- make `start()`/`stop()` idempotent;
- retain exact callback keyword shape without stringifying ambiguous data too early;
- attach local observation number and scene generation;
- write JSONL trace records;
- preserve deletion identity before the object disappears;
- do not emit network operations yet.

### `src/watcher.*`

Convert `Watcher` into an idempotent native trace source.

Phase-1 disposition — **complete**:

- store registration state;
- stop safely;
- log structured records rather than only formatted text;
- never retain `OP_Node *` or callback payload pointers beyond the callback;
- treat payload meaning as event-specific and target-build-specific;
- add start/stop/restart tests;
- remove direct inclusion of `watcher.cpp` from tests.

### `src/event_manager.*`

Do not fill every handler with guessed synchronization payloads.

Phase 1 now supplements `EventManager` with an observation serializer that reveals:

- event reason;
- safe node/parent path at callback time;
- event-specific numeric/index fields;
- stable identity user data if available;
- undo/redo state if accessible;
- scene generation;
- local observation order.

Operation extraction comes after trace review.

### `coophou/client/eventTranslation.py`

Freeze this as legacy sketch code during the probe milestone.

Do not expand `asData`/`setFromData` into the new protocol. The new operation model should later live in portable modules independent of HOM.

### Transport and server

Do only what the probe needs:

- either disable network transmission for probe mode; or
- add minimal explicit framing if traces are sent to a separate process.

Do not implement canonical history, snapshots, or presence before the event matrix exists.

## Suggested probe output

Use one JSON object per line:

```json
{
  "trace_version": 1,
  "adapter": "hom",
  "scenario": "rename_node",
  "houdini_version": "verified at runtime",
  "platform": "verified at runtime",
  "scene_generation": 1,
  "observation": 17,
  "event": "NameChanged",
  "node_path": "/obj/geo1/box_new",
  "entity_id": null,
  "payload": {},
  "undo_state": "unknown"
}
```

Store generated traces under a clearly generated/fixture-oriented path such as:

```text
tests/fixtures/events/<houdini-api>/<platform>/<adapter>/<scenario>.jsonl
```

Choose the exact path once, then document it.

## Probe scenarios

At minimum:

- create ordinary node;
- create and immediately change defaults;
- copy/paste one node;
- copy/paste a connected subtree;
- delete one node;
- delete a subnet;
- rename;
- move by dragging;
- connect and disconnect;
- edit an integer, float, toggle, string, menu, and tuple;
- undo and redo every supported edit;
- save/load/merge/clear;
- locked-HDA boundary;
- remote application under suppression;
- repeated start/stop/reload.

## Static conclusions corrected by runtime evidence

- HOM `BeingDeleted` and `ChildDeleted` preserve the path at callback time, but persistent user data is already unavailable in the tested immediate deletion. The probe therefore needs its plain-data snapshot cache. HDK `OP_NODE_PREDELETE` still exposes the ID before `OP_NODE_DELETED` clears it.
- `hou.copyNodesTo` duplicated `coophou.entity_id` for one node and a connected subtree. It also produced transient/final rename and wiring bursts, confirming collision repair must happen before a single paste transaction is submitted.
- A tuple `set()` produced one callback per changed component in both HOM and HDK, not one tuple-level semantic edit.
- `setPosition()` produced two HOM `PositionChanged` / HDK `OP_UI_MOVED` observations, including parent-network noise. Position must be coalesced and filtered.
- HDK global capture is substantially noisier than HOM during creation and HDA locking. `OP_PARM_VISIBLE_CHANGED`, `OP_PARM_ENABLE_CHANGED`, UI, and channel events cannot be treated as operations.
- A load nests a clear. Scene generation advances once for the replacement, not once for both lifecycle labels.
- HDK can determine `undo_or_redo` during the callback through `UTperformingUndoRedo`; tested HOM exposes no equivalent callback-time state.

## Stop condition

The first milestone is complete for Houdini 21.0.729/Windows and has produced evidence and a recommendation.

It should **not** continue directly into a full protocol implementation. Human review should select:

- authoritative v1 events;
- transaction boundaries;
- identity insertion point;
- unsupported callbacks;
- HOM versus HDK responsibility.

That review prevents the first elegant implementation from encoding the wrong Houdini assumptions.
