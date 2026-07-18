import unittest

from coophou.core.errors import ErrorCode
from coophou.core.models import (
    MODEL_VERSION,
    CreateSubtree,
    NamedParameterValue,
    RawValueKind,
    RenameNode,
    SubtreeConnection,
)
from coophou.core.errors import DomainError
from coophou.core.scene import FakeScene

from core_fixtures import (
    connection,
    create_op,
    delete_tx,
    input_tx,
    move_tx,
    parameter_tx,
    ref,
    rename_tx,
    spec,
    transaction,
    value,
)


V = MODEL_VERSION


class FakeSceneTests(unittest.TestCase):
    def setUp(self):
        self.scene = FakeScene.initial()

    def apply_ok(self, tx):
        result = self.scene.apply_transaction(tx)
        self.assertTrue(result.success, result.error)
        return result

    def test_create_node_and_stable_identity_survive_rename(self):
        self.apply_ok(transaction("tx-create", create_op("node-a", "node_a")))
        diagnostic = self.scene.entity_ref("node-a")
        self.assertEqual(diagnostic.last_known_path, "/node_a")
        self.apply_ok(rename_tx("tx-rename", "node-a", "node_a", "renamed"))
        self.assertEqual(self.scene.path("node-a"), "/renamed")
        self.assertEqual(self.scene.require_live("node-a").entity_id, diagnostic.entity_id)

    def test_create_subtree_is_parent_before_child_and_wires_connections(self):
        copied = CreateSubtree(
            V,
            "op-copy",
            (
                spec("copy-parent", "copy_parent"),
                spec(
                    "copy-child",
                    "copy_child",
                    "copy-parent",
                    parameters=(NamedParameterValue(V, "scale", value(2.0)),),
                ),
            ),
            (SubtreeConnection(V, ref("copy-child"), 0, connection("copy-parent")),),
        )
        self.apply_ok(transaction("tx-copy", copied))
        self.assertEqual(self.scene.path("copy-child"), "/copy_parent/copy_child")
        self.assertEqual(
            self.scene.require_live("copy-child").inputs[0].source.entity_id,
            "copy-parent",
        )
        self.assertEqual(
            self.scene.require_live("copy-child").parameters["scale"], value(2.0)
        )

    def test_create_subtree_wrong_order_fails_atomically(self):
        copied = CreateSubtree(
            V,
            "op-copy",
            (
                spec("copy-child", "copy_child", "copy-parent"),
                spec("copy-parent", "copy_parent"),
            ),
        )
        before = self.scene.semantic_json()
        result = self.scene.apply_transaction(transaction("tx-copy", copied))
        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ErrorCode.PRECONDITION_FAILED)
        self.assertEqual(self.scene.semantic_json(), before)

    def test_copied_subtree_duplicate_ids_are_rejected_by_schema(self):
        with self.assertRaises(DomainError) as caught:
            CreateSubtree(
                V,
                "op-copy",
                (spec("copy-a", "copy_a"), spec("copy-a", "copy_b")),
            )
        self.assertEqual(caught.exception.detail.code, ErrorCode.OPERATION_INVALID_PAYLOAD)

    def test_copied_subtree_missing_connection_source_rejects_whole_transaction(self):
        copied = CreateSubtree(
            V,
            "op-copy",
            (spec("copy-a", "copy_a"),),
            (SubtreeConnection(V, ref("copy-a"), 0, connection("missing")),),
        )
        before = self.scene.semantic_json()
        result = self.scene.apply_transaction(transaction("tx-copy", copied))
        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ErrorCode.ENTITY_NOT_FOUND)
        self.assertEqual(self.scene.semantic_json(), before)

    def test_delete_subtree_tombstones_ids_and_path_reuse_cannot_retarget(self):
        self.apply_ok(
            transaction(
                "tx-create",
                create_op("parent", "asset"),
                create_op("child", "inside", "parent"),
            )
        )
        self.apply_ok(delete_tx("tx-delete", "parent", ("parent", "child")))
        self.assertEqual(self.scene.tombstones["parent"].last_known_path, "/asset")
        self.apply_ok(transaction("tx-replacement", create_op("replacement", "asset")))
        rejected = self.scene.apply_transaction(
            move_tx("tx-stale", "parent", (0.0, 0.0), (4.0, 4.0))
        )
        self.assertFalse(rejected.success)
        self.assertEqual(rejected.error.code, ErrorCode.ENTITY_DELETED)
        self.assertEqual(self.scene.require_live("replacement").position, (0.0, 0.0))

    def test_delete_requires_exact_subtree_set(self):
        self.apply_ok(
            transaction(
                "tx-create",
                create_op("parent", "parent"),
                create_op("child", "child", "parent"),
            )
        )
        result = self.scene.apply_transaction(delete_tx("tx-delete", "parent", ("parent",)))
        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ErrorCode.PRECONDITION_FAILED)
        self.assertIn("parent", self.scene.entities)

    def test_rename_collision_and_precondition_fail_without_mutation(self):
        self.apply_ok(
            transaction(
                "tx-create",
                create_op("node-a", "node_a"),
                create_op("node-b", "node_b"),
            )
        )
        before = self.scene.semantic_json()
        collision = self.scene.apply_transaction(
            rename_tx("tx-collision", "node-a", "node_a", "node_b")
        )
        self.assertFalse(collision.success)
        self.assertEqual(collision.error.code, ErrorCode.NAME_CONFLICT)
        stale = self.scene.apply_transaction(
            rename_tx("tx-stale", "node-a", "old_name", "new_name")
        )
        self.assertFalse(stale.success)
        self.assertEqual(stale.error.code, ErrorCode.PRECONDITION_FAILED)
        self.assertEqual(self.scene.semantic_json(), before)

    def test_move_has_exact_expected_position(self):
        self.apply_ok(transaction("tx-create", create_op("node-a", "node_a")))
        self.apply_ok(move_tx("tx-move", "node-a", (0.0, 0.0), (10.0, -3.0)))
        self.assertEqual(self.scene.require_live("node-a").position, (10.0, -3.0))
        result = self.scene.apply_transaction(
            move_tx("tx-stale", "node-a", (0.0, 0.0), (1.0, 1.0))
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ErrorCode.PRECONDITION_FAILED)

    def test_connect_disconnect_and_expected_previous(self):
        self.apply_ok(
            transaction(
                "tx-create",
                create_op("source-a", "source_a"),
                create_op("source-b", "source_b"),
                create_op("destination", "destination"),
            )
        )
        source_a = connection("source-a")
        source_b = connection("source-b", 1)
        self.apply_ok(input_tx("tx-connect", "destination", 0, source_a))
        self.apply_ok(input_tx("tx-rewire", "destination", 0, source_b, source_a))
        stale = self.scene.apply_transaction(
            input_tx("tx-stale", "destination", 0, None, source_a)
        )
        self.assertFalse(stale.success)
        self.assertEqual(stale.error.code, ErrorCode.PRECONDITION_FAILED)
        self.apply_ok(input_tx("tx-disconnect", "destination", 0, None, source_b))
        self.assertNotIn(0, self.scene.require_live("destination").inputs)

    def test_connect_from_deleted_source_is_rejected(self):
        self.apply_ok(
            transaction(
                "tx-create",
                create_op("source", "source"),
                create_op("destination", "destination"),
            )
        )
        self.apply_ok(delete_tx("tx-delete", "source", ("source",)))
        result = self.scene.apply_transaction(
            input_tx("tx-connect", "destination", 0, connection("source"))
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ErrorCode.ENTITY_DELETED)

    def test_connection_diagnostic_path_is_not_identity(self):
        self.apply_ok(
            transaction(
                "tx-create",
                create_op("source", "source"),
                create_op("destination", "destination"),
            )
        )
        with_wrong_path = connection("source", path="/stale/path")
        self.apply_ok(input_tx("tx-connect", "destination", 0, with_wrong_path))
        stored = self.scene.require_live("destination").inputs[0]
        self.assertEqual(stored.source.entity_id, "source")

    def test_parameter_tuple_replaces_complete_value_and_checks_expected(self):
        self.apply_ok(transaction("tx-create", create_op("node-a", "node_a")))
        vector = value(1.0, 2.0, 3.0)
        changed = value(4.0, 5.0, 6.0)
        self.apply_ok(parameter_tx("tx-first", "node-a", "t", vector))
        self.apply_ok(parameter_tx("tx-second", "node-a", "t", changed, vector))
        self.assertEqual(self.scene.require_live("node-a").parameters["t"], changed)
        stale = self.scene.apply_transaction(
            parameter_tx("tx-stale", "node-a", "t", value(9.0, 9.0, 9.0), vector)
        )
        self.assertFalse(stale.success)
        self.assertEqual(stale.error.code, ErrorCode.PRECONDITION_FAILED)

    def test_parameter_component_fragment_cannot_match_complete_tuple_precondition(self):
        self.apply_ok(transaction("tx-create", create_op("node-a", "node_a")))
        complete = value(1.0, 2.0, 3.0)
        self.apply_ok(parameter_tx("tx-complete", "node-a", "t", complete))
        with self.assertRaises(DomainError):
            parameter_tx(
                "tx-fragment",
                "node-a",
                "t",
                value(9.0),
                complete,
            )

    def test_missing_targets_fail_by_stable_identity_for_each_mutating_family(self):
        missing_transactions = (
            transaction("create-missing-parent", create_op("new", "new", "missing")),
            rename_tx("rename-missing", "missing", "old", "new"),
            move_tx("move-missing", "missing", (0.0, 0.0), (1.0, 1.0)),
            parameter_tx("parameter-missing", "missing", "scale", value(1.0)),
            input_tx("input-missing", "missing", 0, None),
            delete_tx("delete-missing", "missing", ("missing",)),
        )
        for tx in missing_transactions:
            with self.subTest(transaction=tx.transaction_id):
                result = self.scene.apply_transaction(tx)
                self.assertFalse(result.success)
                self.assertEqual(result.error.code, ErrorCode.ENTITY_NOT_FOUND)

    def test_parameter_raw_shapes_are_preserved(self):
        self.apply_ok(transaction("tx-create", create_op("node-a", "node_a")))
        values = {
            "count": value(3, kind=RawValueKind.INTEGER),
            "enabled": value(True, kind=RawValueKind.BOOLEAN),
            "label": value("hello", kind=RawValueKind.STRING),
            "mode": value("linear", kind=RawValueKind.MENU_TOKEN),
        }
        for index, (name, tuple_value) in enumerate(values.items()):
            self.apply_ok(parameter_tx(f"tx-{index}", "node-a", name, tuple_value))
        self.assertEqual(self.scene.require_live("node-a").parameters, values)

    def test_transaction_is_atomic_under_injected_mid_apply_failure(self):
        tx = transaction(
            "tx-two",
            create_op("node-a", "node_a"),
            create_op("node-b", "node_b"),
        )
        before = self.scene.semantic_json()
        failed = self.scene.apply_transaction(tx, fail_after_operation=1)
        self.assertFalse(failed.success)
        self.assertEqual(failed.error.code, ErrorCode.APPLICATION_FAILED)
        self.assertEqual(self.scene.semantic_json(), before)

    def test_transaction_replay_is_idempotent_and_conflicting_reuse_fails(self):
        tx = transaction("tx-create", create_op("node-a", "node_a"))
        first = self.scene.apply_transaction(tx)
        replay = self.scene.apply_transaction(tx)
        self.assertTrue(first.changed)
        self.assertTrue(replay.success)
        self.assertFalse(replay.changed)
        conflicting = transaction("tx-create", create_op("node-b", "node_b"))
        result = self.scene.apply_transaction(conflicting)
        self.assertFalse(result.success)
        self.assertEqual(result.error.code, ErrorCode.DUPLICATE_CONFLICT)

    def test_each_operation_family_has_transaction_replay_no_op(self):
        cases = []

        create_scene = FakeScene.initial()
        cases.append((create_scene, transaction("replay-create", create_op("node-a", "node_a"))))

        subtree_scene = FakeScene.initial()
        subtree = CreateSubtree(
            V,
            "op-subtree",
            (spec("copy-a", "copy_a"), spec("copy-b", "copy_b", "copy-a")),
            (SubtreeConnection(V, ref("copy-b"), 0, connection("copy-a")),),
        )
        cases.append((subtree_scene, transaction("replay-subtree", subtree)))

        for label, operation_transaction in (
            ("delete", delete_tx("replay-delete", "node-a", ("node-a",))),
            ("rename", rename_tx("replay-rename", "node-a", "node_a", "renamed")),
            ("move", move_tx("replay-move", "node-a", (0.0, 0.0), (1.0, 2.0))),
            ("parameter", parameter_tx("replay-parameter", "node-a", "scale", value(2.0))),
        ):
            scene = FakeScene.initial()
            seed = scene.apply_transaction(transaction(f"seed-{label}", create_op("node-a", "node_a")))
            self.assertTrue(seed.success)
            cases.append((scene, operation_transaction))

        input_scene = FakeScene.initial()
        seed = input_scene.apply_transaction(
            transaction(
                "seed-input",
                create_op("source", "source"),
                create_op("destination", "destination"),
            )
        )
        self.assertTrue(seed.success)
        cases.append(
            (
                input_scene,
                input_tx("replay-input", "destination", 0, connection("source")),
            )
        )

        for scene, tx in cases:
            with self.subTest(transaction=tx.transaction_id):
                first = scene.apply_transaction(tx)
                replay = scene.apply_transaction(tx)
                self.assertTrue(first.success, first.error)
                self.assertTrue(first.changed)
                self.assertTrue(replay.success, replay.error)
                self.assertFalse(replay.changed)

    def test_tombstoned_identity_rejects_every_later_targeting_family(self):
        self.apply_ok(
            transaction(
                "seed",
                create_op("deleted", "old_path"),
                create_op("source", "source"),
            )
        )
        self.apply_ok(delete_tx("delete", "deleted", ("deleted",)))
        subtree = CreateSubtree(V, "op-subtree", (spec("deleted", "copy"),))
        later = (
            transaction("create-old-id", create_op("deleted", "replacement")),
            transaction("subtree-old-id", subtree),
            rename_tx("rename-deleted", "deleted", "old_path", "renamed"),
            move_tx("move-deleted", "deleted", (0.0, 0.0), (1.0, 1.0)),
            parameter_tx("parameter-deleted", "deleted", "scale", value(1.0)),
            input_tx("input-deleted", "deleted", 0, connection("source")),
        )
        for tx in later:
            with self.subTest(transaction=tx.transaction_id):
                result = self.scene.apply_transaction(tx)
                self.assertFalse(result.success)
                self.assertEqual(result.error.code, ErrorCode.ENTITY_DELETED)

    def test_wrong_diagnostic_path_never_overrides_entity_identity(self):
        self.apply_ok(transaction("create", create_op("node-a", "node_a")))
        tx = transaction(
            "rename",
            RenameNode(
                V,
                "op-rename-wrong-path",
                ref("node-a", "/not/the/node"),
                "renamed",
                "node_a",
            ),
        )
        self.apply_ok(tx)
        self.assertEqual(self.scene.path("node-a"), "/renamed")

    def test_applied_transaction_history_is_bounded(self):
        scene = FakeScene(applied_history_limit=2)
        for index in range(3):
            result = scene.apply_transaction(
                transaction(f"tx-{index}", create_op(f"node-{index}", f"node_{index}"))
            )
            self.assertTrue(result.success)
        self.assertEqual(len(scene._applied_transactions), 2)


if __name__ == "__main__":
    unittest.main()
