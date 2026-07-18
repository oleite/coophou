"""Frozen, versioned Phase-2 domain records and deterministic JSON."""

from dataclasses import dataclass
from enum import Enum
import json
import math
import re
from typing import Union

from .errors import ErrorCode, ErrorDetail, fail


MODEL_VERSION = 1
MAX_ID_LENGTH = 128
MAX_OPERATIONS = 256
MAX_SUBTREE_NODES = 1024
MAX_PARAMETER_ARITY = 64
MAX_INPUT_INDEX = 255
MAX_POSITION_ABS = 1.0e9

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
_TYPE_PATTERN = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.:-]{0,127}$")


def _version(value, model):
    if type(value) is not int or value != MODEL_VERSION:
        fail(
            ErrorCode.SCHEMA_UNSUPPORTED_VERSION,
            f"unsupported {model} version",
            version=value,
        )


def _identifier(value, field):
    if not isinstance(value, str) or not _ID_PATTERN.fullmatch(value):
        fail(ErrorCode.SCHEMA_INVALID, f"invalid {field}", field=field)


def validate_identifier(value, field="identifier"):
    """Validate an opaque ID used by runtime owners as well as records."""
    _identifier(value, field)
    return value


def _name(value, field="name"):
    if not isinstance(value, str) or not _NAME_PATTERN.fullmatch(value):
        fail(ErrorCode.OPERATION_INVALID_PAYLOAD, f"invalid {field}", field=field)


def _operator_type(value):
    if not isinstance(value, str) or not _TYPE_PATTERN.fullmatch(value):
        fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "invalid operator type")


def _diagnostic_path(value):
    if value is not None and (
        not isinstance(value, str) or not value.startswith("/") or len(value) > 1024
    ):
        fail(ErrorCode.SCHEMA_INVALID, "invalid diagnostic path")


def _position(value):
    if not isinstance(value, tuple) or len(value) != 2:
        fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "position must be a two-value tuple")
    for component in value:
        if type(component) not in (int, float):
            fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "position components must be numeric")
        if not math.isfinite(component) or abs(component) > MAX_POSITION_ABS:
            fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "position component is not finite/in range")


def _keys(data, required, optional=()):
    if not isinstance(data, dict):
        fail(ErrorCode.SCHEMA_INVALID, "serialized model must be an object")
    allowed = set(required) | set(optional)
    if set(data) != allowed:
        fail(
            ErrorCode.SCHEMA_INVALID,
            "serialized model fields do not match schema",
            expected=sorted(allowed),
            actual=sorted(data),
        )


class OperationType(str, Enum):
    CREATE_NODE = "node.create"
    CREATE_SUBTREE = "subtree.create"
    DELETE_SUBTREE = "subtree.delete"
    RENAME_NODE = "node.rename"
    MOVE_NODE = "node.move"
    SET_INPUT = "node.input.set"
    SET_PARAMETER_TUPLE = "node.parameter_tuple.set"


class RawValueKind(str, Enum):
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    STRING = "string"
    MENU_TOKEN = "menu_token"


class ResumeStatus(str, Enum):
    OK = "OK"
    HISTORY_UNAVAILABLE = "HISTORY_UNAVAILABLE"
    HISTORY_GAP = "HISTORY_GAP"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    INCOMPATIBLE = "INCOMPATIBLE"


def _enum_value(enum_type, value, field):
    try:
        return enum_type(value)
    except (TypeError, ValueError):
        fail(ErrorCode.SCHEMA_INVALID, f"invalid {field}", field=field)


@dataclass(frozen=True)
class EntityRef:
    version: int
    entity_id: str
    entity_kind: str = "node"
    last_known_path: str | None = None

    def __post_init__(self):
        _version(self.version, "entity reference")
        _identifier(self.entity_id, "entity_id")
        if self.entity_kind != "node":
            fail(ErrorCode.SCHEMA_INVALID, "only node entity references are supported")
        _diagnostic_path(self.last_known_path)

    def to_dict(self):
        return {
            "version": self.version,
            "entity_id": self.entity_id,
            "entity_kind": self.entity_kind,
            "last_known_path": self.last_known_path,
        }

    @classmethod
    def from_dict(cls, data):
        _keys(data, ("version", "entity_id", "entity_kind", "last_known_path"))
        return cls(**data)


