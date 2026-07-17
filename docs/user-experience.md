# User experience

coophou should feel like Houdini gained collaborators, not like Houdini was wrapped in a distributed-systems control panel.

## Product promise

For supported edits:

- local work feels immediate;
- collaborators appear present but not distracting;
- remote changes are understandable;
- conflicts are calm and recoverable;
- network problems do not interrupt creative flow;
- leaving collaboration never traps or destroys the scene.

Correctness is the foundation. Delight comes from making correctness quiet.

## Core principles

### Local-first interaction

The local Houdini action completes normally. Network submission happens afterward.

Never:

- disable ordinary editing while waiting for an acknowledgement;
- show a spinner for every parameter change;
- make cursor movement depend on round-trip latency.

### Presence without scene pollution

Use temporary network-editor overlays and the collaboration panel.

Do not:

- recolor actual nodes to show ownership;
- write collaborator names into comments;
- create sticky notes for presence;
- persist cursors or selections into the `.hip`.

### Calm truthfulness

Show the smallest honest state:

- **Live** — synchronized.
- **Catching up** — connected, applying missed edits.
- **Offline, keeping your work** — local actions are following the configured offline policy.
- **Needs attention** — collaboration paused; local scene preserved.

Do not expose protocol vocabulary as the primary UI.

### Progressive disclosure

The default view should show:

- session name;
- people;
- current health;
- pending local edits;
- latest activity.

Detailed sequences, operation IDs, queues, and recovery controls belong in an expandable diagnostics area.

## Primary user journeys

### Join a session

1. User opens a project-compatible `.hip`.
2. Opens the coophou panel.
3. Chooses or enters a session.
4. coophou checks capability compatibility.
5. A short summary explains whether the local scene matches the session checkpoint.
6. The user joins or is offered a safe import/fork path.
7. Presence appears immediately.
8. Durable editing becomes available only after catch-up is complete.

Avoid a wall of configuration fields. Remember recent identity and server choices locally.

### Edit together

- The local edit is immediate.
- A subtle pending indicator appears only when confirmation is not nearly instant.
- Remote edits pulse briefly around affected nodes.
- The activity feed says, for example, “Maya connected `scatter1` to `merge2`.”
- Clicking the activity frames the affected network item without changing selection unless requested.
- Frequent parameter and movement updates are coalesced.

### Follow a collaborator

Follow mode is opt-in.

It may:

- navigate to the collaborator's network path;
- frame their active node;
- optionally mirror their viewport camera in a separate mode.

It must:

- be easy to stop with Esc or a visible button;
- never steal focus during typing;
- not consume ordinary Houdini events unnecessarily;
- use transient presence only.

### Disconnect

- The user can leave the session from the panel.
- coophou flushes or preserves pending local edits according to policy.
- callbacks and overlays are removed.
- the scene remains open and usable.
- no presence metadata remains in the scene.

### Recover from a gap or failed operation

1. Status changes from Live to Catching up or Needs attention.
2. Local input follows the configured safe policy.
3. coophou attempts bounded replay.
4. Before destructive repair, it saves a recovery artifact if possible.
5. The user sees a plain explanation and recommended action.
6. Diagnostics remain available.

No routine reconnect modal.

## Collaboration panel

Recommended sections:

### Header

- session name;
- Live/Catching up/Offline/Needs attention state;
- compact latency indicator;
- leave button.

### People

For each collaborator:

- display name;
- initials/avatar;
- accessible color plus icon/label;
- current network path;
- idle/editing/offline state;
- follow button.

### Activity

A bounded, human-readable feed:

- “Ana created `attribwrangle3`.”
- “Gabriel changed `scatter1` Density.”
- “Ravi undid Move `merge2`.”
- “You are caught up.”

Group bursty operations into transactions.

### Pending and recovery

Shown only when relevant:

- local edits waiting for confirmation;
- catch-up progress;
- preserved recovery artifact;
- retry/reconcile/leave actions.

### Diagnostics

Expandable:

- protocol and bridge versions;
- last confirmed sequence;
- queue depths;
- event-probe mode;
- recent structured errors.

## Network-editor presence

Use `hou.NetworkEditor.setOverlayShapes` or an equivalent non-persistent overlay owner.

Recommended visuals:

- collaborator cursor with initials;
- soft ring/outline on active or recently edited nodes;
- short connection animation for a new wire;
- small off-screen direction marker when following someone;
- subtle fade after activity.

Rules:

- maintain one overlay composition service so tools do not overwrite each other's shapes;
- restore or remove only shapes owned by coophou;
- rate-limit redraw;
- hide presence below a useful zoom threshold;
- cap visible collaborators and cluster excess presence;
- never use actual node selection for remote selection;
- never change actual node color for remote identity.

## Transient presence protocol

Presence messages may include:

- user ID and display name;
- assigned accessible theme token;
- network path;
- cursor position in network coordinates;
- selected entity IDs;
- active entity/parameter;
- gesture state;
- follow-compatible viewport pose;
- timestamp and sequence local to that user.

Presence:

- expires after a short TTL;
- can be dropped or superseded;
- is not acknowledged individually;
- is rate-limited;
- is disabled or reduced in privacy mode;
- never participates in canonical recovery.

## Gesture experience

### Node movement

During drag:

- publish lossy preview positions at a bounded rate;
- render remote ghost movement;
- commit the final position as one durable operation or transaction after mouse-up/inactivity.

If reliable mouse-up capture is unavailable for a context, coalesce position changes over a short window and commit the last value.

### Parameter editing

Generic parameter callbacks do not always expose gesture begin/end.

Recommended policy:

- capture raw supported values;
- publish optional transient preview at a bounded rate;
- debounce durable commits;
- flush on focus loss, scene save, disconnect, or a different operation;
- never debounce structural operations;
- show only one activity item per gesture.

A v1 may skip previews and simply coalesce rapid accepted updates.

### Copy/paste

Treat a pasted subtree as one transaction:

- assign new IDs;
- collect nodes and internal wires after Houdini completes the paste;
- show one activity item;
- apply parent-before-child on peers;
- frame the result only for the initiating user unless others choose to follow.

## Undo experience

Recommended v1:

- remote applies are excluded from the local Houdini undo stack;
- local Ctrl+Z/Ctrl+Y remains ordinary Houdini behavior;
- resulting local callbacks form a new collaborative transaction;
- activity describes it as an undo/redo action when detectable.

This means undo does not erase canonical history. It creates a new accepted state change.

The panel should explain this only when relevant, not on every undo.

## Conflict experience

### Benign overwrite

For scalar last-writer-wins:

- apply canonical result;
- briefly indicate who changed the value;
- avoid a modal.

### User is actively editing the same property

Use soft intent:

- “Ana is editing Density.”
- do not hard-lock by default;
- warn before a likely overwrite only when it can be done without disrupting typing;
- allow teams to enable stricter policy later.

### Structural conflict

Pause the affected transaction, not the whole UI when safe.

Show:

- affected node;
- plain explanation;
- preserved work status;
- recommended recovery.

Never silently attach the edit to a similarly named node.

## Latency and performance budgets

Budgets are release goals, not proof of correctness.

### Local interaction

- no network wait on local input;
- callback capture target: under 1 ms for ordinary events;
- no full-scene scan inside a callback;
- expensive normalization deferred.

### Main-thread application

- target less than 8 ms of coophou work per event-loop slice;
- chunk catch-up batches;
- yield between chunks;
- combine redraws;
- expose progress for long catch-up.

### Presence

- cursor preview target: 8–15 updates/second;
- remote redraw target: at most display refresh needs;
- drop stale previews rather than queueing them.

### Durable operations

- coalesce node moves and supported parameter gestures;
- canonical acknowledgement should normally feel instant on a LAN;
- show pending UI only after a small grace period to avoid flicker.

## Accessibility

- do not encode identity by color alone;
- choose color tokens with contrast checks;
- support reduced motion;
- allow presence opacity and cursor visibility controls;
- preserve readable text scaling;
- provide keyboard access to follow/leave/recovery;
- keep status messages concise;
- do not require audio cues.

## Privacy

Users may disable:

- cursor sharing;
- selection sharing;
- active parameter sharing;
- viewport sharing;
- activity detail beyond operation type.

Project administrators may enforce minimum audit data for durable operations, but ephemeral presence should remain configurable.

## UX release gates

A release candidate should pass:

1. Two artists can join and understand the state without documentation.
2. Ordinary local editing feels unchanged.
3. Remote edits are visible but not noisy.
4. Disconnect/reconnect does not interrupt with routine modals.
5. A failed structural operation preserves work and explains next steps.
6. Presence never dirties the scene.
7. A user can leave and continue working normally.
8. Ten minutes of parameter and node movement does not create an unusable activity feed.
9. Reduced-motion and color-independent identity remain usable.
10. Participants prefer the workflow to manually exchanging `.hip` files for the tested task.
