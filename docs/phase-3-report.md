# Phase 3 report: HDK-first single-process Houdini adapter

Phase 3 is complete for the declared Houdini 21.0.729 Windows target and the
narrow capability set below. This milestone connects the unchanged Phase 2
contracts to real Houdini state. It does not claim a multi-user product.

## 1. Exact target

| Component | Verified target |
|---|---|
| Houdini | 21.0.729 |
| HDK API | `21000693` |
| Platform | Windows 10 build 26200, x86-64 |
| Houdini Python | 3.11.7, MSC v.1942, 64-bit |
| Qt / PySide | 6.5.3 / 6.5.3 |
| Compiler | MSVC 19.44.35228, toolset 14.44.35207 |
| Windows SDK | 10.0.26100.0 |
| CMake | 4.3.4 |
| DSO | `C:/Users/Spiel/Documents/houdini21.0/dso/CoopHou.dll` |

The DSO auto-loaded in fresh `hython` processes. Runtime capabilities report
the exact Houdini build, HDK API, Windows platform, bridge schema 1, the native
production path, and exactly seven operation families.

## 2. Native and Python structure

| Module | Responsibility |
|---|---|
| `src/watcher.*` | Exact owned `OP_Director` global/lifecycle registrations and Phase 1 trace compatibility |
| `src/native_adapter.*` | HDK capture, plain mirror, identity, extraction, aggregation, bounded queues, native apply, suppression, verification, diagnostics |
| `src/main.cpp` | Official Houdini extension registration and JSON/Python wrappers |
| `coophou/houdini_adapter/bridge.py` | Lazy, strict plain-JSON calls; no scene mutation |
| `coophou/houdini_adapter/projection.py` | Native-root normalization and strict `FakeScene` projection |
| `coophou/houdini_adapter/orchestrator.py` | Python-owned operation/transaction IDs and single-process portable confirmation |

The DSO owns no canonical session sequence, authority history, reconnect,
conflict, recovery, transport, presence, or UI policy. The portable core still
imports without Houdini or Qt. No raw Houdini pointer is retained in the native
mirror or crosses a callback/bridge boundary; call-local pointers are rebuilt
and discarded during extraction/application.

## 3. Bridge mechanism and schema

`HOMextendLibrary` plus Houdini's wrapped CPython API registers ten functions
on `hou`:

- `coophou_native_capabilities()`
- `coophou_native_start_capture(json)`
- `coophou_native_stop_capture()`
- `coophou_native_capture_state()`
- `coophou_native_flush_settle()`
- `coophou_native_drain_capture(json)`
- `coophou_native_extract_snapshot(json)`
- `coophou_native_enqueue_apply(json)`
- `coophou_native_drain_apply(json)`
- `coophou_native_reset_for_tests(json)`

The first nine are the adapter surface; reset is test-only fault control. Each
response is a schema-1 JSON success envelope with an object payload or an error
envelope with stable `code`, `message`, and `context`. Requests are JSON
objects limited to 4 MiB. Exact fields, types, versions, IDs, bounds,
allowlists, tuple shapes, transaction requirements, and scene generation are
validated. Unknown fields/versions/operations fail closed. No path, import,
callback, expression, or code-execution capability is exposed.

The registered functions are only a language bridge. Supported reads and
mutation behind them are HDK/C++, not Python calls to `hou.OpNode`.

## 4. Callback ownership and bounded work

`Watcher::start()` and `stop()` are idempotent. They add/remove only the exact
coophou global and director callbacks; an integration test proves a foreign
global callback remains registered. Stop clears only coophou adapter queues,
mirror, tombstones, replay memory, correlation, and suppression state.

Callbacks accept these primary signals on the declared build:

- `OP_CHILD_CREATED`;
- `OP_NODE_PREDELETE`;
- `OP_NAME_CHANGED`;
- `OP_UI_MOVED`;
- `OP_INPUT_CHANGED` and `OP_INPUT_REWIRED`;
- `OP_PARM_CHANGED`;
- director clear/load/merge lifecycle events.