@dataclass(frozen=True)
class ConnectionRef:
    version: int
    source: EntityRef
    output_index: int

    def __post_init__(self):
        _version(self.version, "connection reference")
        if not isinstance(self.source, EntityRef):
            fail(ErrorCode.SCHEMA_INVALID, "connection source must be EntityRef")
        if type(self.output_index) is not int or not 0 <= self.output_index <= MAX_INPUT_INDEX:
            fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "invalid output index")

    def to_dict(self):
        return {
            "version": self.version,
            "source": self.source.to_dict(),
            "output_index": self.output_index,
        }

    @classmethod
    def from_dict(cls, data):
        _keys(data, ("version", "source", "output_index"))
        return cls(data["version"], EntityRef.from_dict(data["source"]), data["output_index"])


@dataclass(frozen=True)
class ParameterTupleValue:
    version: int
    value_kind: RawValueKind
    values: tuple[object, ...]

    def __post_init__(self):
        _version(self.version, "parameter tuple value")
        if not isinstance(self.value_kind, RawValueKind):
            fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "invalid raw value kind")
        if not isinstance(self.values, tuple) or not 1 <= len(self.values) <= MAX_PARAMETER_ARITY:
            fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "parameter tuple arity is invalid")
        for value in self.values:
            if self.value_kind is RawValueKind.INTEGER and type(value) is not int:
                fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "integer tuple contains non-integer")
            if self.value_kind is RawValueKind.FLOAT:
                if type(value) is not float or not math.isfinite(value):
                    fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "float tuple contains a non-float or non-finite value")
            if self.value_kind is RawValueKind.BOOLEAN and type(value) is not bool:
                fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "boolean tuple contains non-boolean")
            if self.value_kind in (RawValueKind.STRING, RawValueKind.MENU_TOKEN):
                if not isinstance(value, str) or len(value) > 4096:
                    fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "string tuple contains invalid value")
                if self.value_kind is RawValueKind.MENU_TOKEN and not value:
                    fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "menu token cannot be empty")

    def to_dict(self):
        return {
            "version": self.version,
            "value_kind": self.value_kind.value,
            "values": list(self.values),
        }

    @classmethod
    def from_dict(cls, data):
        _keys(data, ("version", "value_kind", "values"))
        if not isinstance(data["values"], list):
            fail(ErrorCode.SCHEMA_INVALID, "parameter values must be an array")
        return cls(
            data["version"],
            _enum_value(RawValueKind, data["value_kind"], "value_kind"),
            tuple(data["values"]),
        )


@dataclass(frozen=True)
class NamedParameterValue:
    version: int
    name: str
    value: ParameterTupleValue

    def __post_init__(self):
        _version(self.version, "named parameter")
        _name(self.name, "parameter name")
        if not isinstance(self.value, ParameterTupleValue):
            fail(ErrorCode.SCHEMA_INVALID, "parameter value must be ParameterTupleValue")

    def to_dict(self):
        return {"version": self.version, "name": self.name, "value": self.value.to_dict()}

    @classmethod
    def from_dict(cls, data):
        _keys(data, ("version", "name", "value"))
        return cls(data["version"], data["name"], ParameterTupleValue.from_dict(data["value"]))


@dataclass(frozen=True)
class CreateNodeSpec:
    version: int
    entity: EntityRef
    parent: EntityRef
    operator_type: str
    name: str
    position: tuple[float, float]
    initial_parameters: tuple[NamedParameterValue, ...] = ()

    def __post_init__(self):
        _version(self.version, "create-node spec")
        if not isinstance(self.entity, EntityRef) or not isinstance(self.parent, EntityRef):
            fail(ErrorCode.SCHEMA_INVALID, "node spec entity and parent must be references")
        _operator_type(self.operator_type)
        _name(self.name)
        _position(self.position)
        if not isinstance(self.initial_parameters, tuple):
            fail(ErrorCode.SCHEMA_INVALID, "initial parameters must be a tuple")
        names = []
        for parameter in self.initial_parameters:
            if not isinstance(parameter, NamedParameterValue):
                fail(ErrorCode.SCHEMA_INVALID, "invalid initial parameter")
            names.append(parameter.name)
        if len(names) != len(set(names)):
            fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "duplicate initial parameter name")

    def to_dict(self):
        return {
            "version": self.version,
            "entity": self.entity.to_dict(),
            "parent": self.parent.to_dict(),
            "operator_type": self.operator_type,
            "name": self.name,
            "position": list(self.position),
            "initial_parameters": [value.to_dict() for value in self.initial_parameters],
        }

    @classmethod
    def from_dict(cls, data):
        _keys(data, ("version", "entity", "parent", "operator_type", "name", "position", "initial_parameters"))
        return cls(
            data["version"],
            EntityRef.from_dict(data["entity"]),
            EntityRef.from_dict(data["parent"]),
            data["operator_type"],
            data["name"],
            tuple(data["position"]),
            tuple(NamedParameterValue.from_dict(value) for value in data["initial_parameters"]),
        )


