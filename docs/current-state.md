# Current project state

This file records what is actually present in coophou. Static facts were first inspected on 2026-07-17; the Phase 0/1 facts below were then compiled and executed against the declared target installation on the same date.

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
| Target Houdini version/build | Verified at runtime | Houdini `21.0.729` | `hou.applicationVersionString()` |
| Platform | Verified at runtime | `Windows-10-10.0.26200-SP0`, x86-64 | Houdini Python `platform.platform()` |
| Houdini Python | Verified at runtime | `3.11.7`, MSC v.1942, 64-bit | Houdini `hython` |
| Qt / PySide | Verified at runtime | Qt `6.5.3`, PySide `6.5.3` | Houdini `hython` |
| `HDK_API_VERSION` | Verified from installed SDK | `21000693` | `UT/UT_HDKVersion.h` |
| Compiler / SDK | Verified by configure/build | MSVC `19.44.35228`, toolset `14.44.35207`, Windows SDK `10.0.26100.0` | CMake/MSBuild output and `cl /Bv` |
| CMake | Verified at runtime | `4.3.4` | `cmake --version` |
| Verified configure command | Passed | `cmake -S . -B build -G "Visual Studio 17 2022" -A x64 -DBUILD_TESTING=ON` | local run |
| Verified build command | Passed | `cmake --build build --config RelWithDebInfo --parallel` | built `CoopHou.dll` and `CoopHou_Tests.exe` |
| Verified test commands | Passed | `ctest --test-dir build -C RelWithDebInfo --output-on-failure`; `python -m unittest discover -s tests -p "test_*.py" -v` | local runs |

## Phase 0 target declaration

The verified target is Houdini 21.0.729 on Windows build 10.0.26200 with MSVC 19.44. The plugin is installed by `houdini_configure_target` at `C:/Users/Spiel/Documents/houdini21.0/dso/CoopHou.dll`. The package loads Python from `python3.11libs/`; `pythonrc.py` adds the repository package root and `uiready.py` starts the environment-selected test client. The legacy server entry point remains `python -m coophou.server`; it is not used by the event probes.

The checked-in sample inputs are generated from isolated empty scenes in fresh `hython` processes. No artist working `.hip` was opened or overwritten. The lifecycle scenario uses only a temporary directory.

## Current architecture

### Python client

**Verified in sketch**

- `CoopHouClient` uses `QTcpSocket`.
- A handshake assigns a server-local numeric UID.
- `ClientSender` is now a Phase-1 HOM observation probe and emits no synchronization operations.
- The legacy `ClientReceiver` can schedule application using `hou.ui.postEventCallback` and `hou.undos.disabler()`, but `CoopHouClient` ignores non-handshake relay payloads during Phase 1.
- Legacy event extraction/application remains in `client/eventTranslation.py`, but the probe does not call it.
- Frozen legacy synchronization code addresses Houdini objects by path; the probe treats paths as diagnostics only.

### Python server

**Verified in sketch**

- `QTcpServer` listens on localhost port 8101.
- Non-handshake messages are broadcast to every other connected user.
- An HTTP debug server exposes the current users dictionary.
- There is no canonical sequence, durable operation history, acknowledgement model, capability negotiation, transaction model, or reconnect resume contract.

### Native HDK sketch

**Verified in sketch**

- `Watcher` uses `OP_Director::addGlobalOpChangedCallback` plus owned director lifecycle callbacks.
- `coop_start` and `coop_stop` are idempotent and remove only the exact coophou registrations.
- The callback serializes safe callback-time values to a bounded plain-data queue. It never dereferences an unverified `void *data` payload or retains native pointers.
- `EventManager` emits the versioned common observation shape for known and unknown events.
- An HDK/gtest fixture initializes a `MOT_Director` and creates real object nodes.

### UI sketch

**Verified in sketch**

