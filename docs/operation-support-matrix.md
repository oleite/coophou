# Operation support matrix

This document defines the recommended release scope. “Possible in Houdini” does not mean “supported by coophou.”

## Statuses

- **v1 candidate**: implement after the event probe and contract tests pass.
- **portable v1 contract**: strict Phase 2 domain/fake-scene behavior is implemented; real Houdini capture/application remains unverified until Phase 3.
- **v1 optional**: useful, but may be cut without weakening the core experience.
- **later**: requires a richer identity, transaction, or conflict model.
- **personal state**: presence-only or intentionally local; never durable scene synchronization.
- **unsupported**: outside the product contract until a new ADR changes it.

## Phase-1 evidence: Houdini 21.0.729 / Windows

These results come from fresh headless `hython` processes and do not promote any candidate to production support. Interactive UI gestures and other builds remain unverified.

| Candidate | Measured observation | Evidence boundary |
|---|---|---|
| Create one node | HOM: one `ChildCreated`; HDK: parent `OP_CHILD_CREATED` followed by 26 initialization/visibility/input events for the tested object node | Collect initialization through a bounded settle point; ignore HDK initialization noise rather than serializing it |
| Create copied subtree | IDs in `coophou.entity_id` were duplicated; copy emitted create, temporary/final rename, appearance, flag, and wiring bursts | One transaction after new-ID repair and subtree/wire collection; clipboard UI timing is still unverified |
| Delete node/subtree | HOM: `BeingDeleted` then parent `ChildDeleted`; HDK: `OP_NODE_PREDELETE`, `OP_NODE_DELETED`, then parent `OP_CHILD_DELETED` | Capture tombstone data at pre-delete; group descendant deletes under one root transaction |
| Rename | HOM supplied final path and `old_name`; HDK emitted one `OP_NAME_CHANGED` in the simple case | One final rename keyed by stable ID; path remains diagnostic |
| Move | One scripted `setPosition()` emitted two HOM/HDK move observations, including parent-network noise | Filter parent noise and coalesce to final position; actual drag cadence is unverified |
| Connect/disconnect | HOM and HDK each emitted one rewire event per set/unset; HOM supplied destination `input_index`, and the probe captured the current source/output | One destination-input edit with cached before-source and callback-time after-source |
| Simple parameter tuple | Raw integer/float/toggle/string/menu-token/tuple values were preserved. Tuple sets emitted per-component callbacks; menu raw token `mesh` evaluated to integer index `2` | Group component callbacks by tuple/gesture and use raw menu token, not evaluated index |
| Selected flags | Flag noise appeared around ordinary creation/copy and was not isolated into a reliable allowlist | Remains optional/unproven; do not include in the initial operation contract |
| Undo/redo | Candidate scripted edits replayed. HDK marked 45 observations `undo_or_redo`; HOM could not distinguish callback-time undo from redo | Treat one undo-stack action as one transaction only after a reliable boundary/correlation mechanism exists |
| Scene lifecycle | Save/merge/clear/load lifecycle pairs were observed; load nested clear | Not ordinary operations. Clear/load invalidate one scene generation; merge requires bounded create-transaction normalization or reconciliation |
| Locked HDA boundary | A locked custom HDA reported `inside_editable=false`; mutation raised `hou.PermissionError` | Reject edits across the permission boundary; do not claim locked-internal support |
| Temporary suppression | Three tuple callbacks retained HOM suppression depth/label during the scoped change | HOM probe proves scoped labeling; native correlation remains unresolved |

## v1 candidate operations

Phase 2 promotes the seven rows below to **portable v1 contract** status only.
That status does not claim a production Houdini adapter. Connect and disconnect
share one explicit destination-input operation.

