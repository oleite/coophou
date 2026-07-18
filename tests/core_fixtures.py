from coophou.core.models import (
    MODEL_VERSION,
    ConnectionRef,
    CreateNode,
    CreateNodeSpec,
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
    Transaction,
)


V = MODEL_VERSION


def ref(entity_id, path=None):
    return EntityRef(V, entity_id, "node", path)


def connection(entity_id, output_index=0, path=None):
    return ConnectionRef(V, ref(entity_id, path), output_index)


def value(*values, kind=RawValueKind.FLOAT):
    return ParameterTupleValue(V, kind, tuple(values))


def spec(entity_id, name, parent_id="root", position=(0.0, 0.0), parameters=()):
    return CreateNodeSpec(
        V,
        ref(entity_id),
        ref(parent_id),
        "test::1.0",
        name,
        position,
        tuple(parameters),
    )


def create_op(entity_id, name, parent_id="root", operation_id=None, position=(0.0, 0.0)):
    return CreateNode(
        V,
        operation_id or f"op-create-{entity_id}",
        spec(entity_id, name, parent_id, position),
    )


def transaction(transaction_id, *operations, author="alice", session="session"):
    required = tuple(sorted({op.operation_type for op in operations}, key=lambda item: item.value))
    return Transaction(V, transaction_id, author, session, tuple(operations), None, required)


def rename_tx(transaction_id, entity_id, old_name, new_name, author="alice"):
    return transaction(
        transaction_id,
        RenameNode(V, f"op-{transaction_id}", ref(entity_id), new_name, old_name),
        author=author,
    )


def move_tx(transaction_id, entity_id, old, new, author="alice"):
    return transaction(
        transaction_id,
        MoveNode(V, f"op-{transaction_id}", ref(entity_id), new, old),
        author=author,
    )


def delete_tx(transaction_id, entity_id, deleted_ids, parent_id="root", author="alice"):
    return transaction(
        transaction_id,
        DeleteSubtree(
            V,
            f"op-{transaction_id}",
            ref(entity_id),
            tuple(deleted_ids),
            parent_id,
        ),
        author=author,
    )


def parameter_tx(transaction_id, entity_id, name, new_value, expected=None, author="alice"):
    return transaction(
        transaction_id,
        SetParameterTuple(
            V,
            f"op-{transaction_id}",
            ref(entity_id),
            name,
            new_value,
            expected,
        ),
        author=author,
    )


def input_tx(transaction_id, destination_id, index, new_source, expected=None, author="alice"):
    return transaction(
        transaction_id,
        SetInput(
            V,
            f"op-{transaction_id}",
            ref(destination_id),
            index,
            expected,
            new_source,
        ),
        author=author,
    )


def initial_create_tx(transaction_id="tx-create", author="alice"):
    return transaction(transaction_id, create_op("node-a", "node_a"), author=author)
