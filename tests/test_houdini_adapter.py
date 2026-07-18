import json
import unittest

from coophou.core import FakeScene, MODEL_VERSION
from coophou.core.models import CreateNode, CreateNodeSpec, EntityRef, Transaction
from coophou.houdini_adapter import (
    NativeBridge,
    NativeBridgeError,
    SingleProcessOrchestrator,
    portable_semantic_snapshot,
)


def envelope(payload=None, *, error=None):
    if error is not None:
        return json.dumps(
            {
                "bridge_schema_version": 1,
                "ok": False,
                "error": error,
            }
        )
    return json.dumps(
        {
            "bridge_schema_version": 1,
            "ok": True,
            "payload": payload or {},
        }
    )


class FakeHou:
    def __init__(self):
        self.requests = []

    def _request(self, name, raw):
        self.requests.append((name, json.loads(raw)))
        return envelope({"name": name})

    def coophou_native_capabilities(self):
        return envelope({"production_adapter": "hdk_cpp"})

    def coophou_native_start_capture(self, raw):
        return self._request("start_capture", raw)

    def coophou_native_stop_capture(self):
        return envelope({"was_started": True})

    def coophou_native_capture_state(self):
        return envelope({"active": True})

    def coophou_native_flush_settle(self):
        return envelope({"settled": False})

    def coophou_native_drain_capture(self, raw):
        return self._request("drain_capture", raw)

    def coophou_native_extract_snapshot(self, raw):
        return self._request("extract_snapshot", raw)

    def coophou_native_enqueue_apply(self, raw):
        return self._request("enqueue_apply", raw)

    def coophou_native_drain_apply(self, raw):
        return self._request("drain_apply", raw)

    def coophou_native_reset_for_tests(self, raw):
        return self._request("reset_for_tests", raw)


class StubBridge:
    def __init__(self, records=()):
        self.records = list(records)
        self.enqueued = []

    def flush_settle(self):
        return {"settled": True}

    def drain_capture(self, max_count=64):
        records, self.records = self.records[:max_count], self.records[max_count:]
        return {"records": records, "remaining": len(self.records), "overflow": False}

    def enqueue_apply(self, transaction, scene_generation, correlation_id):
        self.enqueued.append((transaction, scene_generation, correlation_id))
        return {"queued": True}

    def drain_apply(self, max_transactions=8, max_operations=64):
        transaction = self.enqueued[-1][0]
        return {
            "results": [
                {
                    "bridge_schema_version": 1,
                    "ok": True,
                    "payload": {
                        "status": "APPLIED_VERIFIED",
                        "transaction_id": transaction.transaction_id,
                    },
                }
            ],
            "remaining": 0,
        }


def create_candidate(entity_id="node-1", name="created"):
    reference = lambda value, path: {
        "version": 1,
        "entity_id": value,
        "entity_kind": "node",
        "last_known_path": path,
    }
    return {
        "version": 1,
        "operation_type": "node.create",
        "spec": {
            "version": 1,
            "entity": reference(entity_id, f"/obj/{name}"),
            "parent": reference("root", "/obj"),
            "operator_type": "geo",
            "name": name,
            "position": [1.0, 2.0],
            "initial_parameters": [],
        },
    }