| Operation | Identity | Capture concerns | Apply concerns | Conflict rule |
|---|---|---|---|---|
| Create one node | New node ID + parent ID | Parent `ChildCreated`; exact initialization may span callbacks | Exact type/name/position; operator availability | Canonical transaction; authority resolves final name |
| Create copied subtree | New IDs for every copied node | Must wait one event-loop turn and collect complete subtree/internal wires | Parent-before-child topological apply | Canonical transaction; duplicate IDs repaired before submit |
| Delete node/subtree | Existing root ID + descendant tombstones | Capture IDs before destruction; avoid dangling pointers | Delete only matching IDs | Canonical delete dominates later edits |
| Rename node | Node ID | Callback occurs after rename | Exact final canonical name | Later canonical rename wins |
| Move node | Node ID | High-frequency drag events | Layout-only mutation; coalesce | Latest accepted position wins |
| Connect input | Source/destination IDs + connector indices | `InputRewired` reports destination input | Validate operator and connector range | Later canonical connection wins or fails precondition |
| Disconnect input | Destination ID + input index + expected source | Must capture previous source | Disconnect only expected connection | Identity/precondition mismatch requires recovery |
| Simple parameter tuple set | Node ID + tuple name | `parm_tuple` may be `None`; high-frequency UI edits | Preserve raw typed value, not evaluated expression | Later canonical value wins |

## Definition of “simple parameter”

A v1 simple parameter:

- belongs to an ordinary `hou.OpNode`;
- is not a multiparm instance;
- is not a spare-parameter schema edit;
- is not animated;
- contains no expression or channel reference;
- is not time-dependent;
- is not a button or callback-only UI action;
- has a supported primitive value type;
- can be read and set without cooking-dependent semantic ambiguity;
- is writable in the current asset permission context.

Prefer initial support for:

- integer;
- float;
- toggle;
- string;
- menu token;
- fixed-size tuples of those values.

Menu tokens, not display labels, are canonical.

## v1 optional

| Operation | Reason optional |
|---|---|
| Bypass/template/display/render flags | Useful, but context-specific flag behavior must be probed |
| Node color/shape/comment | Technically ordinary state, but conflicts with presence visuals and personal graph organization |
| Batch node layout | Nice for copy/paste; can be represented as create transaction positions |
| Sticky “edit pulse” history | UI only; no scene operation |
| Follow another user | Presence feature, not synchronization |

## Later operations

| Operation family | Why later |
|---|---|
| Expressions and channel references | Must preserve language, raw expression, references, and dependency semantics |
| Keyframes and animation curves | Structured data, animation editor bulk events, undo complexity |
| Multiparms | Instance identity and reorder semantics |
| Spare parameter templates | Schema mutation and broad callback noise |
| Network boxes/sticky notes/dots | No proven persistent collaborative identity contract yet |
| HDA definition changes | Asset-library scope, permissions, shared filesystem, versioning |
| Locked HDA internals | Permission and definition ownership |
| Takes | Alternate value layers and active-take semantics |
| APEX | Different graph model and session IDs |
| LOP custom data/stage edits | Not all state maps to ordinary node operations |
| TOP work items | Runtime scheduler state, not scene-authoring state |
| DOP simulations | Runtime state, timing, caches, determinism |
| Geometry edits/caches | Potentially huge state and context-specific cooking |
| Viewer states/handles | Interaction mechanism, not necessarily durable scene state |
| Embedded files/assets | Large binary and security boundary |
| Environment variables/project config | Session capability/configuration, not casual edits |

## Personal or transient state

These features should use a separate lossy presence channel:

- user cursor position;
- active pane and network path;
- hovered node;
- selected nodes;
- typing or dragging indicator;
- active parameter;
- viewport camera pose when “follow” is enabled;
- user display name, avatar initials, and color;
- edit pulse;
- latency indicator.

Transient state:

- has a short time-to-live;
- is never appended to canonical operation history;
- is never used for recovery;
- never dirties the scene;
- may be dropped under load;
- is rate-limited and privacy-configurable.

## Unsupported by default

Do not serialize arbitrary:

- Python callbacks;
- node code sections;
- HDA libraries;
- shell commands;
- file paths for remote execution;
- custom object pointers;
- cooked geometry;
- opaque node data;
- pane layouts;
- desktop preferences.

## Per-operation contract checklist

Before moving an operation to **v1 candidate complete**, document and test:

1. Event trace on every supported Houdini build.
2. Stable target identity.
3. Plain payload schema.
4. Transaction boundary.
5. Precondition.
6. Deterministic apply algorithm.
7. Idempotent replay.
8. Conflict rule.
9. Local undo/redo behavior.
10. Remote echo suppression.
11. Reconnect behavior.
12. Scene-generation behavior.
13. Permission failure.
14. User-facing activity text.
15. Performance under a realistic network.