- `NetworkOverlay` uses a transparent top-level Qt widget positioned over a Network Editor.
- Cursor and viewport event classes exist in `eventTranslation.py`, but their periodic sending is commented out.
- There is no collaboration panel or multi-user overlay composition service yet.

## Current synchronization surface

Nothing should yet be marked as a production-supported operation.

The frozen legacy `eventTranslation.py` sketch attempts:

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

## Baseline safety findings and Phase-1 disposition

### 1. Baseline callback ownership was unsafe

**Resolved for the probe.** `ClientSender` retains exact bound callbacks and removes only those registrations. A reload-stable coophou registry stops the previous probe before replacement. Pure tests prove unrelated event-loop and node callbacks survive stop/restart.

### 2. Baseline native watcher registration was not idempotent

**Resolved for the probe.** `Watcher` has explicit registration state, symmetric global/director cleanup, and start/start/stop/stop/restart tests. An HDK test registers a foreign global callback and proves `Watcher::stop()` leaves it active.

### 3. TCP framing is not defined

Messages are written as raw JSON bytes without a delimiter or length prefix. Readers call `readAll()` and split on newlines, but senders do not append newlines.

TCP may combine or split messages arbitrarily. Do not build further protocol behavior on this transport until framing is explicit.

### 4. Echo suppression is path-based and lossy

**Legacy path suppression is no longer used by capture.** The HOM probe includes a nesting- and exception-safe temporary suppression context only to label evidence. It is not the final remote-apply contract. HDK observations cannot yet see the Python suppression depth.

### 5. Deletion capture can be discarded

**Resolved for the probe.** HOM copies paths and other values in the callback and maintains a main-thread plain-data snapshot cache for entity IDs that HOM has already cleared by `BeingDeleted`. HDK captures the entity ID at `OP_NODE_PREDELETE`; no native pointer survives the callback.

### 6. Paths are currently authoritative

Create, delete, rename, parameter, position, and wiring payloads resolve targets by path.

The v1 design requires persistent entity IDs and path-reuse tests before these become collaborative contracts.

### 7. Callback payload normalization is incomplete

**Resolved for the probe.** Primitive values retain their types; parameter records distinguish raw and evaluated values and label `parm_tuple=None` as `bulk_or_ambiguous`. The native probe records only payload presence and `unverified` semantics. Fixtures are checked in under `tests/fixtures/events/houdini-21.0.729/hdk-api-21000693/windows/`.

### 8. Reconnect can spin

Connection refusal immediately calls `start()` again with no timer or bounded backoff. This can create a tight retry loop.

The first milestone may replace this with a cancellable timer, but it should not implement the final reconnect/history protocol yet.

### 9. Server state is only a relay

The server accepts a UID supplied in the packet and broadcasts messages. It does not establish canonical order or verify scene compatibility.

Keep the relay only as a disposable demonstration while the event probe is built. Do not mistake it for the planned authority.

### 10. Snapshot and node serialization experiments are not protocol contracts

`src/main.cpp` contains a disabled `saveSingle`/`loadNetwork` experiment, and the Python layer uses `asData`/`setFromData`.

These are useful probes, but they should not become routine full-scene or opaque-node synchronization without an ADR, deterministic tests, and recovery semantics.

## Phase 1 result and boundary

Phase 0 + Phase 1 are complete for the declared Windows target in headless/scripted Houdini. Fifteen scenarios were captured through both adapters. See `docs/event-probe-report.md` and `docs/event-probe-comparison.md`.

Not verified in this environment pass:

- interactive Network Editor dragging and clipboard paste timing;
- a licensed full UI session's event-loop settle behavior;
- Linux or macOS;
- any Houdini build other than 21.0.729;
- exact meanings of HDK callback `void *data`;
- a native DSO unload/reload cycle;
- a `parm_tuple=None` bulk callback generated by a real gesture;
- final operation, server, recovery, or collaboration UI contracts.

The next milestone is human review of these fixtures followed by Phase 2's portable deterministic core. Do not turn the observations directly into network messages.