@dataclass(frozen=True)
class SubtreeConnection:
    version: int
    destination: EntityRef
    input_index: int
    source: ConnectionRef

    def __post_init__(self):
        _version(self.version, "subtree connection")
        if not isinstance(self.destination, EntityRef) or not isinstance(self.source, ConnectionRef):
            fail(ErrorCode.SCHEMA_INVALID, "invalid subtree connection reference")
        if type(self.input_index) is not int or not 0 <= self.input_index <= MAX_INPUT_INDEX:
            fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "invalid destination input index")

    def to_dict(self):
        return {
            "version": self.version,
            "destination": self.destination.to_dict(),
            "input_index": self.input_index,
            "source": self.source.to_dict(),
        }

    @classmethod
    def from_dict(cls, data):
        _keys(data, ("version", "destination", "input_index", "source"))
        return cls(
            data["version"],
            EntityRef.from_dict(data["destination"]),
            data["input_index"],
            ConnectionRef.from_dict(data["source"]),
        )


class Operation:
    operation_type: OperationType

    def validate_common(self):
        _version(self.version, "operation")
        _identifier(self.operation_id, "operation_id")


@dataclass(frozen=True)
class CreateNode(Operation):
    version: int
    operation_id: str
    spec: CreateNodeSpec
    operation_type = OperationType.CREATE_NODE

    def __post_init__(self):
        self.validate_common()
        if not isinstance(self.spec, CreateNodeSpec):
            fail(ErrorCode.SCHEMA_INVALID, "create-node operation requires a node spec")

    def to_dict(self):
        return {"version": self.version, "operation_type": self.operation_type.value, "operation_id": self.operation_id, "spec": self.spec.to_dict()}


@dataclass(frozen=True)
class CreateSubtree(Operation):
    version: int
    operation_id: str
    nodes: tuple[CreateNodeSpec, ...]
    connections: tuple[SubtreeConnection, ...] = ()
    operation_type = OperationType.CREATE_SUBTREE

    def __post_init__(self):
        self.validate_common()
        if not isinstance(self.nodes, tuple) or not 1 <= len(self.nodes) <= MAX_SUBTREE_NODES:
            fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "copied subtree node count is invalid")
        ids = []
        seen = set()
        for spec in self.nodes:
            if not isinstance(spec, CreateNodeSpec):
                fail(ErrorCode.SCHEMA_INVALID, "subtree contains invalid node spec")
            if spec.entity.entity_id in seen:
                fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "copied subtree contains duplicate IDs")
            ids.append(spec.entity.entity_id)
            seen.add(spec.entity.entity_id)
        for connection in self.connections:
            if not isinstance(connection, SubtreeConnection):
                fail(ErrorCode.SCHEMA_INVALID, "subtree contains invalid connection")
            if connection.destination.entity_id not in seen:
                fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "subtree connection destination must be newly created")

    def to_dict(self):
        return {
            "version": self.version,
            "operation_type": self.operation_type.value,
            "operation_id": self.operation_id,
            "nodes": [node.to_dict() for node in self.nodes],
            "connections": [connection.to_dict() for connection in self.connections],
        }


@dataclass(frozen=True)
class DeleteSubtree(Operation):
    version: int
    operation_id: str
    root: EntityRef
    deleted_entity_ids: tuple[str, ...]
    expected_parent_id: str | None = None
    operation_type = OperationType.DELETE_SUBTREE

    def __post_init__(self):
        self.validate_common()
        if not isinstance(self.root, EntityRef):
            fail(ErrorCode.SCHEMA_INVALID, "delete root must be EntityRef")
        if not isinstance(self.deleted_entity_ids, tuple) or not self.deleted_entity_ids:
            fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "delete set cannot be empty")
        for entity_id in self.deleted_entity_ids:
            _identifier(entity_id, "deleted_entity_id")
        if self.deleted_entity_ids[0] != self.root.entity_id:
            fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "delete root must be first in deletion set")
        if len(self.deleted_entity_ids) != len(set(self.deleted_entity_ids)):
            fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "delete set contains duplicate IDs")
        if self.expected_parent_id is not None:
            _identifier(self.expected_parent_id, "expected_parent_id")

    def to_dict(self):
        return {
            "version": self.version,
            "operation_type": self.operation_type.value,
            "operation_id": self.operation_id,
            "root": self.root.to_dict(),
            "deleted_entity_ids": list(self.deleted_entity_ids),
            "expected_parent_id": self.expected_parent_id,
        }


