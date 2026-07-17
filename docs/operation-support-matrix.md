# Operation support matrix

This document defines the recommended release scope. “Possible in Houdini” does not mean “supported by coophou.”

## Statuses

- **v1 candidate**: implement after the event probe and contract tests pass.
- **v1 optional**: useful, but may be cut without weakening the core experience.
- **later**: requires a richer identity, transaction, or conflict model.
- **personal state**: presence-only or intentionally local; never durable scene synchronization.
- **unsupported**: outside the product contract until a new ADR changes it.

## v1 candidate operations

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
| Selected node flags | Node ID + explicit flag | One callback may cover several flags | Apply allowlisted flags only | Later canonical flag value wins |

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