A callback marks plain paths/scopes and copies subtree IDs at pre-delete. It
does no networking, Python call, arbitrary payload dereference, or scene scan.
Capture and apply queues have configured hard limits; overflow sets an explicit
overflow flag and reconciliation-required state. Drain counts and operations
per drain are bounded. Normal adapter use does not print the raw HDK trace.

## 5. Configured collaboration root

One configured native root, default `/obj`, maps explicitly to portable entity
ID `root` for one scene generation. A dedicated ordinary network can be used
for isolation. The adapter does not write `coophou.entity_id=root` to the
configured root, including Houdini's built-in manager; the mapping is adapter
state only. Descendants may include supported nested ordinary networks. Any
operator outside the configured allowlist, node bound, root, or permission
boundary fails closed. Multi-root/whole-scene collaboration is future work.

## 6. Stable identity

Supported descendants use persistent user data key `coophou.entity_id` with a
validated opaque ID. Production IDs are UUIDs; tests inject a deterministic
prefix/counter. Internal metadata callbacks are counted separately and never
become semantic operations.

The native supported-state mirror maps IDs to plain state and diagnostic paths.
It stores no cross-call node pointer. Rename refreshes path data; delete records
parent/path tombstones; clear/load clears lookup state. Resolution never falls
back from an ID mismatch to a path. A replacement at a deleted path receives a
different ID, and an old-ID operation is rejected.

Copying duplicates Houdini user data. Structural settle finds the complete new
scope, repairs every live collision under identity suppression, rescans, and
emits one generic parent-before-child `CreateSubtree` with wires after
endpoints. Connected two-node copy and nested generated scope tests pass.
Locked HDA internals reject missing-ID assignment rather than being skipped or
retargeted.

## 7. Aggregation, state reads, and verification

HDK events are primary evidence. Ordinary rename, move, input, and parameter
bursts retain exact touched native paths and settle with targeted HDK reads.
Structural create/delete/copy/generated actions, bootstrap, clear/load, merge,
explicit snapshot extraction, and post-apply verification use a bounded scan
of the configured supported root. There is no scan per raw callback and no
whole Houdini-scene scan.

The mirror diff emits candidates without operation IDs. One settle coalesces
tuple component changes and high-frequency movement to complete final values.
Python validates candidates through the frozen Phase 2 constructors, assigns
operation/transaction IDs, and feeds the existing portable semantics.

Native application independently extracts before state, stages the complete
transaction abstractly, mutates, extracts after state, and compares entity IDs,
parent/type/name/position, exact input endpoints, and configured raw parameter
tuples. Mismatches include entity/property/expected/actual plus transaction,
operation, and scene-generation context where attributable.

## 8. Capability boundary

Operator types are an explicit per-start allowlist. Automated contracts use
ordinary `null`, `subnet`, `merge`, and test-scope `geo` networks. Creation
uses exact operator type and exact requested name; implicit Houdini collision
renaming is not accepted.

Parameters are an explicit fixed-name/fixed-kind allowlist. Verified raw kinds
are integer, finite float, boolean, string, ordinal menu token, and fixed
tuples. Menu tokens are extracted through `PRM_ChoiceList::tokenFromIndex` and
applied by bounded token lookup. Complete tuples, never component deltas, cross
the bridge.

Expressions, keyframes/channels, buttons, multiparms, spare schemas, locked
internals, HDA definitions, flags, animation layers, APEX, cooked geometry,
simulation state, boxes/notes/dots, and personal UI state are rejected or
outside capability. The bridge never evaluates a supplied expression.

## 9. Native application gateway

Accepted transactions enter a bounded FIFO with correlation and scene
generation. `drain_apply` runs only on Houdini's main thread with explicit
transaction/operation budgets. The gateway parses exact Phase 2 transaction
and operation shapes, checks replay hash, stages every dependency and
precondition before mutation, then applies in submitted order.

Native application covers exact node create, generic subtree create, exact
subtree delete, rename, final position, exact input set/disconnect, and raw
parameter tuple set. Name collisions, unsupported types, stale expected name,
position/source/value, deleted sources, tombstoned IDs, missing endpoints,
wrong arity/kind, stale generation, and oversized work reject before normal
mutation. Same-ID/same-content replay returns `APPLIED_REPLAY`; same ID with
different content is a conflict.

