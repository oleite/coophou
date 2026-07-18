"""Real Houdini 21.0.729 contract tests for the Phase 3 native adapter.

HOM is used only to build fixtures and independently inspect final state. The
capture and application work under test is performed by the HDK DSO.
"""

from __future__ import annotations

import itertools
import importlib
import os
import tempfile
import unittest

import hou

from coophou.core import MODEL_VERSION
from coophou.core.models import (
    ConnectionRef,
    CreateNode,
    CreateNodeSpec,
    CreateSubtree,
    DeleteSubtree,
    EntityRef,
    MoveNode,
    NamedParameterValue,
    OperationType,
    ParameterTupleValue,
    RawValueKind,
    RenameNode,
    SetInput,
    SetParameterTuple,
    SubtreeConnection,
    Transaction,
    operation_from_dict,
)
from coophou.houdini_adapter import (
    NativeBridge,
    NativeBridgeError,
    fake_scene_from_native_snapshot,
)


class NativeHoudiniContract(unittest.TestCase):
    ids = itertools.count(1)

    def setUp(self):
        self.bridge = NativeBridge(hou)
        self.bridge.stop_capture()
        hou.hipFile.clear(suppress_save_prompt=True)
        self.root = hou.node("/obj").createNode("geo", "phase3_root")
        for child in self.root.children():
            child.destroy()
        started = self.bridge.start_capture(
            root_path=self.root.path(),
            root_entity_id="root",
            deterministic_id_prefix=f"contract{next(self.ids)}",
            operator_types=["null", "merge", "subnet"],
            parameter_names=["cacheinput"],
            parameter_kinds={"cacheinput": "boolean"},
            max_nodes=256,
            capture_queue_limit=64,
            apply_queue_limit=16,
        )
        self.generation = started["scene_generation"]
        self.portable_scene = fake_scene_from_native_snapshot(
            self.bridge.extract_snapshot()
        )

    def tearDown(self):
        self.bridge.stop_capture()

    @staticmethod
    def ref(entity_id, path=None):
        return EntityRef(MODEL_VERSION, entity_id, last_known_path=path)

    @staticmethod
    def bool_value(value):
        return ParameterTupleValue(
            MODEL_VERSION, RawValueKind.BOOLEAN, (value,)
        )

    def null_spec(self, entity_id, name, position=(0.0, 0.0), parent=None):
        parent = parent or self.ref("root", self.root.path())
        parent_path = parent.last_known_path or self.root.path()
        return CreateNodeSpec(
            MODEL_VERSION,
            self.ref(entity_id, f"{parent_path}/{name}"),
            parent,
            "null",
            name,
            position,
            (
                NamedParameterValue(
                    MODEL_VERSION, "cacheinput", self.bool_value(False)
                ),
            ),
        )

    def transaction(self, *operations):
        suffix = next(self.ids)
        return Transaction(
            MODEL_VERSION,
            f"transaction-{suffix}",
            "remote-client",
            "contract-session",
            tuple(operations),
            "Phase 3 contract",
            tuple(dict.fromkeys(op.operation_type for op in operations)),
        )

    def apply(self, *operations):
        transaction = self.transaction(*operations)
        expected = fake_scene_from_native_snapshot(self.bridge.extract_snapshot())
        portable_result = expected.apply_transaction(transaction)
        self.assertTrue(portable_result.success, portable_result.error)
        self.bridge.enqueue_apply(
            transaction, self.generation, f"correlation-{transaction.transaction_id}"
        )
        drained = self.bridge.drain_apply(
            max_transactions=1, max_operations=len(operations)
        )
        self.assertEqual(drained["remaining"], 0)
        self.assertEqual(len(drained["results"]), 1)
        result = drained["results"][0]
        self.assertTrue(result["ok"], result.get("error"))
        self.assertEqual(result["payload"]["status"], "APPLIED_VERIFIED")
        actual = fake_scene_from_native_snapshot(self.bridge.extract_snapshot())
        self.assertEqual(actual.semantic_snapshot(), expected.semantic_snapshot())
        self.bridge.flush_settle()
        capture = self.bridge.drain_capture(max_count=64)
        self.assertEqual(capture["records"], [], "remote apply echoed as local capture")
        return transaction, result["payload"]

    def reject_apply(self, expected_code, *operations):
        transaction = self.transaction(*operations)
        self.bridge.enqueue_apply(
            transaction,
            self.generation,
            f"reject-{transaction.transaction_id}",
        )
        result = self.bridge.drain_apply(
            max_transactions=1, max_operations=len(operations)
        )["results"][0]
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], expected_code)
        return result["error"]

    def capture(self):
        settled = self.bridge.flush_settle()
        drained = self.bridge.drain_capture(max_count=64)
        change_sets = [
            record
            for record in drained["records"]
            if record.get("record_type") == "capture.change_set"
        ]
        self.assertEqual(len(change_sets), 1, drained)
        candidates = change_sets[0]["operations"]
        operations = []
        for index, candidate in enumerate(candidates):
            operations.append(
                operation_from_dict(
                    {
                        **candidate,
                        "operation_id": f"captured-operation-{next(self.ids)}-{index}",
                    }
                )
            )
        self.assertEqual(settled["operation_count"], len(operations))
        portable_result = self.portable_scene.apply_transaction(
            self.transaction(*operations)
        )
        self.assertTrue(portable_result.success, portable_result.error)
        actual = fake_scene_from_native_snapshot(self.bridge.extract_snapshot())
        self.assertEqual(actual.semantic_snapshot(), self.portable_scene.semantic_snapshot())
        return operations, change_sets[0]

    def create_fixture_null(self, name, position=(0.0, 0.0)):
        node = self.root.createNode("null", name)
        node.setPosition(position)
        return node

    # Local capture direction -------------------------------------------------

    def test_capture_create_node(self):
        node = self.create_fixture_null("captured_create", (1.0, 2.0))
        operations, _ = self.capture()
        self.assertEqual([op.operation_type for op in operations], [OperationType.CREATE_NODE])
        self.assertEqual(operations[0].spec.name, "captured_create")
        self.assertIsNotNone(node.userData("coophou.entity_id"))

    def test_capture_create_includes_immediate_supported_parameter_value(self):
        node = self.create_fixture_null("create_with_parameter")
        node.parm("cacheinput").set(1)
        operations, _ = self.capture()
        self.assertEqual(len(operations), 1)
        self.assertIsInstance(operations[0], CreateNode)
        values = {
            parameter.name: parameter.value
            for parameter in operations[0].spec.initial_parameters
        }
        self.assertEqual(values["cacheinput"], self.bool_value(True))

    def test_capture_create_subtree_and_repairs_copy_ids(self):
        first = self.create_fixture_null("source_a")
        second = self.create_fixture_null("source_b")
        second.setInput(0, first)
        self.capture()
        first_id = first.userData("coophou.entity_id")
        second_id = second.userData("coophou.entity_id")

        copies = hou.copyNodesTo((first, second), self.root)
        operations, _ = self.capture()
        subtrees = [op for op in operations if isinstance(op, CreateSubtree)]
        self.assertEqual(len(subtrees), 1, operations)
        copied_ids = {node.userData("coophou.entity_id") for node in copies}
        self.assertTrue(copied_ids.isdisjoint({first_id, second_id}))
        self.assertEqual(len(copied_ids), 2)
        self.assertEqual(len(subtrees[0].connections), 1)

    def test_capture_nested_generated_scope_is_parent_before_child(self):
        subnet = self.root.createNode("subnet", "generated_parent")
        child = subnet.createNode("null", "generated_child")
        operations, _ = self.capture()
        self.assertEqual(len(operations), 1, operations)
        self.assertIsInstance(operations[0], CreateSubtree)
        self.assertEqual(
            [spec.name for spec in operations[0].nodes],
            ["generated_parent", "generated_child"],
        )
        self.assertNotEqual(
            subnet.userData("coophou.entity_id"),
            child.userData("coophou.entity_id"),
        )

    def test_capture_delete_subtree_uses_predelete_identity_set(self):
        subnet = self.root.createNode("subnet", "delete_subnet")
        child = subnet.createNode("null", "delete_child")
        self.capture()
        expected = (
            subnet.userData("coophou.entity_id"),
            child.userData("coophou.entity_id"),
        )
        subnet.destroy()
        operations, _ = self.capture()
        deletes = [op for op in operations if isinstance(op, DeleteSubtree)]
        self.assertEqual(len(deletes), 1, operations)
        self.assertEqual(deletes[0].deleted_entity_ids, expected)

    def test_capture_rename(self):
        node = self.create_fixture_null("rename_before")
        self.capture()
        node.setName("rename_after")
        operations, _ = self.capture()
        renames = [op for op in operations if isinstance(op, RenameNode)]
        self.assertEqual(len(renames), 1, operations)
        self.assertEqual((renames[0].expected_name, renames[0].name), ("rename_before", "rename_after"))

    def test_capture_move_coalesces_to_final_position(self):
        node = self.create_fixture_null("move_capture")
        self.capture()
        for position in ((1.0, 1.0), (2.0, 3.0), (8.0, -4.0)):
            node.setPosition(position)
        operations, _ = self.capture()
        moves = [op for op in operations if isinstance(op, MoveNode)]
        self.assertEqual(len(moves), 1, operations)
        self.assertEqual(moves[0].position, (8.0, -4.0))

    def test_capture_set_input_connect_and_disconnect(self):
        source = self.create_fixture_null("wire_source")
        destination = self.create_fixture_null("wire_destination")
        self.capture()
        destination.setInput(0, source)
        operations, _ = self.capture()
        wires = [op for op in operations if isinstance(op, SetInput)]
        self.assertEqual(len(wires), 1, operations)
        self.assertIsNotNone(wires[0].new_source)
        destination.setInput(0, None)
        operations, _ = self.capture()
        wires = [op for op in operations if isinstance(op, SetInput)]
        self.assertEqual(len(wires), 1, operations)
        self.assertIsNone(wires[0].new_source)

    def test_capture_parameter_tuple_preserves_boolean_raw_shape(self):
        node = self.create_fixture_null("parameter_capture")
        self.capture()
        node.parmTuple("cacheinput").set((True,))
        operations, _ = self.capture()
        parameters = [op for op in operations if isinstance(op, SetParameterTuple)]
        self.assertEqual(len(parameters), 1, operations)
        self.assertEqual(parameters[0].value, self.bool_value(True))
        self.assertEqual(parameters[0].expected_value, self.bool_value(False))

    # Remote application direction ------------------------------------------

    def test_apply_create_node(self):
        operation = CreateNode(
            MODEL_VERSION, "operation-create", self.null_spec("remote-create", "remote_create", (2.0, 3.0))
        )
        transaction, _ = self.apply(operation)
        node = self.root.node("remote_create")
        self.assertEqual(node.userData("coophou.entity_id"), "remote-create")
        self.assertEqual(tuple(node.position()), (2.0, 3.0))
        self.bridge.enqueue_apply(transaction, self.generation, "replay-create")
        replay = self.bridge.drain_apply(max_transactions=1, max_operations=1)["results"][0]
        self.assertEqual(replay["payload"]["status"], "APPLIED_REPLAY")

    def test_apply_create_subtree_with_internal_connection(self):
        first = self.null_spec("remote-a", "remote_a", (0.0, 0.0))
        second = self.null_spec("remote-b", "remote_b", (3.0, 0.0))
        connection = SubtreeConnection(
            MODEL_VERSION,
            second.entity,
            0,
            ConnectionRef(MODEL_VERSION, first.entity, 0),
        )
        self.apply(
            CreateSubtree(
                MODEL_VERSION,
                "operation-subtree",
                (first, second),
                (connection,),
            )
        )
        self.assertEqual(self.root.node("remote_b").inputs()[0], self.root.node("remote_a"))

    def test_apply_delete_and_path_reuse_cannot_retarget_old_id(self):
        node = self.create_fixture_null("reused_name")
        self.capture()
        old_id = node.userData("coophou.entity_id")
        delete = DeleteSubtree(
            MODEL_VERSION,
            "operation-delete",
            self.ref(old_id, node.path()),
            (old_id,),
            "root",
        )
        self.apply(delete)
        self.assertIsNone(self.root.node("reused_name"))
        replacement = CreateNode(
            MODEL_VERSION,
            "operation-replacement",
            self.null_spec("replacement-id", "reused_name"),
        )
        self.apply(replacement)
        stale_rename = RenameNode(
            MODEL_VERSION,
            "operation-stale-rename",
            self.ref(old_id, f"{self.root.path()}/reused_name"),
            "must_not_apply",
            "reused_name",
        )
        tx = self.transaction(stale_rename)
        self.bridge.enqueue_apply(tx, self.generation, "stale-old-id")
        result = self.bridge.drain_apply(max_transactions=1, max_operations=1)["results"][0]
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "APPLICATION_PREVALIDATION_FAILED")
        self.assertEqual(self.root.node("reused_name").userData("coophou.entity_id"), "replacement-id")

    def test_apply_rename(self):
        node = self.create_fixture_null("remote_rename_before")
        self.capture()
        entity_id = node.userData("coophou.entity_id")
        self.apply(
            RenameNode(
                MODEL_VERSION,
                "operation-rename",
                self.ref(entity_id, node.path()),
                "remote_rename_after",
                "remote_rename_before",
            )
        )
        self.assertIsNotNone(self.root.node("remote_rename_after"))

    def test_apply_rename_preconditions_and_collision_reject_before_mutation(self):
        first = self.create_fixture_null("rename_first")
        second = self.create_fixture_null("rename_second")
        self.capture()
        first_ref = self.ref(first.userData("coophou.entity_id"), first.path())
        self.reject_apply(
            "APPLICATION_PREVALIDATION_FAILED",
            RenameNode(
                MODEL_VERSION,
                "operation-rename-collision",
                first_ref,
                "rename_second",
                "rename_first",
            ),
        )
        self.assertEqual(first.name(), "rename_first")
        self.reject_apply(
            "APPLICATION_PREVALIDATION_FAILED",
            RenameNode(
                MODEL_VERSION,
                "operation-rename-stale",
                first_ref,
                "rename_after",
                "wrong_expected_name",
            ),
        )
        self.assertEqual(first.name(), "rename_first")

    def test_apply_unsupported_operator_rejects_before_creation(self):
        operation = CreateNode(
            MODEL_VERSION,
            "operation-unsupported-type",
            CreateNodeSpec(
                MODEL_VERSION,
                self.ref("unsupported-id", f"{self.root.path()}/unsupported"),
                self.ref("root", self.root.path()),
                "box",
                "unsupported",
                (0.0, 0.0),
                (),
            ),
        )
        self.reject_apply("APPLICATION_PREVALIDATION_FAILED", operation)
        self.assertIsNone(self.root.node("unsupported"))

    def test_apply_move(self):
        node = self.create_fixture_null("remote_move")
        self.capture()
        entity_id = node.userData("coophou.entity_id")
        self.apply(
            MoveNode(
                MODEL_VERSION,
                "operation-move",
                self.ref(entity_id, node.path()),
                (7.0, -2.0),
                tuple(node.position()),
            )
        )
        self.assertEqual(tuple(node.position()), (7.0, -2.0))

    def test_apply_set_input_connect_and_disconnect(self):
        source = self.create_fixture_null("remote_wire_source")
        destination = self.create_fixture_null("remote_wire_destination")
        self.capture()
        source_ref = self.ref(source.userData("coophou.entity_id"), source.path())
        destination_ref = self.ref(destination.userData("coophou.entity_id"), destination.path())
        connection = ConnectionRef(MODEL_VERSION, source_ref, 0)
        self.apply(
            SetInput(
                MODEL_VERSION,
                "operation-connect",
                destination_ref,
                0,
                None,
                connection,
            )
        )
        self.assertEqual(destination.inputs()[0], source)
        self.apply(
            SetInput(
                MODEL_VERSION,
                "operation-disconnect",
                destination_ref,
                0,
                connection,
                None,
            )
        )
        self.assertEqual(destination.inputs(), ())

    def test_apply_input_stale_expected_and_deleted_source_reject(self):
        source = self.create_fixture_null("stale_wire_source")
        destination = self.create_fixture_null("stale_wire_destination")
        self.capture()
        source_ref = self.ref(source.userData("coophou.entity_id"), source.path())
        destination_ref = self.ref(
            destination.userData("coophou.entity_id"), destination.path()
        )
        connection = ConnectionRef(MODEL_VERSION, source_ref, 0)
        self.reject_apply(
            "APPLICATION_PREVALIDATION_FAILED",
            SetInput(
                MODEL_VERSION,
                "operation-stale-wire",
                destination_ref,
                0,
                connection,
                None,
            ),
        )
        self.assertEqual(destination.inputs(), ())
        source.destroy()
        self.capture()
        self.reject_apply(
            "APPLICATION_PREVALIDATION_FAILED",
            SetInput(
                MODEL_VERSION,
                "operation-deleted-wire",
                destination_ref,
                0,
                None,
                connection,
            ),
        )
        self.assertEqual(destination.inputs(), ())

    def test_apply_parameter_tuple(self):
        node = self.create_fixture_null("remote_parameter")
        self.capture()
        self.apply(
            SetParameterTuple(
                MODEL_VERSION,
                "operation-parameter",
                self.ref(node.userData("coophou.entity_id"), node.path()),
                "cacheinput",
                self.bool_value(True),
                self.bool_value(False),
            )
        )
        self.assertEqual(node.parmTuple("cacheinput").eval(), (1,))

    def test_apply_parameter_expected_value_rejects_before_mutation(self):
        node = self.create_fixture_null("stale_parameter")
        self.capture()
        self.reject_apply(
            "APPLICATION_PREVALIDATION_FAILED",
            SetParameterTuple(
                MODEL_VERSION,
                "operation-stale-parameter",
                self.ref(node.userData("coophou.entity_id"), node.path()),
                "cacheinput",
                self.bool_value(True),
                self.bool_value(True),
            ),
        )
        self.assertEqual(node.parm("cacheinput").eval(), 0)

    def test_expression_parameter_is_rejected_and_stops_capture(self):
        node = self.create_fixture_null("expression_parameter")
        self.capture()
        node.parm("cacheinput").setExpression(
            "$F > 1", language=hou.exprLanguage.Hscript
        )
        with self.assertRaisesRegex(NativeBridgeError, "CAPTURE_EXTRACTION_FAILED"):
            self.bridge.flush_settle()
        self.assertTrue(self.bridge.capture_state()["reconciliation_required"])

    def test_keyframed_parameter_is_rejected_and_stops_capture(self):
        node = self.create_fixture_null("keyframed_parameter")
        self.capture()
        key = hou.Keyframe()
        key.setFrame(1)
        key.setValue(1)
        node.parm("cacheinput").setKeyframe(key)
        with self.assertRaisesRegex(NativeBridgeError, "CAPTURE_EXTRACTION_FAILED"):
            self.bridge.flush_settle()
        self.assertTrue(self.bridge.capture_state()["reconciliation_required"])

    def test_parameter_raw_kinds_capture_and_apply(self):
        self.bridge.stop_capture()
        hou.hipFile.clear(suppress_save_prompt=True)
        self.root = hou.node("/obj")
        started = self.bridge.start_capture(
            root_path="/obj",
            root_entity_id="root",
            deterministic_id_prefix="raw-kinds",
            operator_types=["geo"],
            parameter_names=["t", "keeppos", "pathorient", "constraints_path", "xOrd"],
            parameter_kinds={
                "t": "float",
                "keeppos": "boolean",
                "pathorient": "integer",
                "constraints_path": "string",
                "xOrd": "menu_token",
            },
            max_nodes=64,
            capture_queue_limit=64,
            apply_queue_limit=8,
        )
        self.generation = started["scene_generation"]
        self.portable_scene = fake_scene_from_native_snapshot(
            self.bridge.extract_snapshot()
        )
        node = self.root.createNode("geo", "raw_kinds")
        self.capture()
        entity_id = node.userData("coophou.entity_id")
        node.parmTuple("t").set((1.5, 2.5, 3.5))
        node.parm("keeppos").set(1)
        node.parm("pathorient").set(2)
        node.parm("constraints_path").set("raw-string")
        node.parm("xOrd").set("trs")
        operations, _ = self.capture()
        parameters = {
            op.parameter_name: op
            for op in operations
            if isinstance(op, SetParameterTuple)
        }
        self.assertEqual(
            {name: op.value.value_kind for name, op in parameters.items()},
            {
                "t": RawValueKind.FLOAT,
                "keeppos": RawValueKind.BOOLEAN,
                "pathorient": RawValueKind.INTEGER,
                "constraints_path": RawValueKind.STRING,
                "xOrd": RawValueKind.MENU_TOKEN,
            },
        )
        target = self.ref(entity_id, node.path())
        replacements = {
            "t": ParameterTupleValue(MODEL_VERSION, RawValueKind.FLOAT, (9.0, 8.0, 7.0)),
            "keeppos": ParameterTupleValue(MODEL_VERSION, RawValueKind.BOOLEAN, (False,)),
            "pathorient": ParameterTupleValue(MODEL_VERSION, RawValueKind.INTEGER, (3,)),
            "constraints_path": ParameterTupleValue(MODEL_VERSION, RawValueKind.STRING, ("remote-string",)),
            "xOrd": ParameterTupleValue(MODEL_VERSION, RawValueKind.MENU_TOKEN, ("rts",)),
        }
        apply_operations = tuple(
            SetParameterTuple(
                MODEL_VERSION,
                f"operation-raw-{name}",
                target,
                name,
                replacements[name],
                parameters[name].value,
            )
            for name in sorted(replacements)
        )
        self.apply(*apply_operations)
        self.assertEqual(node.parmTuple("t").eval(), (9.0, 8.0, 7.0))
        self.assertEqual(node.parm("keeppos").eval(), 0)
        self.assertEqual(node.parm("pathorient").eval(), 3)
        self.assertEqual(node.parm("constraints_path").unexpandedString(), "remote-string")
        self.assertEqual(node.parm("xOrd").evalAsString(), "rts")

    # Lifecycle, bounds, and bridge ------------------------------------------

    def test_bridge_capabilities_and_duplicate_start_stop(self):
        capabilities = self.bridge.capabilities()
        self.assertEqual(capabilities["houdini_version"], "21.0.729")
        self.assertEqual(capabilities["hdk_api_version"], 21000693)
        self.assertEqual(len(capabilities["operation_types"]), 7)
        restarted = self.bridge.start_capture(root_path=self.root.path())
        self.assertTrue(restarted["already_started"])
        self.assertTrue(self.bridge.stop_capture()["was_started"])
        self.assertFalse(self.bridge.stop_capture()["was_started"])

    def test_configured_root_mapping_does_not_write_portable_id_metadata(self):
        self.assertIsNone(self.root.userData("coophou.entity_id"))
        snapshot = self.bridge.extract_snapshot()
        self.assertEqual(snapshot["root"]["entity_id"], "root")
        self.assertEqual(snapshot["root"]["native_path"], self.root.path())

    def test_prefix_similar_sibling_is_outside_configured_root(self):
        sibling = hou.node("/obj").createNode("geo", "phase3_root_extra")
        for child in sibling.children():
            child.destroy()
        sibling.createNode("null", "outside_edit")
        settled = self.bridge.flush_settle()
        self.assertFalse(settled["settled"])
        self.assertEqual(self.bridge.drain_capture(max_count=16)["records"], [])

    def test_bridge_rejects_unknown_fields_and_schema_versions(self):
        with self.assertRaisesRegex(NativeBridgeError, "SCHEMA_INVALID"):
            self.bridge._call(
                "drain_capture",
                {"bridge_schema_version": 1, "max_count": 1, "extra": True},
            )
        with self.assertRaisesRegex(NativeBridgeError, "BRIDGE_UNSUPPORTED_VERSION"):
            self.bridge._call(
                "drain_capture", {"bridge_schema_version": 999, "max_count": 1}
            )
        with self.assertRaisesRegex(TypeError, "must be one JSON object"):
            hou.coophou_native_drain_capture("not-json")

    def test_python_bridge_reload_does_not_duplicate_native_lifecycle(self):
        import coophou.houdini_adapter.bridge as bridge_module

        reloaded = importlib.reload(bridge_module).NativeBridge(hou)
        self.assertTrue(reloaded.start_capture(root_path=self.root.path())["already_started"])
        self.assertTrue(reloaded.stop_capture()["was_started"])
        self.assertFalse(reloaded.stop_capture()["was_started"])

    def test_capture_queue_overflow_is_explicit_and_stops_normal_settle(self):
        self.bridge.stop_capture()
        self.bridge.start_capture(
            root_path=self.root.path(),
            root_entity_id="root",
            deterministic_id_prefix="overflow",
            operator_types=["null"],
            parameter_names=[],
            parameter_kinds={},
            max_nodes=64,
            capture_queue_limit=1,
            apply_queue_limit=4,
        )
        self.create_fixture_null("overflow_a")
        self.bridge.flush_settle()
        self.create_fixture_null("overflow_b")
        self.bridge.flush_settle()
        state = self.bridge.capture_state()
        self.assertTrue(state["capture_overflow"])
        self.assertTrue(state["reconciliation_required"])

    def test_apply_queue_overflow_is_explicit_and_stops_normal_apply(self):
        self.bridge.stop_capture()
        started = self.bridge.start_capture(
            root_path=self.root.path(),
            root_entity_id="root",
            deterministic_id_prefix="apply-overflow",
            operator_types=["null"],
            parameter_names=[],
            parameter_kinds={},
            max_nodes=64,
            capture_queue_limit=8,
            apply_queue_limit=1,
        )
        self.generation = started["scene_generation"]
        first = self.transaction(
            CreateNode(
                MODEL_VERSION,
                "operation-overflow-a",
                self.null_spec("overflow-a", "overflow_a"),
            )
        )
        second = self.transaction(
            CreateNode(
                MODEL_VERSION,
                "operation-overflow-b",
                self.null_spec("overflow-b", "overflow_b"),
            )
        )
        self.bridge.enqueue_apply(first, self.generation, "overflow-a")
        with self.assertRaisesRegex(NativeBridgeError, "QUEUE_OVERFLOW"):
            self.bridge.enqueue_apply(second, self.generation, "overflow-b")
        state = self.bridge.capture_state()
        self.assertTrue(state["apply_overflow"])
        self.assertTrue(state["reconciliation_required"])
        with self.assertRaisesRegex(NativeBridgeError, "RECONCILIATION_REQUIRED"):
            self.bridge.drain_apply(max_transactions=1, max_operations=1)

    def test_locked_hda_identity_assignment_fails_closed(self):
        self.bridge.stop_capture()
        hou.hipFile.clear(suppress_save_prompt=True)
        with tempfile.TemporaryDirectory(prefix="coophou-phase3-hda-") as directory:
            library_path = os.path.join(directory, "locked_identity.hda")
            subnet = hou.node("/obj").createNode("subnet", "locked_identity")
            subnet.createNode("null", "inside")
            type_name = f"coophou::locked_identity_{next(self.ids)}::1.0"
            asset = subnet.createDigitalAsset(
                name=type_name,
                hda_file_name=library_path,
                description="CoopHou locked identity contract fixture",
            )
            asset.matchCurrentDefinition()
            self.assertTrue(asset.isLockedHDA())
            child_types = sorted(
                {child.type().name() for child in asset.allSubChildren()}
            )
            try:
                with self.assertRaisesRegex(
                    NativeBridgeError, "not writable for identity assignment"
                ):
                    self.bridge.start_capture(
                        root_path=asset.path(),
                        root_entity_id="root",
                        deterministic_id_prefix="locked",
                        operator_types=child_types,
                        parameter_names=[],
                        parameter_kinds={},
                        max_nodes=64,
                        capture_queue_limit=8,
                        apply_queue_limit=4,
                    )
            finally:
                self.bridge.stop_capture()
                asset.destroy()
                hou.hda.uninstallFile(library_path)

    def test_scene_clear_advances_generation_and_rejects_stale_apply(self):
        old_generation = self.generation
        operation = CreateNode(
            MODEL_VERSION,
            "operation-stale",
            self.null_spec("stale-id", "stale_node"),
        )
        tx = self.transaction(operation)
        hou.hipFile.clear(suppress_save_prompt=True)
        state = self.bridge.capture_state()
        self.assertGreater(state["scene_generation"], old_generation)
        with self.assertRaisesRegex(Exception, "STALE_SCENE_GENERATION"):
            self.bridge.enqueue_apply(tx, old_generation, "stale-generation")

    def test_merge_emits_explicit_lifecycle_record(self):
        self.bridge.stop_capture()
        with tempfile.TemporaryDirectory(prefix="coophou-phase3-merge-") as directory:
            path = os.path.join(directory, "merge_source.hip")
            hou.hipFile.clear(suppress_save_prompt=True)
            hou.node("/obj").createNode("null", "merged_node")
            hou.hipFile.save(path)
            hou.hipFile.clear(suppress_save_prompt=True)
            started = self.bridge.start_capture(
                root_path="/obj",
                root_entity_id="root",
                deterministic_id_prefix="merge",
                operator_types=["null"],
                parameter_names=[],
                parameter_kinds={},
                max_nodes=64,
                capture_queue_limit=16,
                apply_queue_limit=4,
            )
            self.generation = started["scene_generation"]
            hou.hipFile.merge(path)
            records = self.bridge.drain_capture(max_count=16)["records"]
            self.assertTrue(
                any(
                    record.get("record_type") == "scene.merge_requires_settle"
                    for record in records
                ),
                records,
            )

    def test_save_load_preserves_identity_and_resets_generation(self):
        node = self.create_fixture_null("persisted_identity")
        self.capture()
        entity_id = node.userData("coophou.entity_id")
        old_generation = self.generation
        with tempfile.TemporaryDirectory(prefix="coophou-phase3-") as directory:
            path = os.path.join(directory, "identity.hip")
            hou.hipFile.save(path)
            self.assertEqual(
                self.bridge.capture_state()["scene_generation"], old_generation
            )
            hou.hipFile.load(path, suppress_save_prompt=True)
        state = self.bridge.capture_state()
        self.assertEqual(state["scene_generation"], old_generation + 1)
        loaded = hou.node("/obj/phase3_root/persisted_identity")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.userData("coophou.entity_id"), entity_id)
        records = self.bridge.drain_capture(max_count=64)["records"]
        self.assertTrue(any(record.get("record_type") == "scene.replaced" for record in records))


if __name__ == "__main__":
    unittest.main(verbosity=2)
