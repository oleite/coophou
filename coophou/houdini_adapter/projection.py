"""Strict conversion of a native supported snapshot to Phase 2 semantics."""

from __future__ import annotations

from coophou.core import FakeScene, MODEL_VERSION
from coophou.core.models import (
    ConnectionRef,
    EntityRef,
    ParameterTupleValue,
    validate_identifier,
)
from coophou.core.scene import SceneEntity, Tombstone


def _exact(data, required, label):
    if not isinstance(data, dict) or set(data) != set(required):
        raise ValueError(f"{label} fields do not match the snapshot schema")


def portable_semantic_snapshot(native):
    """Normalize the configured Houdini root to the portable synthetic root."""
    _exact(
        native,
        (
            "snapshot_schema_version",
            "scene_generation",
            "root",
            "nodes",
            "tombstones",
        ),
        "native snapshot",
    )
    if native["snapshot_schema_version"] != 1:
        raise ValueError("unsupported native snapshot schema version")
    _exact(native["root"], ("entity_id", "native_path"), "snapshot root")
    root_id = validate_identifier(native["root"]["entity_id"], "root entity ID")
    root_path = native["root"]["native_path"]
    if root_id != "root" or not isinstance(root_path, str) or not root_path.startswith("/"):
        raise ValueError("native snapshot root mapping is invalid")
    if not isinstance(native["nodes"], list) or not isinstance(native["tombstones"], list):
        raise ValueError("native snapshot collections must be arrays")

    by_id = {}
    for node in native["nodes"]:
        _exact(
            node,
            (
                "version",
                "entity_id",
                "parent_id",
                "operator_type",
                "name",
                "native_path",
                "position",
                "parameters",
                "inputs",
            ),
            "snapshot node",
        )
        entity_id = validate_identifier(node["entity_id"], "entity ID")
        validate_identifier(node["parent_id"], "parent ID")
        if node["version"] != MODEL_VERSION or entity_id in by_id:
            raise ValueError("snapshot node version or identity is invalid")
        if (
            not isinstance(node["operator_type"], str)
            or not isinstance(node["name"], str)
            or not isinstance(node["native_path"], str)
            or not isinstance(node["position"], list)
            or len(node["position"]) != 2
            or not isinstance(node["parameters"], dict)
            or not isinstance(node["inputs"], dict)
        ):
            raise ValueError("snapshot node value shape is invalid")
        parameters = {
            name: ParameterTupleValue.from_dict(value).to_dict()
            for name, value in node["parameters"].items()
        }
        inputs = {}
        for index, connection in node["inputs"].items():
            _exact(connection, ("source_entity_id", "output_index"), "snapshot input")
            validate_identifier(connection["source_entity_id"], "source entity ID")
            if not index.isdigit() or type(connection["output_index"]) is not int:
                raise ValueError("snapshot input index is invalid")
            inputs[str(int(index))] = dict(connection)
        by_id[entity_id] = {
            **node,
            "parameters": parameters,
            "inputs": inputs,
        }

    def path(entity_id, visiting=()):
        if entity_id == root_id:
            return "/"
        if entity_id in visiting or entity_id not in by_id:
            raise ValueError("snapshot hierarchy is missing a parent or contains a cycle")
        node = by_id[entity_id]
        parent = path(node["parent_id"], (*visiting, entity_id))
        return (parent.rstrip("/") + "/" + node["name"]) or "/"

    entities = [
        {
            "version": MODEL_VERSION,
            "entity_id": root_id,
            "parent_id": None,
            "operator_type": "root",
            "name": "",
            "path": "/",
            "position": [0.0, 0.0],
            "parameters": {},
            "inputs": {},
        }
    ]
    for entity_id in sorted(by_id):
        node = by_id[entity_id]
        for connection in node["inputs"].values():
            if connection["source_entity_id"] not in by_id:
                raise ValueError("snapshot input source is outside the supported snapshot")
        entities.append(
            {
                "version": MODEL_VERSION,
                "entity_id": entity_id,
                "parent_id": node["parent_id"],
                "operator_type": node["operator_type"],
                "name": node["name"],
                "path": path(entity_id),
                "position": [float(value) for value in node["position"]],
                "parameters": node["parameters"],
                "inputs": node["inputs"],
            }
        )

    tombstones = []
    live_ids = set(by_id) | {root_id}
    for deleted in native["tombstones"]:
        _exact(
            deleted,
            ("version", "entity_id", "parent_id", "last_known_native_path"),
            "snapshot tombstone",
        )
        entity_id = validate_identifier(deleted["entity_id"], "tombstone entity ID")
        if entity_id in live_ids or deleted["version"] != MODEL_VERSION:
            raise ValueError("snapshot tombstone conflicts with live state")
        native_path = deleted["last_known_native_path"]
        if not isinstance(native_path, str) or not native_path.startswith(root_path + "/"):
            raise ValueError("snapshot tombstone path is outside the configured root")
        tombstones.append(
            {
                "version": MODEL_VERSION,
                "entity_id": entity_id,
                "parent_id": deleted["parent_id"],
                "last_known_path": native_path[len(root_path) :],
            }
        )
    return {
        "version": MODEL_VERSION,
        "entities": sorted(entities, key=lambda item: item["entity_id"]),
        "tombstones": sorted(tombstones, key=lambda item: item["entity_id"]),
    }


def fake_scene_from_native_snapshot(native):
    """Materialize the strict native projection as a Phase 2 FakeScene."""
    semantic = portable_semantic_snapshot(native)
    scene = FakeScene.initial()
    scene.entities.clear()
    for entity in semantic["entities"]:
        scene.entities[entity["entity_id"]] = SceneEntity(
            version=entity["version"],
            entity_id=entity["entity_id"],
            parent_id=entity["parent_id"],
            operator_type=entity["operator_type"],
            name=entity["name"],
            position=tuple(entity["position"]),
            parameters={
                name: ParameterTupleValue.from_dict(value)
                for name, value in entity["parameters"].items()
            },
            inputs={},
        )
    for entity in semantic["entities"]:
        target = scene.entities[entity["entity_id"]]
        target.inputs = {
            int(index): ConnectionRef(
                MODEL_VERSION,
                EntityRef(MODEL_VERSION, value["source_entity_id"]),
                value["output_index"],
            )
            for index, value in entity["inputs"].items()
        }
    scene.tombstones = {
        value["entity_id"]: Tombstone(
            value["version"],
            value["entity_id"],
            value["parent_id"],
            value["last_known_path"],
        )
        for value in semantic["tombstones"]
    }
    return scene