## 10. Suppression and correlation

Remote application has a native depth and current transaction/operation ID
context. Expected callbacks increment `expected_echoes_suppressed` and do not
dirty capture. Identity writes use a separate depth and counter. Context is
cleared after success and injected failure. Every remotely applied operation
family was followed by settle/drain and produced no local change record;
ordinary later local edits remained capturable.

The current result exposes the caller correlation ID and transaction ID.
Per-callback correlation is retained in native diagnostic context rather than
sent as a new operation. No suppression remains active while waiting for
network or Python work.

## 11. Scene generation

Save does not change generation. Clear advances it. Load's nested clear/load
sequence advances it exactly once. After replacement, native queues, mirror,
tombstones, and stale scopes are invalidated and a `scene.replaced` record is
emitted. Stale apply is rejected before queueing. Merge emits
`scene.merge_requires_settle`; it is not silently treated as an ordinary user
gesture.

## 12. Real Houdini contract results

The fresh-`hython` contract suite passes 34 scenarios:

| Family/boundary | Real target evidence |
|---|---|
| CreateNode | local create, immediate supported parameter coalescing, native apply, replay, unsupported type rejection |
| CreateSubtree | connected copy collision repair, parent-before-child nested generation, internal wire, native apply |
| DeleteSubtree | callback-time descendant IDs, exact native delete, tombstones, path reuse protection |
| RenameNode | capture/apply, identity preserved, stale expected name and collision reject |
| MoveNode | 3 scripted moves coalesce to final value; native apply |
| SetInput | connect/disconnect exact endpoint, stale expected source and deleted source reject |
| SetParameterTuple | boolean and all five raw kinds; fixed float tuple; stale expected value; expression/keyframe rejection |
| Lifecycle/bridge | duplicate start/stop, reload, schema rejection, exact root containment/mapping, queue overflows, stale generation, save/load, merge, locked HDA |

HOM is used only to construct fixtures and independently assert selected final
state. Capture/application under test are native.

## 13. Semantic round-trip proof

For every local capture test, the emitted native candidates receive
Python-owned IDs, form a frozen Phase 2 transaction, apply to a maintained
`FakeScene`, and are compared to a freshly extracted native supported-state
projection. For every successful remote helper test, the initial native
snapshot is materialized as a `FakeScene`, the Phase 2 transaction applies to
that projection, native apply runs, and final native extraction must equal the
expected `FakeScene.semantic_snapshot()`.

Equality covers the supported entities, hierarchy, types, names, normalized
paths, positions, configured parameters, exact inputs, and tombstones—not
byte-identical `.hip` files or cooked state. The portable Phase 2 schemas were
not changed.

## 14. Failure and partial application

The fake authority remains clone/apply/validate/swap atomic. Houdini is not
claimed to be transactionally atomic. Native prevalidation minimizes failure
after mutation. A deterministic operation-boundary fault after the first of
two creates proves that the first node exists, the second does not, the result
is `RECONCILIATION_REQUIRED`, `partial_apply=true`, and normal draining stops.
An unexpected failure inside an operation is conservatively reported as
possibly partial. No confirmed success is returned after failure or semantic
mismatch. No text-`.hip` merge or automatic snapshot rollback was added.

## 15. Performance evidence

`tests/houdini_phase3_benchmark.py` ran in a fresh `hython` process on the exact
target. Values are single-machine evidence, not universal budgets.