class NativeBridgeTests(unittest.TestCase):
    def test_bridge_round_trips_sorted_plain_json(self):
        hou = FakeHou()
        bridge = NativeBridge(hou)
        self.assertEqual(bridge.capabilities()["production_adapter"], "hdk_cpp")
        bridge.start_capture(root_path="/obj")
        self.assertEqual(hou.requests[0][0], "start_capture")
        self.assertEqual(hou.requests[0][1]["bridge_schema_version"], 1)

    def test_native_snapshot_normalizes_to_fake_scene_semantics(self):
        native = {
            "snapshot_schema_version": 1,
            "scene_generation": 7,
            "root": {"entity_id": "root", "native_path": "/obj/collab"},
            "nodes": [
                {
                    "version": 1,
                    "entity_id": "node-1",
                    "parent_id": "root",
                    "operator_type": "null",
                    "name": "created",
                    "native_path": "/obj/collab/created",
                    "position": [1, 2],
                    "parameters": {},
                    "inputs": {},
                }
            ],
            "tombstones": [],
        }
        scene = FakeScene.initial()
        operation = CreateNode(
            MODEL_VERSION,
            "operation-projection",
            CreateNodeSpec(
                MODEL_VERSION,
                EntityRef(MODEL_VERSION, "node-1"),
                EntityRef(MODEL_VERSION, "root"),
                "null",
                "created",
                (1.0, 2.0),
                (),
            ),
        )
        transaction = Transaction(
            MODEL_VERSION,
            "transaction-projection",
            "client",
            "session",
            (operation,),
            None,
            (operation.operation_type,),
        )
        self.assertTrue(scene.apply_transaction(transaction).success)
        self.assertEqual(portable_semantic_snapshot(native), scene.semantic_snapshot())

    def test_missing_function_fails_closed(self):
        with self.assertRaises(NativeBridgeError) as caught:
            NativeBridge(object())
        self.assertEqual(caught.exception.code, "BRIDGE_UNAVAILABLE")

class OrchestratorTests(unittest.TestCase):
    def ids(self):
        counter = iter(("operation-1", "transaction-1", "correlation-1"))
        return lambda prefix: next(counter)

    def test_native_change_set_becomes_frozen_transaction_and_confirms(self):
        record = {
            "bridge_schema_version": 1,
            "record_type": "capture.change_set",
            "scene_generation": 1,
            "operations": [create_candidate()],
        }
        orchestrator = SingleProcessOrchestrator(
            bridge=StubBridge([record]), id_factory=self.ids()
        )
        accepted, adapter_records, remaining = orchestrator.capture_local()
        self.assertEqual(len(accepted), 1)
        self.assertEqual(adapter_records, [])
        self.assertEqual(remaining, 0)
        self.assertEqual(accepted[0].transaction.transaction_id, "transaction-1")
        self.assertEqual(accepted[0].transaction.operations[0].operation_id, "operation-1")
        self.assertTrue(orchestrator.client.is_synchronized)
        self.assertIn("node-1", orchestrator.client.confirmed_scene.entities)

    def test_native_candidate_cannot_smuggle_operation_id(self):
        candidate = create_candidate()
        candidate["operation_id"] = "native-owned-id"
        orchestrator = SingleProcessOrchestrator(
            bridge=StubBridge(), id_factory=self.ids()
        )
        with self.assertRaises(ValueError):
            orchestrator.transaction_from_change_set(
                {
                    "bridge_schema_version": 1,
                    "record_type": "capture.change_set",
                    "operations": [candidate],
                }
            )

    def test_remote_transaction_is_serialized_to_native_gateway(self):
        bridge = StubBridge()
        orchestrator = SingleProcessOrchestrator(
            bridge=bridge, id_factory=self.ids()
        )
        operation = CreateNode(
            MODEL_VERSION,
            "operation-remote",
            CreateNodeSpec(
                MODEL_VERSION,
                EntityRef(MODEL_VERSION, "remote-node", last_known_path="/obj/remote"),
                EntityRef(MODEL_VERSION, "root", last_known_path="/obj"),
                "geo",
                "remote",
                (0.0, 0.0),
                (),
            ),
        )
        transaction = Transaction(
            MODEL_VERSION,
            "transaction-remote",
            "other-client",
            orchestrator.session_id,
            (operation,),
            None,
            (operation.operation_type,),
        )
        result = orchestrator.apply_remote(transaction, 7, "correlation-explicit")
        self.assertEqual(result["status"], "APPLIED_VERIFIED")
        self.assertEqual(bridge.enqueued[0][1:], (7, "correlation-explicit"))


if __name__ == "__main__":
    unittest.main()