@dataclass(frozen=True)
class RenameNode(Operation):
    version: int
    operation_id: str
    entity: EntityRef
    name: str
    expected_name: str | None = None
    operation_type = OperationType.RENAME_NODE

    def __post_init__(self):
        self.validate_common()
        if not isinstance(self.entity, EntityRef):
            fail(ErrorCode.SCHEMA_INVALID, "rename target must be EntityRef")
        _name(self.name)
        if self.expected_name is not None:
            _name(self.expected_name, "expected name")

    def to_dict(self):
        return {
            "version": self.version,
            "operation_type": self.operation_type.value,
            "operation_id": self.operation_id,
            "entity": self.entity.to_dict(),
            "name": self.name,
            "expected_name": self.expected_name,
        }


@dataclass(frozen=True)
class MoveNode(Operation):
    version: int
    operation_id: str
    entity: EntityRef
    position: tuple[float, float]
    expected_position: tuple[float, float] | None = None
    operation_type = OperationType.MOVE_NODE

    def __post_init__(self):
        self.validate_common()
        if not isinstance(self.entity, EntityRef):
            fail(ErrorCode.SCHEMA_INVALID, "move target must be EntityRef")
        _position(self.position)
        if self.expected_position is not None:
            _position(self.expected_position)

    def to_dict(self):
        return {
            "version": self.version,
            "operation_type": self.operation_type.value,
            "operation_id": self.operation_id,
            "entity": self.entity.to_dict(),
            "position": list(self.position),
            "expected_position": None if self.expected_position is None else list(self.expected_position),
        }


@dataclass(frozen=True)
class SetInput(Operation):
    version: int
    operation_id: str
    destination: EntityRef
    input_index: int
    expected_source: ConnectionRef | None
    new_source: ConnectionRef | None
    operation_type = OperationType.SET_INPUT

    def __post_init__(self):
        self.validate_common()
        if not isinstance(self.destination, EntityRef):
            fail(ErrorCode.SCHEMA_INVALID, "input destination must be EntityRef")
        if type(self.input_index) is not int or not 0 <= self.input_index <= MAX_INPUT_INDEX:
            fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "invalid destination input index")
        if self.expected_source is not None and not isinstance(self.expected_source, ConnectionRef):
            fail(ErrorCode.SCHEMA_INVALID, "expected source must be ConnectionRef or null")
        if self.new_source is not None and not isinstance(self.new_source, ConnectionRef):
            fail(ErrorCode.SCHEMA_INVALID, "new source must be ConnectionRef or null")

    def to_dict(self):
        return {
            "version": self.version,
            "operation_type": self.operation_type.value,
            "operation_id": self.operation_id,
            "destination": self.destination.to_dict(),
            "input_index": self.input_index,
            "expected_source": None if self.expected_source is None else self.expected_source.to_dict(),
            "new_source": None if self.new_source is None else self.new_source.to_dict(),
        }


@dataclass(frozen=True)
class SetParameterTuple(Operation):
    version: int
    operation_id: str
    entity: EntityRef
    parameter_name: str
    value: ParameterTupleValue
    expected_value: ParameterTupleValue | None = None
    operation_type = OperationType.SET_PARAMETER_TUPLE

    def __post_init__(self):
        self.validate_common()
        if not isinstance(self.entity, EntityRef):
            fail(ErrorCode.SCHEMA_INVALID, "parameter target must be EntityRef")
        _name(self.parameter_name, "parameter name")
        if not isinstance(self.value, ParameterTupleValue):
            fail(ErrorCode.SCHEMA_INVALID, "parameter value must be complete tuple value")
        if self.expected_value is not None and not isinstance(self.expected_value, ParameterTupleValue):
            fail(ErrorCode.SCHEMA_INVALID, "expected parameter value must be tuple value or null")
        if self.expected_value is not None and len(self.expected_value.values) != len(self.value.values):
            fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "expected and final tuple arity differ")

    def to_dict(self):
        return {
            "version": self.version,
            "operation_type": self.operation_type.value,
            "operation_id": self.operation_id,
            "entity": self.entity.to_dict(),
            "parameter_name": self.parameter_name,
            "value": self.value.to_dict(),
            "expected_value": None if self.expected_value is None else self.expected_value.to_dict(),
        }


