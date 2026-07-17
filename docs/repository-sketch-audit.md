# Attached sketch audit

This audit maps the current code to the engineering roadmap. It is intentionally static: validate every claim through the target Houdini build.

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

Required immediate changes:

- remove only coophou-owned event-loop and node callbacks;
- make `start()`/`stop()` idempotent;
- retain exact callback keyword shape without stringifying ambiguous data too early;
- attach local observation number and scene generation;
- write JSONL trace records;
- preserve deletion identity before the object disappears;
- do not emit network operations yet.

### `src/watcher.*`

Convert `Watcher` into an idempotent native trace source.

Required immediate changes:

- store registration state;
- stop safely;
- log structured records rather than only formatted text;
- never retain `OP_Node *` or callback payload pointers beyond the callback;
- treat payload meaning as event-specific and target-build-specific;
- add start/stop/restart tests;
- remove direct inclusion of `watcher.cpp` from tests.

### `src/event_manager.*`

Do not fill every handler with guessed synchronization payloads.

For Phase 1, replace or supplement `EventManager` with an observation serializer whose purpose is to reveal:

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

## Stop condition

The first milestone is complete when it produces evidence and a recommendation.

It should **not** continue directly into a full protocol implementation. Human review should select:

- authoritative v1 events;
- transaction boundaries;
- identity insertion point;
- unsupported callbacks;
- HOM versus HDK responsibility.

That review prevents the first elegant implementation from encoding the wrong Houdini assumptions.
