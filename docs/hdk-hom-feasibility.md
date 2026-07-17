# HDK and HOM feasibility

## Verdict

The proposed coophou architecture is feasible for a deliberately limited Houdini node-graph collaboration surface.

Houdini's public APIs provide the required building blocks:

- global and per-node operator-change notifications;
- scene load, save, merge, and clear lifecycle callbacks;
- a main event loop and custom event generators;
- persistent per-node user data;
- undo grouping and suppression;
- Python panels and network-editor overlay shapes;
- node creation, deletion, naming, positioning, parameters, and wiring APIs.

What cannot be guaranteed from documentation alone is the exact event trace for every operation, Houdini context, undo/redo action, copy/paste path, and build. The architecture therefore requires an event-probe milestone before claiming production support.

## Official SideFX API basis

### Event capture

- [`OP_Director::addGlobalOpChangedCallback`](https://www.sidefx.com/docs/hdk/class_o_p___director.html) provides a process-wide HDK notification hook for operator changes.
- [`OP_Node::addOpInterest`](https://www.sidefx.com/docs/hdk/class_o_p___node.html) provides targeted HDK notifications for a node.
- [`hou.OpNode.addEventCallback`](https://www.sidefx.com/docs/houdini/hom/hou/OpNode.html) provides session-local HOM callbacks.
- [`hou.nodeEventType`](https://www.sidefx.com/docs/houdini/hom/hou/nodeEventType.html) includes node creation/deletion through parent callbacks, rename, position, input rewiring, parameter changes, flags, and several network-item changes.

Important caveat: a parameter callback may receive `parm_tuple=None` when many parameters change. Bulk events require diffing against a known mirror or a transaction snapshot.

### Scene lifecycle

- [`OP_Director::addEventCallback`](https://www.sidefx.com/docs/hdk/class_o_p___director.html) exposes clear, load, merge, and save lifecycle events to HDK code.
- [`hou.hipFile.addEventCallback`](https://www.sidefx.com/docs/houdini/hom/hou/hipFile.html) exposes corresponding HOM lifecycle events.
- Callbacks are session registrations and require explicit cleanup.

### Main-loop integration

- [`FS_EventGenerator`](https://www.sidefx.com/docs/hdk/_h_d_k__event_generator.html) integrates custom event sources with Houdini's internal event loop and can use file-descriptor or polling strategies.
- [`hou.ui.postEventCallback`](https://www.sidefx.com/docs/houdini/hom/hou/ui.html) schedules one-shot work on Houdini's event loop.
- [`hou.ui.addEventLoopCallback`](https://www.sidefx.com/docs/houdini/hom/hou/ui.html) runs while the UI is idle, approximately every 50 ms, and must remain fast.

Recommended use:

- HDK bridge: an `FS_EventGenerator` wakes the main thread when a native queue has work.
- HOM prototype: a bounded queue drained by one event-loop callback or posted callback.
- Networking thread: receives, validates framing, and enqueues plain data only.

### Thread safety

SideFX documents node and parameter evaluation as non-thread-safe. Scene reads or writes involved in collaboration should remain on the main thread even if a low-level lock exists.

Do not use the existence of an HDK lock as permission to mutate an interactive scene from arbitrary workers.

### Persistent identity

- [`hou.OpNode.setUserData`](https://www.sidefx.com/docs/houdini/hom/nodeuserdata.html) stores string data with the `.hip` file.
- [`OP_Node::setUserData`](https://www.sidefx.com/docs/hdk/class_o_p___node.html) exposes the corresponding native mechanism.

This is a feasible v1 identity carrier for nodes, with two required safeguards:

1. copy/paste may duplicate stored IDs and must be detected;
2. identity writes are internal metadata changes and must not become user operations.

Do not use `sessionId()` as collaborative identity; SideFX only guarantees it within one Houdini process.

### Undo

- [`hou.undos.disabler`](https://www.sidefx.com/docs/houdini/hom/hou/undos.html) prevents remote application from filling the local undo stack.
- [`hou.undos.group`](https://www.sidefx.com/docs/houdini/hom/hou/undos.html) groups a scripted local action.
- [`UT_UndoManager`](https://www.sidefx.com/docs/hdk/class_u_t___undo_manager.html) provides native undo state and hooks.

The recommended v1 policy is described in ADR 0003: remote operations do not enter the local undo stack; a user's ordinary local undo/redo is captured as a new collaborative transaction. This must be validated operation-by-operation.

### UI and presence

- [Python Panels](https://www.sidefx.com/docs/houdini/ref/panes/pythonpanel.html) support embedded PySide6/PyQt6 interfaces.
- [`hou.NetworkEditor.setOverlayShapes`](https://www.sidefx.com/docs/houdini/hom/hou/NetworkEditor.html) supports temporary overlay graphics.
- [`hou.NetworkShape`](https://www.sidefx.com/docs/houdini/hom/hou/NetworkShape.html) describes overlay primitives.
- [Network editor extension](https://www.sidefx.com/docs/houdini/hom/network.html) exposes mouse and context events.

Passive collaboration UI should prefer overlay shapes and a Python panel. Do not globally replace Houdini's network-editor event handling merely to show presence.

### HDK build compatibility

The HDK is ABI-sensitive. SideFX documents that plugins may require recompilation when `HDK_API_VERSION` changes, and Windows builds need a compatible compiler.

Therefore:

- ship one DSO per supported Houdini API/platform build;
- check runtime API compatibility;
- keep the DSO thin;
- permit a HOM-only fallback where possible;
- do not store canonical state inside the DSO.

## Recommended runtime architecture

```text
PySide6 collaboration panel
        │
        ▼
portable client/session core
  - protocol
  - ordering
  - operation model
  - recovery
  - presence
        │ plain records
        ▼
Houdini adapter interface
   ├── HOM adapter
   └── thin HDK bridge
          - global OP change hook
          - scene lifecycle hook
          - native event generator
          - thread-safe event queues
        │
        ▼
single ordered main-thread application gateway
        │
        ▼
Houdini scene
```

The HOM and HDK adapters should emit the same normalized **observations**, not different operation contracts.

## Thin HDK bridge contract

The bridge should expose a narrow interface conceptually equivalent to:

```text
start_capture(config)
stop_capture()
drain_observations(max_count)
post_wakeup()
runtime_capabilities()
runtime_version()
```

An observation contains only plain data:

```text
event category
node pointer token valid only during immediate capture
resolved node path
stable entity ID if present
event-specific index
scene generation
monotonic local observation number
```

Resolve all data that cannot outlive the callback before enqueuing it. Never retain raw `OP_Node*` pointers in a queue after deletion or scene replacement.

The portable layer decides whether observations form:

- one operation;
- one composite transaction;
- a bulk diff request;
- internal metadata;
- unsupported noise.

## Recommended staged use of HDK

### Stage A — HOM prototype

Use HOM callbacks and a Python panel to validate:

- product experience;
- protocol;
- operation contracts;
- identity policy;
- failure behavior.

### Stage B — HDK event probe

Build a native probe using global operator callbacks and scene events. Log exact traces for the supported matrix on each target Houdini build.

### Stage C — thin native capture bridge

Move only event observation and main-loop wakeup into HDK when the probe proves value.

### Stage D — measured native hot paths

Move application or serialization into C++ only after profiling proves a bottleneck and equivalent tests exist.

This avoids converting product iteration into a cross-platform C++ build problem prematurely.

## Feasible v1 surface

The safest v1 is:

- create/delete an ordinary node or copied subtree;
- rename a node;
- move a node in the network editor;
- connect/disconnect an input;
- set a simple unanimated, unexpressed parameter tuple;
- selected display/render/bypass/template flags after callback traces are proven.

The operation support matrix is authoritative.

## Not a v1 guarantee

Do not claim support yet for:

- cooked geometry or cache data;
- DOP simulation state;
- TOP work-item state;
- LOP stage edits that are not represented by ordinary node/parameter operations;
- APEX graph internals;
- HDA definition or asset-library edits;
- locked HDA internals;
- expressions, channel references, keyframes, animation layers, takes;
- multiparms or spare-parameter schemas;
- arbitrary custom node data;
- network boxes, sticky notes, dots, or subnet indirect inputs without stable identity;
- pane layouts, viewport cameras, selections, update mode, or other personal workspace state.

## Required empirical proofs

Before a public alpha, run the event probe for every target build and record:

- exact callback order;
- event payload and nullability;
- whether changes are emitted once or in bursts;
- undo and redo traces;
- remote-application traces;
- copy/paste identity duplication;
- subnet delete/create behavior;
- locked-asset permissions;
- save/load persistence;
- callback cleanup after Python reload;
- scene replacement while work is queued;
- Windows, Linux, and macOS differences if supported.

The architecture is feasible. Production confidence comes from this matrix, not from API names alone.
