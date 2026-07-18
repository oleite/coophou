# ADR 0002: Use persistent node user data as the v1 identity carrier

- **Status:** Accepted
- **Date:** 2026-07-17
- **Owners:** coophou maintainers
- **Supersedes:** None
- **Superseded by:** None

## Context

Houdini node paths change and may be reused. Session IDs are process-local. coophou requires identity that survives rename, save/load, and reconnect.

Houdini supports string user data saved with the `.hip` file through HOM and HDK.

## Decision

For ordinary v1 nodes, store a namespaced UUID in persistent node user data:

```text
coophou.entity_id
```

Optional versioned metadata may use:

```text
coophou.identity = {"version": 1, "entity_id": "..."}
```

The single-value form is preferred until structured metadata is necessary.

Paths remain diagnostic only.

## Required behavior

- assign an ID before submitting creation;
- persist through save/load;
- retain tombstones after deletion for the session/history window;
- detect duplicate IDs after copy/paste;
- assign new IDs to every newly copied entity before the create transaction is submitted;
- suppress internal identity metadata from user-operation capture;
- never repair an identity mismatch by path-only lookup;
- reset lookup caches on scene replacement.

## Limitations

Phase 2 proves the identity semantics in the fake scene: `entity_id` is the
only lookup key, paths are derived diagnostics, copied payloads require unique
repaired IDs, deleted IDs become session tombstones, and path reuse cannot
redirect an old operation. Persisting and repairing `coophou.entity_id` in a
real Houdini scene remains Phase 3 adapter work.

Network boxes, sticky notes, dots, APEX items, and other objects without a proven equivalent identity mechanism are not covered by this ADR.

## Migration

If a scene contains no IDs, joining may:

- assign IDs as one initialization transaction when starting a new authoritative session; or
- compare against an authoritative checkpoint before writing IDs.

Never mass-tag a scene silently during an incompatible join.

## Testing

- rename;
- save/load;
- copy/paste;
- duplicate subtree;
- delete and path reuse;
- undo deletion;
- merge another `.hip`;
- locked asset;
- malformed/duplicate ID;
- identity cache invalidation.