OperationRecord = Union[
    CreateNode,
    CreateSubtree,
    DeleteSubtree,
    RenameNode,
    MoveNode,
    SetInput,
    SetParameterTuple,
]


def operation_from_dict(data):
    if not isinstance(data, dict):
        fail(ErrorCode.SCHEMA_INVALID, "operation must be an object")
    try:
        operation_type = OperationType(data.get("operation_type"))
    except (TypeError, ValueError):
        fail(ErrorCode.OPERATION_UNKNOWN_TYPE, "unknown operation type")
    if operation_type is OperationType.CREATE_NODE:
        _keys(data, ("version", "operation_type", "operation_id", "spec"))
        return CreateNode(data["version"], data["operation_id"], CreateNodeSpec.from_dict(data["spec"]))
    if operation_type is OperationType.CREATE_SUBTREE:
        _keys(data, ("version", "operation_type", "operation_id", "nodes", "connections"))
        return CreateSubtree(
            data["version"],
            data["operation_id"],
            tuple(CreateNodeSpec.from_dict(value) for value in data["nodes"]),
            tuple(SubtreeConnection.from_dict(value) for value in data["connections"]),
        )
    if operation_type is OperationType.DELETE_SUBTREE:
        _keys(data, ("version", "operation_type", "operation_id", "root", "deleted_entity_ids", "expected_parent_id"))
        return DeleteSubtree(
            data["version"], data["operation_id"], EntityRef.from_dict(data["root"]),
            tuple(data["deleted_entity_ids"]), data["expected_parent_id"]
        )
    if operation_type is OperationType.RENAME_NODE:
        _keys(data, ("version", "operation_type", "operation_id", "entity", "name", "expected_name"))
        return RenameNode(data["version"], data["operation_id"], EntityRef.from_dict(data["entity"]), data["name"], data["expected_name"])
    if operation_type is OperationType.MOVE_NODE:
        _keys(data, ("version", "operation_type", "operation_id", "entity", "position", "expected_position"))
        expected = data["expected_position"]
        return MoveNode(data["version"], data["operation_id"], EntityRef.from_dict(data["entity"]), tuple(data["position"]), None if expected is None else tuple(expected))
    if operation_type is OperationType.SET_INPUT:
        _keys(data, ("version", "operation_type", "operation_id", "destination", "input_index", "expected_source", "new_source"))
        return SetInput(
            data["version"], data["operation_id"], EntityRef.from_dict(data["destination"]), data["input_index"],
            None if data["expected_source"] is None else ConnectionRef.from_dict(data["expected_source"]),
            None if data["new_source"] is None else ConnectionRef.from_dict(data["new_source"]),
        )
    _keys(data, ("version", "operation_type", "operation_id", "entity", "parameter_name", "value", "expected_value"))
    return SetParameterTuple(
        data["version"], data["operation_id"], EntityRef.from_dict(data["entity"]), data["parameter_name"],
        ParameterTupleValue.from_dict(data["value"]),
        None if data["expected_value"] is None else ParameterTupleValue.from_dict(data["expected_value"]),
    )


