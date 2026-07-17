# Current project state

This file records what is actually present in the attached coophou sketch. It is based on static inspection of the repository on 2026-07-17.

The code has **not** been compiled or executed in this documentation pass because the active environment does not contain the target Houdini SDK/runtime. The first implementation milestone must verify every build and runtime statement inside the declared target Houdini installation.

## Confidence labels

- **Verified in sketch**: directly present in the current files.
- **Requires runtime verification**: code exists, but its behavior has not been proven in the target Houdini build.
- **Proposed**: target architecture from the engineering guide.
- **Unsupported**: not currently implemented as a trustworthy contract.

## Repository inventory

| Item | Status | Current value | Evidence |
|---|---|---|---|
| Python package | Verified in sketch | `coophou` | `coophou/` |
| Native source | Verified in sketch | `src/` | C++ files |
| Build system | Verified in sketch | CMake 3.21+, C++17 | `CMakeLists.txt` |
| Houdini discovery | Verified in sketch | `$HFS/toolkit/cmake`, `find_package(Houdini REQUIRED)` | `CMakeLists.txt` |
| Qt native dependencies | Verified in sketch | Houdini Qt6 Core/Gui/Widgets targets | `CMakeLists.txt` |
| Python Qt binding | Verified in sketch | PySide6 | Python imports |
| Python startup layout | Verified in sketch | `python3.11libs/` | startup files |
| Native plugin target | Verified in sketch | shared library `CoopHou` | `CMakeLists.txt` |
| Native core target | Verified in sketch | static library `CoopHouCore` | `CMakeLists.txt` |
| C++ tests | Verified in sketch | GoogleTest 1.15.2 through FetchContent | `CMakeLists.txt` |
| Server entry point | Verified in sketch | `python -m coophou.server` | `coophou/server/__main__.py` |
| Multi-client launcher | Verified in sketch | launches Houdini sessions in a test desktop | `scripts/launchClients.py` |
| HDK commands | Verified in sketch | `coop_start`, `coop_stop` | `src/main.cpp` |
| Target Houdini version/build | Unknown | — | must be declared |
| `HDK_API_VERSION` | Unknown | — | must be recorded |
| Supported platforms/compiler | Unknown | — | must be declared |
| Verified build command | Unknown | — | must be run |
| Verified test command | Unknown | — | must be run |

## Current architecture

### Python client

**Verified in sketch**

- `CoopHouClient` uses `QTcpSocket`.
- A handshake assigns a server-local numeric UID.
- `ClientSender` observes HOM node events and emits dictionaries.
- `ClientReceiver` schedules remote application using `hou.ui.postEventCallback`.
- Remote changes are applied inside `hou.undos.disabler()`.
- Event extraction and application are coupled in `client/eventTranslation.py`.
- Synchronization currently addresses Houdini objects by path.

### Python server

**Verified in sketch**

- `QTcpServer` listens on localhost port 8101.
- Non-handshake messages are broadcast to every other connected user.
- An HTTP debug server exposes the current users dictionary.
- There is no canonical sequence, durable operation history, acknowledgement model, capability negotiation, transaction model, or reconnect resume contract.

### Native HDK sketch

**Verified in sketch**

- `Watcher` uses `OP_Director::addGlobalOpChangedCallback`.
- `coop_start` and `coop_stop` register and remove the callback.
- The callback logs the event and inspects selected payload forms.
- `EventManager` currently implements only a child-created JSON payload; the other declared event handlers return empty objects.
- An HDK/gtest fixture initializes a `MOT_Director` and creates real object nodes.

### UI sketch

**Verified in sketch**

- `NetworkOverlay` uses a transparent top-level Qt widget positioned over a Network Editor.
- Cursor and viewport event classes exist in `eventTranslation.py`, but their periodic sending is commented out.
- There is no collaboration panel or multi-user overlay composition service yet.

## Current synchronization surface

Nothing should yet be marked as a production-supported operation.

The Python sketch attempts:

| Edit | Capture/apply sketch | Trustworthy contract? |
|---|---|---|
| Node position | HOM position and `setPosition` | No: path identity, no canonical order or transaction |
| Parameter tuple | `asData()` / `setFromData()` | No: bulk/null callback and expression scope unresolved |
| Rename | current path + `setName()` | No: the old stable target identity is absent |
| Create | path/type + `createNode()` | No: subtree, defaults, copy/paste, identity and naming unresolved |
| Delete | path + `destroy()` | No: current buffer filtering can discard deleted-node events |
| Input rewiring | node `asData(inputs=True)` | No: too broad; endpoint preconditions are absent |
| Full node data after create | `asData(children=True)` / `setFromData()` | Experimental only; not the target durable protocol |
| Cursor/camera | partial classes | Presence experiment only |

The desired v1 surface is defined in `docs/operation-support-matrix.md`.

## Immediate safety and correctness findings

These findings should be addressed in the first milestone without turning it into a full architecture rewrite.

### 1. Callback ownership is currently unsafe

`ClientSender.startWatcher()` removes every callback returned by `hou.ui.eventLoopCallbacks()`.

`ClientSender.addCallbacks()` calls `removeAllEventCallbacks()` on every observed node.

Both actions can remove callbacks owned by Houdini or unrelated tools. coophou must remove only registrations it owns.

### 2. Native watcher registration is not idempotent

Repeated `Watcher::start()` calls may register the same global hook more than once. The current sanity test starts the watcher without stopping it.

The event probe needs explicit registration state and symmetric cleanup.

### 3. TCP framing is not defined

Messages are written as raw JSON bytes without a delimiter or length prefix. Readers call `readAll()` and split on newlines, but senders do not append newlines.

TCP may combine or split messages arbitrarily. Do not build further protocol behavior on this transport until framing is explicit.

### 4. Echo suppression is path-based and lossy

Remote receive adds one path to `ignoredNodes`. During capture, one matching event removes the path and returns from the whole batch.

One remote operation may emit several callbacks, a path may change, and an unrelated local edit may share the path later. Replace this with a scoped remote-apply context after the event probe establishes callback traces.

### 5. Deletion capture can be discarded

`processEvents()` filters buffered events through `hou.node(event["node"])`. A deleted node may no longer resolve, so the information needed for a delete operation can be removed before normalization.

Deletion data must be captured while still valid, without retaining stale native pointers.

### 6. Paths are currently authoritative

Create, delete, rename, parameter, position, and wiring payloads resolve targets by path.

The v1 design requires persistent entity IDs and path-reuse tests before these become collaborative contracts.

### 7. Callback payload normalization is incomplete

The Python callback converts event values to strings. A bulk `ParmTupleChanged` may not identify one tuple. The native watcher also assumes selected `void *data` meanings that need to be proven for the target HDK build.

The first milestone must log raw event categories safely and create checked-in trace fixtures.

### 8. Reconnect can spin

Connection refusal immediately calls `start()` again with no timer or bounded backoff. This can create a tight retry loop.

The first milestone may replace this with a cancellable timer, but it should not implement the final reconnect/history protocol yet.

### 9. Server state is only a relay

The server accepts a UID supplied in the packet and broadcasts messages. It does not establish canonical order or verify scene compatibility.

Keep the relay only as a disposable demonstration while the event probe is built. Do not mistake it for the planned authority.

### 10. Snapshot and node serialization experiments are not protocol contracts

`src/main.cpp` contains a disabled `saveSingle`/`loadNetwork` experiment, and the Python layer uses `asData`/`setFromData`.

These are useful probes, but they should not become routine full-scene or opaque-node synchronization without an ADR, deterministic tests, and recovery semantics.

## First milestone

The next implementation milestone is **Phase 0 + Phase 1**, not a server rewrite:

1. make startup and teardown non-destructive and idempotent;
2. verify the existing CMake/HDK test setup;
3. convert the HOM and HDK watchers into structured event probes;
4. add scripted scenarios for the v1 operation matrix;
5. check in trace fixtures and a generated comparison report;
6. update this file with verified Houdini/build/platform evidence;
7. stop and report before designing durable operations from those traces.

See `docs/implementation-roadmap.md` and the initial agentic prompt supplied with this package.
