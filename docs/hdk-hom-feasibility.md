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

- HDK/C++ production adapter: callbacks enqueue bounded evidence and one
  main-thread gateway settles capture or applies queued requests.
- Native wakeup: an `FS_EventGenerator` may wake the main thread when tests and
  measurements justify it; deterministic explicit draining is sufficient for
  the first Phase 3 slice.
- HOM fallback: a separately capability-gated adapter may use one bounded
  event-loop callback or posted callback, but it is not the production path.
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
- keep the DSO thin by responsibility, not by routing production work through
  Python HOM;
- permit a HOM-only fallback only where declared capabilities and conformance
  evidence support it;
- do not store canonical state inside the DSO.

## Recommended runtime architecture

```text
portable client/session core
  - protocol
  - ordering
  - operation model
  - recovery
        │ plain records
        ▼
versioned native Python bridge
        │ bounded plain records
        ▼
thin HDK/C++ production adapter
   - global OP and scene lifecycle hooks
   - persistent identity and tombstones
   - bounded aggregation and scoped extraction
   - native apply context and verification
   - bounded capture/application queues
        │
        ▼
single ordered main-thread application gateway
        │
        ▼
Houdini scene
```

HOM may drive fixtures or independently inspect results in tests. Any fallback
adapter must conform to the same normalized operation contract, but production
capture and application do not depend on HOM callbacks or HOM mutation.

## Thin HDK bridge contract

The bridge should expose a narrow interface conceptually equivalent to:

```text
start_capture(config)
stop_capture()
capture_state()
drain_observations(max_count)
flush_settle()
extract_supported_snapshot()
enqueue_apply(request)
drain_apply(max_transactions, max_operations)
runtime_capabilities()
```

An observation contains only plain data:

```text
bridge schema version
record category and supported event context
stable entity ID and diagnostic path
transaction/operation/correlation IDs where applicable
scene generation
monotonic local observation number
```

Resolve all data that cannot outlive the callback before enqueuing it. Never retain raw `OP_Node*` pointers in a queue after deletion or scene replacement. Unknown versions, operation families, stale generations, and queue overflow fail closed with structured errors.

The portable layer decides whether observations form:

- one operation;
- one composite transaction;
- a bulk diff request;
- internal metadata;
- unsupported noise.

## Recommended staged use of HDK

### Stage A — completed probes and portable contracts

Keep the Phase 1 HDK/HOM traces as evidence and the Phase 2 portable records as
the semantic reference. Do not rewrite probe evidence to imply coverage that
was not measured.

### Stage B — native Phase 3 adapter (complete for 21.0.729 / Windows)

The versioned bridge and HDK-first identity, capture, aggregation, supported
application, suppression, and verification paths are implemented. Real
Houdini contracts prove both semantic directions for the seven families on the
exact target.

Measured native API findings include:

- `OP_CHILD_CREATED`, `OP_NODE_PREDELETE`, `OP_NAME_CHANGED`, `OP_UI_MOVED`,
  `OP_INPUT_CHANGED`, `OP_INPUT_REWIRED`, and `OP_PARM_CHANGED` are sufficient
  primary signals for the scripted declared surface when followed by one
  bounded settle extraction;
- `OP_INPUT_REWIRED` was required in addition to the earlier probe allowlist;
- `PRM_ChoiceList::tokenFromIndex` and a bounded token search preserve ordinal
  menu tokens instead of evaluated indices;
- `OP_Node::canAccess(PRM_WRITE_OK)` rejects identity and parameter mutation
  inside a locked HDA on this build;
- `OP_Network::createNodeOfExactType`, native rename/position/input/parameter
  APIs, and `destroyNode` implement the declared application surface;
- load's nested clear advances one coophou scene generation, save does not, and
  merge is classified explicitly rather than normalized silently.

No meaning is assigned to unverified callback `void *data`, and no raw pointer
is retained across a callback or bridge call.

### Stage C — measured wakeup and hot paths

Add an `FS_EventGenerator` or further native optimization only when measurements
show that deterministic bounded draining cannot meet the latency budget.

### Stage D — capability-gated fallback and additional builds

Add a fallback or another Houdini/platform build only with explicit capability
negotiation and its own conformance evidence.

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