@dataclass(frozen=True)
class Transaction:
    version: int
    transaction_id: str
    author_client_id: str
    session_id: str
    operations: tuple[OperationRecord, ...]
    activity_label: str | None = None
    required_operation_types: tuple[OperationType, ...] = ()

    def __post_init__(self):
        _version(self.version, "transaction")
        _identifier(self.transaction_id, "transaction_id")
        _identifier(self.author_client_id, "author_client_id")
        _identifier(self.session_id, "session_id")
        if not isinstance(self.operations, tuple) or not 1 <= len(self.operations) <= MAX_OPERATIONS:
            fail(ErrorCode.TRANSACTION_INVALID, "transaction operation count is invalid")
        operation_ids = []
        types = []
        for operation in self.operations:
            if not isinstance(operation, (CreateNode, CreateSubtree, DeleteSubtree, RenameNode, MoveNode, SetInput, SetParameterTuple)):
                fail(ErrorCode.TRANSACTION_INVALID, "transaction contains unsupported operation")
            operation_ids.append(operation.operation_id)
            types.append(operation.operation_type)
        if len(operation_ids) != len(set(operation_ids)):
            fail(ErrorCode.TRANSACTION_INVALID, "transaction contains duplicate operation IDs")
        if self.activity_label is not None and (
            not isinstance(self.activity_label, str) or not self.activity_label or len(self.activity_label) > 256
        ):
            fail(ErrorCode.TRANSACTION_INVALID, "invalid activity label")
        if not isinstance(self.required_operation_types, tuple):
            fail(ErrorCode.TRANSACTION_INVALID, "capability requirements must be a tuple")
        if any(not isinstance(value, OperationType) for value in self.required_operation_types):
            fail(ErrorCode.TRANSACTION_INVALID, "unknown required capability")
        if len(self.required_operation_types) != len(set(self.required_operation_types)):
            fail(ErrorCode.TRANSACTION_INVALID, "duplicate capability requirement")
        missing = set(types).difference(self.required_operation_types)
        if self.required_operation_types and missing:
            fail(ErrorCode.TRANSACTION_INVALID, "capability requirements omit operation type")

    def to_dict(self):
        return {
            "version": self.version,
            "transaction_id": self.transaction_id,
            "author_client_id": self.author_client_id,
            "session_id": self.session_id,
            "operations": [operation.to_dict() for operation in self.operations],
            "activity_label": self.activity_label,
            "required_operation_types": [value.value for value in self.required_operation_types],
        }

    @classmethod
    def from_dict(cls, data):
        _keys(data, ("version", "transaction_id", "author_client_id", "session_id", "operations", "activity_label", "required_operation_types"))
        if not isinstance(data["operations"], list) or not isinstance(data["required_operation_types"], list):
            fail(ErrorCode.SCHEMA_INVALID, "transaction arrays are invalid")
        return cls(
            data["version"], data["transaction_id"], data["author_client_id"], data["session_id"],
            tuple(operation_from_dict(value) for value in data["operations"]), data["activity_label"],
            tuple(
                _enum_value(OperationType, value, "required_operation_type")
                for value in data["required_operation_types"]
            ),
        )

    def semantic_json(self):
        return deterministic_json(self)


@dataclass(frozen=True)
class CapabilitySet:
    version: int
    protocol_version: int
    transaction_schema_version: int
    operation_schema_version: int
    operation_types: tuple[OperationType, ...]

    def __post_init__(self):
        _version(self.version, "capability set")
        for value, name in (
            (self.protocol_version, "protocol"),
            (self.transaction_schema_version, "transaction schema"),
            (self.operation_schema_version, "operation schema"),
        ):
            if type(value) is not int or value != MODEL_VERSION:
                fail(ErrorCode.CAPABILITY_INCOMPATIBLE, f"unsupported {name} version")
        if not isinstance(self.operation_types, tuple) or not self.operation_types:
            fail(ErrorCode.CAPABILITY_INCOMPATIBLE, "operation capability list is empty")
        if any(not isinstance(value, OperationType) for value in self.operation_types):
            fail(ErrorCode.CAPABILITY_INCOMPATIBLE, "unknown operation capability")
        if tuple(sorted(set(self.operation_types), key=lambda value: value.value)) != self.operation_types:
            fail(ErrorCode.CAPABILITY_INCOMPATIBLE, "operation capabilities must be unique and sorted")

    @classmethod
    def v1(cls):
        return cls(MODEL_VERSION, MODEL_VERSION, MODEL_VERSION, MODEL_VERSION, tuple(sorted(OperationType, key=lambda value: value.value)))

    def supports(self, transaction):
        required = set(transaction.required_operation_types)
        required.update(operation.operation_type for operation in transaction.operations)
        return required.issubset(self.operation_types)

    def compatible_with(self, offered):
        return (
            isinstance(offered, CapabilitySet)
            and self.protocol_version == offered.protocol_version
            and self.transaction_schema_version == offered.transaction_schema_version
            and self.operation_schema_version == offered.operation_schema_version
            and set(self.operation_types).issubset(offered.operation_types)
        )

    def to_dict(self):
        return {
            "version": self.version,
            "protocol_version": self.protocol_version,
            "transaction_schema_version": self.transaction_schema_version,
            "operation_schema_version": self.operation_schema_version,
            "operation_types": [value.value for value in self.operation_types],
        }

    @classmethod
    def from_dict(cls, data):
        _keys(data, ("version", "protocol_version", "transaction_schema_version", "operation_schema_version", "operation_types"))
        return cls(
            data["version"], data["protocol_version"], data["transaction_schema_version"], data["operation_schema_version"],
            tuple(
                _enum_value(OperationType, value, "operation_type")
                for value in data["operation_types"]
            ),
        )