| Measurement | Result |
|---|---|
| Native callback handler, 1,004 events from 1,000 creates | mean 1.865 µs; max 13.9 µs |
| 10-node explicit snapshot, bridge included (20 samples) | median 0.110 ms; p95 0.124 ms |
| 100-node explicit snapshot, bridge included (10 samples) | median 0.986 ms; p95 2.106 ms |
| 1,000-node explicit snapshot, bridge included (5 samples) | median 17.149 ms; p95 21.192 ms |
| 1,000-node native extraction only (6 scans including bootstrap) | mean 2.467 ms; max 4.146 ms |
| 1,000 create observations → one subtree candidate | settle/scan 24.192 ms; bridge drain 26.196 ms |
| 1,000 scripted moves → one move | action 2.989 ms; targeted settle 4.050 ms |
| 1,002 toggle sets → one tuple set | action 9.633 ms; targeted settle 3.672 ms |
| Copy 100 nodes → one subtree candidate | Houdini copy 25.673 ms; settle 2.337 ms |
| Delete 100 independent nodes → 100 deletes | Houdini destroy 100.045 ms; settle 1.791 ms |
| Native subtree apply + post-verify, 10 nodes | 1.178 ms |
| Native subtree apply + post-verify, 100 nodes | 18.231 ms |
| Capture-state JSON round trip (1,000 samples) | median 0.0278 ms; p95 0.0328 ms |

No network/socket wait exists. No Python call occurs per callback. Structural
1,000-node settle and 100-node apply can exceed one 60 Hz frame; Phase 4 must
schedule bounded drains between interactive work and profile large atomic
subtrees before raising capability limits. The test does not hide this with an
unsafe background Houdini scan.

## 16. Test layers and commands

The completed validation is:

- 94 ordinary-Python tests (88 preserved plus 6 adapter tests);
- 13 native/gtest tests against initialized Houdini HDK state;
- 34 fresh-`hython` Phase 3 contracts;
- one fresh-`hython` benchmark scenario suite;
- 16/16 CTest entries, including the ordinary-Python, real-Houdini contract,
  and benchmark runners.

Successful commands:

```powershell
$env:HFS = 'C:\Program Files\Side Effects Software\Houdini 21.0.729'
cmake -S . -B build -G "Visual Studio 17 2022" -A x64 -DBUILD_TESTING=ON
cmake --build build --config RelWithDebInfo
ctest --test-dir build -C RelWithDebInfo --output-on-failure
python -m unittest discover -s tests -p "test_*.py" -v
python -c "import coophou.core; ...verify no hou/Qt modules..."
& "$env:HFS\bin\hython.exe" tests/houdini_phase3_contract.py
& "$env:HFS\bin\hython.exe" tests/houdini_phase3_benchmark.py
```

The original Phase 1 fixtures/report remain evidence; they were not rewritten
to imply semantic HDK callbacks.

## 17. Unverified interactive/API behavior

Still explicitly unverified:

- physical Network Editor drag cadence and mouse-release transaction boundary;
- physical clipboard paste timing (scripted `hou.copyNodesTo` passes);
- local undo versus redo direction/grouping and remote undo-stack behavior;
- arbitrary third-party OnCreated scripts beyond tested generic nested and
  multi-node scripted/copy scopes;
- interactive UI settle scheduling and licensed long-session responsiveness;
- DSO unload/static-destruction behavior (not claimed by capabilities);
- callback `void *data` meanings (never dereferenced);
- Houdini builds other than 21.0.729, Linux/macOS, and other compilers;
- a capability-gated HOM fallback;
- snapshot/checkpoint recovery and safe `.hip` save-copy APIs.

These do not expand the supported surface. Physical gesture and undo claims
must remain disabled until their own probe/contract evidence exists.

## 18. Recommended Phase 4

Phase 4 should connect the proven adapter and portable core across two real
Houdini processes over a direct-address LAN/VPN session. Scope it to:

1. bounded, authenticated-ready length framing and safe message validation;
2. join and exact capability negotiation, including Houdini/HDK/bridge and
   operator/parameter fingerprints;
3. real authority wiring for canonical transaction order and acknowledgements;
4. two-client apply/confirm health with truthful connected versus synchronized
   states;
5. retained history, reconnect/resume, original-ID resend, gap detection, and
   explicit history-unavailable handling;
6. only after direct-address sessions are trustworthy, passwordless LAN
   discovery as a convenience layer.

Do not add collaboration UI, presence, snapshot recovery, or collaborative
undo as incidental Phase 4 work. Do not connect the legacy relay. This report
is the Phase 3 stopping boundary.
