import json
import unittest

from coophou.core.errors import DomainError, ErrorCode, ErrorDetail
from coophou.core.models import (
    MODEL_VERSION,
    AcceptedTransaction,
    ApplyResult,
    CapabilitySet,
    ClientSequenceState,
    ConnectionRef,
    CreateNode,
    CreateSubtree,
    DeleteSubtree,
    EntityRef,
    MoveNode,
    NamedParameterValue,
    OperationType,
    ParameterTupleValue,
    PendingLocalTransaction,
    RawValueKind,
    RejectedTransaction,
    RenameNode,
    ResumeRequest,
    ResumeResult,
    ResumeStatus,
    SetInput,
    SetParameterTuple,
    SubtreeConnection,
    Transaction,
    deterministic_json,
    operation_from_dict,
)

from core_fixtures import connection, create_op, ref, spec, transaction, value


V = MODEL_VERSION


class CoreModelTests(unittest.TestCase):
    def setUp(self):
        float_value = value(1.25, 2.5)
        self.operations = (
            create_op("node-a", "node_a"),
            CreateSubtree(
                V,
                "op-copy",
                (spec("copy-a", "copy_a"), spec("copy-b", "copy_b", "copy-a")),
                (SubtreeConnection(V, ref("copy-b"), 0, connection("copy-a")),),
            ),
            DeleteSubtree(V, "op-delete", ref("node-a"), ("node-a",), "root"),
            RenameNode(V, "op-rename", ref("node-a"), "renamed", "node_a"),
            MoveNode(V, "op-move", ref("node-a"), (3.0, 4.0), (0.0, 0.0)),
            SetInput(V, "op-input", ref("node-a"), 0, None, connection("copy-a")),
            SetParameterTuple(V, "op-parameter", ref("node-a"), "t", float_value, float_value),
        )

    def test_all_operations_round_trip(self):
        for operation in self.operations:
            with self.subTest(operation=operation.operation_type):
                self.assertEqual(operation, operation_from_dict(operation.to_dict()))

    def test_transaction_round_trip_and_deterministic_json(self):
        tx = transaction("tx-all", *self.operations)
        encoded = deterministic_json(tx)
        self.assertEqual(tx, Transaction.from_dict(json.loads(encoded)))
        self.assertEqual(encoded, tx.semantic_json())
        self.assertEqual(encoded, deterministic_json(Transaction.from_dict(tx.to_dict())))

    def test_support_records_round_trip(self):
        tx = transaction("tx-one", self.operations[0])
        error = ErrorDetail(V, ErrorCode.PRECONDITION_FAILED, "no", (("field", "name"),))
        records = (
            (EntityRef, ref("node-a", "/node_a")),
            (ConnectionRef, connection("node-a", 2)),
            (ParameterTupleValue, value(1, 2, kind=RawValueKind.INTEGER)),
            (NamedParameterValue, NamedParameterValue(V, "scale", value(1.0))),
            (CapabilitySet, CapabilitySet.v1()),
            (AcceptedTransaction, AcceptedTransaction(V, 1, "authority", tx)),
            (RejectedTransaction, RejectedTransaction(V, tx.transaction_id, "session", error)),
            (PendingLocalTransaction, PendingLocalTransaction(V, tx, 1, 2, 3)),
            (ApplyResult, ApplyResult(V, False, False, error)),
            (ClientSequenceState, ClientSequenceState(V, 3, 2, 2)),
            (ResumeRequest, ResumeRequest(V, "session", "alice", 3, 2, ("tx-one",))),
            (
                ResumeResult,
                ResumeResult(
                    V,
                    ResumeStatus.OK,
                    "session",
                    0,
                    0,
                    1,
                    (AcceptedTransaction(V, 1, "authority", tx),),
                ),
            ),
        )
        for model_type, record in records:
            with self.subTest(model=model_type.__name__):
                self.assertEqual(record, model_type.from_dict(record.to_dict()))
        self.assertEqual(error, ErrorDetail.from_dict(error.to_dict()))

    def test_unknown_operation_type_fails_closed(self):
        data = self.operations[0].to_dict()
        data["operation_type"] = "python.execute"
        with self.assertRaises(DomainError) as caught:
            operation_from_dict(data)
        self.assertEqual(caught.exception.detail.code, ErrorCode.OPERATION_UNKNOWN_TYPE)

    def test_extra_or_missing_fields_are_rejected(self):
        data = self.operations[0].to_dict()
        data["script"] = "print('unsafe')"
        with self.assertRaises(DomainError) as caught:
            operation_from_dict(data)
        self.assertEqual(caught.exception.detail.code, ErrorCode.SCHEMA_INVALID)
        del data["script"]
        del data["spec"]
        with self.assertRaises(DomainError):
            operation_from_dict(data)

    def test_no_executable_payload_shape(self):
        with self.assertRaises(DomainError):
            ParameterTupleValue(V, RawValueKind.STRING, (lambda: None,))
        with self.assertRaises(DomainError):
            Transaction(V, "tx", "alice", "session", (object(),))

    def test_versions_and_identifiers_fail_closed(self):
        with self.assertRaises(DomainError) as caught:
            EntityRef(2, "node-a")
        self.assertEqual(caught.exception.detail.code, ErrorCode.SCHEMA_UNSUPPORTED_VERSION)
        with self.assertRaises(DomainError):
            EntityRef(V, "../../escape")
        with self.assertRaises(DomainError):
            EntityRef(V, "node-a", "node", "relative/path")

    def test_raw_value_kinds_and_shapes(self):
        valid = (
            value(1, -2, kind=RawValueKind.INTEGER),
            value(1.0, 2.0, kind=RawValueKind.FLOAT),
            value(True, False, kind=RawValueKind.BOOLEAN),
            value("hello", kind=RawValueKind.STRING),
            value("token", kind=RawValueKind.MENU_TOKEN),
        )
        for item in valid:
            self.assertEqual(item, ParameterTupleValue.from_dict(item.to_dict()))
        invalid = (
            (RawValueKind.INTEGER, (True,)),
            (RawValueKind.FLOAT, (1,)),
            (RawValueKind.FLOAT, (float("nan"),)),
            (RawValueKind.BOOLEAN, (1,)),
            (RawValueKind.MENU_TOKEN, ("",)),
        )
        for kind, values in invalid:
            with self.subTest(kind=kind):
                with self.assertRaises(DomainError):
                    ParameterTupleValue(V, kind, values)

    def test_transaction_requires_unique_operations_and_complete_capabilities(self):
        operation = create_op("node-a", "node_a")
        with self.assertRaises(DomainError):
            Transaction(V, "tx", "alice", "session", (operation, operation))
        with self.assertRaises(DomainError):
            Transaction(
                V,
                "tx",
                "alice",
                "session",
                (operation,),
                None,
                (OperationType.RENAME_NODE,),
            )

    def test_capability_compatibility_is_directional(self):
        all_capabilities = CapabilitySet.v1()
        create_only = CapabilitySet(V, V, V, V, (OperationType.CREATE_NODE,))
        self.assertTrue(create_only.compatible_with(all_capabilities))
        self.assertFalse(all_capabilities.compatible_with(create_only))
        self.assertTrue(create_only.supports(transaction("tx", create_op("n", "n"))))
        extra_requirement = Transaction(
            V,
            "tx-extra",
            "alice",
            "session",
            (create_op("extra", "extra"),),
            None,
            (OperationType.CREATE_NODE, OperationType.RENAME_NODE),
        )
        self.assertFalse(create_only.supports(extra_requirement))


if __name__ == "__main__":
    unittest.main()