@dataclass(frozen=True)
class AcceptedTransaction:
    version: int
    sequence: int
    authority_id: str
    transaction: Transaction

    def __post_init__(self):
        _version(self.version, "accepted transaction")
        if type(self.sequence) is not int or self.sequence < 1:
            fail(ErrorCode.SCHEMA_INVALID, "canonical transaction sequence must be positive")
        _identifier(self.authority_id, "authority_id")
        if not isinstance(self.transaction, Transaction):
            fail(ErrorCode.SCHEMA_INVALID, "accepted transaction is missing transaction")

    def to_dict(self):
        return {"version": self.version, "sequence": self.sequence, "authority_id": self.authority_id, "transaction": self.transaction.to_dict()}

    @classmethod
    def from_dict(cls, data):
        _keys(data, ("version", "sequence", "authority_id", "transaction"))
        return cls(data["version"], data["sequence"], data["authority_id"], Transaction.from_dict(data["transaction"]))


@dataclass(frozen=True)
class RejectedTransaction:
    version: int
    transaction_id: str
    session_id: str
    error: ErrorDetail

    def __post_init__(self):
        _version(self.version, "rejected transaction")
        _identifier(self.transaction_id, "transaction_id")
        _identifier(self.session_id, "session_id")
        if not isinstance(self.error, ErrorDetail):
            fail(ErrorCode.SCHEMA_INVALID, "rejection requires structured error")

    def to_dict(self):
        return {"version": self.version, "transaction_id": self.transaction_id, "session_id": self.session_id, "error": self.error.to_dict()}

    @classmethod
    def from_dict(cls, data):
        _keys(data, ("version", "transaction_id", "session_id", "error"))
        return cls(data["version"], data["transaction_id"], data["session_id"], ErrorDetail.from_dict(data["error"]))


@dataclass(frozen=True)
class PendingLocalTransaction:
    version: int
    transaction: Transaction
    submission_order: int
    attempts: int
    connection_generation: int

    def __post_init__(self):
        _version(self.version, "pending local transaction")
        if not isinstance(self.transaction, Transaction):
            fail(ErrorCode.SCHEMA_INVALID, "pending record requires transaction")
        if type(self.submission_order) is not int or self.submission_order < 1:
            fail(ErrorCode.SCHEMA_INVALID, "invalid submission order")
        if type(self.attempts) is not int or self.attempts < 1:
            fail(ErrorCode.SCHEMA_INVALID, "invalid attempt count")
        if type(self.connection_generation) is not int or self.connection_generation < 1:
            fail(ErrorCode.SCHEMA_INVALID, "invalid connection generation")

    def to_dict(self):
        return {
            "version": self.version,
            "transaction": self.transaction.to_dict(),
            "submission_order": self.submission_order,
            "attempts": self.attempts,
            "connection_generation": self.connection_generation,
        }

    @classmethod
    def from_dict(cls, data):
        _keys(data, ("version", "transaction", "submission_order", "attempts", "connection_generation"))
        return cls(data["version"], Transaction.from_dict(data["transaction"]), data["submission_order"], data["attempts"], data["connection_generation"])


@dataclass(frozen=True)
class ApplyResult:
    version: int
    success: bool
    changed: bool
    error: ErrorDetail | None = None

    def __post_init__(self):
        _version(self.version, "apply result")
        if type(self.success) is not bool or type(self.changed) is not bool:
            fail(ErrorCode.SCHEMA_INVALID, "apply result flags must be boolean")
        if self.success and self.error is not None:
            fail(ErrorCode.SCHEMA_INVALID, "successful apply cannot contain error")
        if not self.success and not isinstance(self.error, ErrorDetail):
            fail(ErrorCode.SCHEMA_INVALID, "failed apply requires structured error")

    def to_dict(self):
        return {"version": self.version, "success": self.success, "changed": self.changed, "error": None if self.error is None else self.error.to_dict()}

    @classmethod
    def from_dict(cls, data):
        _keys(data, ("version", "success", "changed", "error"))
        return cls(data["version"], data["success"], data["changed"], None if data["error"] is None else ErrorDetail.from_dict(data["error"]))


@dataclass(frozen=True)
class ClientSequenceState:
    version: int
    last_received: int
    last_applied: int
    last_confirmed: int

    def __post_init__(self):
        _version(self.version, "client sequence state")
        values = (self.last_received, self.last_applied, self.last_confirmed)
        if any(type(value) is not int or value < 0 for value in values):
            fail(ErrorCode.SCHEMA_INVALID, "sequence values must be non-negative integers")
        if self.last_confirmed > self.last_applied or self.last_applied > self.last_received:
            fail(ErrorCode.SCHEMA_INVALID, "client sequence state is contradictory")

    def to_dict(self):
        return {"version": self.version, "last_received": self.last_received, "last_applied": self.last_applied, "last_confirmed": self.last_confirmed}

    @classmethod
    def from_dict(cls, data):
        _keys(data, ("version", "last_received", "last_applied", "last_confirmed"))
        return cls(**data)


@dataclass(frozen=True)
class ResumeRequest:
    version: int
    session_id: str
    client_id: str
    connection_generation: int
    after_sequence: int
    pending_transaction_ids: tuple[str, ...]

    def __post_init__(self):
        _version(self.version, "resume request")
        _identifier(self.session_id, "session_id")
        _identifier(self.client_id, "client_id")
        if type(self.connection_generation) is not int or self.connection_generation < 1:
            fail(ErrorCode.SCHEMA_INVALID, "invalid connection generation")
        if type(self.after_sequence) is not int or self.after_sequence < 0:
            fail(ErrorCode.SCHEMA_INVALID, "invalid resume sequence")
        for transaction_id in self.pending_transaction_ids:
            _identifier(transaction_id, "pending_transaction_id")
        if len(set(self.pending_transaction_ids)) != len(self.pending_transaction_ids):
            fail(ErrorCode.SCHEMA_INVALID, "duplicate pending transaction ID")

    def to_dict(self):
        return {
            "version": self.version, "session_id": self.session_id, "client_id": self.client_id,
            "connection_generation": self.connection_generation, "after_sequence": self.after_sequence,
            "pending_transaction_ids": list(self.pending_transaction_ids),
        }

    @classmethod
    def from_dict(cls, data):
        _keys(data, ("version", "session_id", "client_id", "connection_generation", "after_sequence", "pending_transaction_ids"))
        return cls(data["version"], data["session_id"], data["client_id"], data["connection_generation"], data["after_sequence"], tuple(data["pending_transaction_ids"]))


@dataclass(frozen=True)
class ResumeResult:
    version: int
    status: ResumeStatus
    session_id: str
    after_sequence: int
    earliest_resumable_sequence: int
    latest_sequence: int
    history: tuple[AcceptedTransaction, ...]
    error: ErrorDetail | None = None

    def __post_init__(self):
        _version(self.version, "resume result")
        if not isinstance(self.status, ResumeStatus):
            fail(ErrorCode.SCHEMA_INVALID, "invalid resume status")
        _identifier(self.session_id, "session_id")
        for value in (self.after_sequence, self.earliest_resumable_sequence, self.latest_sequence):
            if type(value) is not int or value < 0:
                fail(ErrorCode.SCHEMA_INVALID, "resume sequence values must be non-negative")
        if any(not isinstance(value, AcceptedTransaction) for value in self.history):
            fail(ErrorCode.SCHEMA_INVALID, "resume history contains invalid record")
        if self.status is ResumeStatus.OK and self.error is not None:
            fail(ErrorCode.SCHEMA_INVALID, "successful resume cannot contain error")
        if self.status is not ResumeStatus.OK and not isinstance(self.error, ErrorDetail):
            fail(ErrorCode.SCHEMA_INVALID, "failed resume requires structured error")

    def to_dict(self):
        return {
            "version": self.version, "status": self.status.value, "session_id": self.session_id,
            "after_sequence": self.after_sequence, "earliest_resumable_sequence": self.earliest_resumable_sequence,
            "latest_sequence": self.latest_sequence, "history": [value.to_dict() for value in self.history],
            "error": None if self.error is None else self.error.to_dict(),
        }

    @classmethod
    def from_dict(cls, data):
        _keys(data, ("version", "status", "session_id", "after_sequence", "earliest_resumable_sequence", "latest_sequence", "history", "error"))
        return cls(
            data["version"],
            _enum_value(ResumeStatus, data["status"], "resume_status"),
            data["session_id"], data["after_sequence"],
            data["earliest_resumable_sequence"], data["latest_sequence"],
            tuple(AcceptedTransaction.from_dict(value) for value in data["history"]),
            None if data["error"] is None else ErrorDetail.from_dict(data["error"]),
        )


def deterministic_json(model):
    if not hasattr(model, "to_dict"):
        fail(ErrorCode.SCHEMA_INVALID, "model is not serializable")
    return json.dumps(model.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
