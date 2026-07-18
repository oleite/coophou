"""Deterministic in-memory projection of the supported collaborative state."""

from collections import OrderedDict
from dataclasses import dataclass, field
import copy
import json

from .errors import DomainError, ErrorCode, ErrorDetail, fail
from .models import (
    MODEL_VERSION,
    ApplyResult,
    ConnectionRef,
    CreateNode,
    CreateNodeSpec,
    CreateSubtree,
    DeleteSubtree,
    EntityRef,
    MoveNode,
    NamedParameterValue,
    ParameterTupleValue,
    RenameNode,
    SetInput,
    SetParameterTuple,
    Transaction,
)


ROOT_ENTITY_ID = "root"


@dataclass
class SceneEntity:
    version: int
    entity_id: str
    parent_id: str | None
    operator_type: str
    name: str
    position: tuple[float, float]
    parameters: dict[str, ParameterTupleValue] = field(default_factory=dict)
    inputs: dict[int, ConnectionRef] = field(default_factory=dict)


@dataclass(frozen=True)
class Tombstone:
    version: int
    entity_id: str
    parent_id: str | None
    last_known_path: str

    def to_dict(self):
        return {
            "version": self.version,
            "entity_id": self.entity_id,
            "parent_id": self.parent_id,
            "last_known_path": self.last_known_path,
        }


class FakeScene:
    """Only the v1 collaborative projection; no Houdini behavior or cooking."""

    def __init__(self, applied_history_limit=4096):
        if applied_history_limit < 1:
            raise ValueError("applied transaction history limit must be positive")
        self.applied_history_limit = applied_history_limit
        self.entities = {
            ROOT_ENTITY_ID: SceneEntity(
                version=MODEL_VERSION,
                entity_id=ROOT_ENTITY_ID,
                parent_id=None,
                operator_type="root",
                name="",
                position=(0.0, 0.0),
            )
        }
        self.tombstones = {}
        self._applied_transactions = OrderedDict()

    @classmethod
    def initial(cls):
        return cls()

    def clone(self):
        duplicate = FakeScene.__new__(FakeScene)
        duplicate.entities = copy.deepcopy(self.entities)
        duplicate.tombstones = dict(self.tombstones)
        duplicate.applied_history_limit = self.applied_history_limit
        duplicate._applied_transactions = OrderedDict(self._applied_transactions)
        return duplicate

    def replace_with(self, other):
        self.entities = other.entities
        self.tombstones = other.tombstones
        self._applied_transactions = other._applied_transactions
        self.applied_history_limit = other.applied_history_limit

    def entity_ref(self, entity_id):
        entity = self.require_live(entity_id)
        return EntityRef(MODEL_VERSION, entity.entity_id, "node", self.path(entity_id))

    def require_live(self, entity_id):
        if entity_id in self.tombstones:
            fail(ErrorCode.ENTITY_DELETED, "entity has been deleted", entity_id=entity_id)
        entity = self.entities.get(entity_id)
        if entity is None:
            fail(ErrorCode.ENTITY_NOT_FOUND, "entity does not exist", entity_id=entity_id)
        return entity

    def path(self, entity_id):
        entity = self.require_live(entity_id)
        if entity.entity_id == ROOT_ENTITY_ID:
            return "/"
        parts = []
        visited = set()
        while entity.entity_id != ROOT_ENTITY_ID:
            if entity.entity_id in visited:
                fail(ErrorCode.APPLICATION_FAILED, "parent hierarchy contains a cycle")
            visited.add(entity.entity_id)
            parts.append(entity.name)
            entity = self.require_live(entity.parent_id)
        return "/" + "/".join(reversed(parts))

    def child_ids(self, parent_id):
        self.require_live(parent_id)
        return tuple(sorted(
            (entity.entity_id for entity in self.entities.values() if entity.parent_id == parent_id),
            key=lambda entity_id: (self.entities[entity_id].name, entity_id),
        ))

    def subtree_ids(self, root_id):
        self.require_live(root_id)
        result = []

        def visit(entity_id):
            result.append(entity_id)
            for child_id in self.child_ids(entity_id):
                visit(child_id)

        visit(root_id)
        return tuple(result)

    def _name_available(self, parent_id, name, excluding_id=None):
        return all(
            entity.entity_id == excluding_id
            or entity.parent_id != parent_id
            or entity.name != name
            for entity in self.entities.values()
        )

    def _normalized_connection(self, value):
        if value is None:
            return None
        source = self.require_live(value.source.entity_id)
        return ConnectionRef(
            MODEL_VERSION,
            EntityRef(MODEL_VERSION, source.entity_id, "node", None),
            value.output_index,
        )

    @staticmethod
    def _connection_key(value):
        if value is None:
            return None
        return (value.source.entity_id, value.output_index)

    def _create_spec(self, spec):
        entity_id = spec.entity.entity_id
        if entity_id in self.entities:
            fail(ErrorCode.ENTITY_ALREADY_EXISTS, "entity ID is already live", entity_id=entity_id)
        if entity_id in self.tombstones:
            fail(ErrorCode.ENTITY_DELETED, "entity ID is tombstoned", entity_id=entity_id)
        parent = self.require_live(spec.parent.entity_id)
        if not self._name_available(parent.entity_id, spec.name):
            fail(
                ErrorCode.NAME_CONFLICT,
                "sibling name already exists",
                parent_id=parent.entity_id,
                name=spec.name,
            )
        self.entities[entity_id] = SceneEntity(
            version=MODEL_VERSION,
            entity_id=entity_id,
            parent_id=parent.entity_id,
            operator_type=spec.operator_type,
            name=spec.name,
            position=(float(spec.position[0]), float(spec.position[1])),
            parameters={parameter.name: parameter.value for parameter in spec.initial_parameters},
            inputs={},
        )

    def _apply_create_node(self, operation):
        self._create_spec(operation.spec)

    def _apply_create_subtree(self, operation):
        new_ids = {spec.entity.entity_id for spec in operation.nodes}
        if len(new_ids) != len(operation.nodes):
            fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "copied subtree IDs are not unique")
        created = set()
        for spec in operation.nodes:
            parent_id = spec.parent.entity_id
            if parent_id in new_ids and parent_id not in created:
                fail(
                    ErrorCode.PRECONDITION_FAILED,
                    "copied subtree is not ordered parent-before-child",
                    entity_id=spec.entity.entity_id,
                    parent_id=parent_id,
                )
            self._create_spec(spec)
            created.add(spec.entity.entity_id)
        occupied = set()
        for connection in operation.connections:
            destination_id = connection.destination.entity_id
            if destination_id not in new_ids:
                fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "connection destination is outside copied subtree")
            key = (destination_id, connection.input_index)
            if key in occupied:
                fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "duplicate copied-subtree input assignment")
            occupied.add(key)
            destination = self.require_live(destination_id)
            destination.inputs[connection.input_index] = self._normalized_connection(connection.source)

    def _apply_delete_subtree(self, operation):
        root_id = operation.root.entity_id
        if root_id == ROOT_ENTITY_ID:
            fail(ErrorCode.OPERATION_INVALID_PAYLOAD, "the fake-scene root cannot be deleted")
        if root_id in self.tombstones:
            if all(entity_id in self.tombstones for entity_id in operation.deleted_entity_ids):
                return False
            fail(ErrorCode.ENTITY_DELETED, "delete root is tombstoned but deletion set is inconsistent")
        root = self.require_live(root_id)
        if operation.expected_parent_id is not None and root.parent_id != operation.expected_parent_id:
            fail(
                ErrorCode.PRECONDITION_FAILED,
                "delete parent precondition failed",
                expected=operation.expected_parent_id,
                actual=root.parent_id,
            )
        actual = self.subtree_ids(root_id)
        if actual != operation.deleted_entity_ids:
            fail(
                ErrorCode.PRECONDITION_FAILED,
                "delete set does not match canonical subtree",
                expected=operation.deleted_entity_ids,
                actual=actual,
            )
        deleted = set(actual)
        last_known_paths = {entity_id: self.path(entity_id) for entity_id in actual}
        for entity_id in actual:
            entity = self.entities[entity_id]
            self.tombstones[entity_id] = Tombstone(
                MODEL_VERSION, entity_id, entity.parent_id, last_known_paths[entity_id]
            )
        for entity in self.entities.values():
            entity.inputs = {
                index: connection
                for index, connection in entity.inputs.items()
                if connection.source.entity_id not in deleted
            }
        for entity_id in reversed(actual):
            del self.entities[entity_id]
        return True

    def _apply_rename(self, operation):
        entity = self.require_live(operation.entity.entity_id)
        if operation.expected_name is not None and entity.name != operation.expected_name:
            fail(
                ErrorCode.PRECONDITION_FAILED,
                "rename expected-name precondition failed",
                expected=operation.expected_name,
                actual=entity.name,
            )
        if entity.name == operation.name:
            return False
        if not self._name_available(entity.parent_id, operation.name, excluding_id=entity.entity_id):
            fail(ErrorCode.NAME_CONFLICT, "canonical sibling-name rule rejected collision")
        entity.name = operation.name
        return True

    def _apply_move(self, operation):
        entity = self.require_live(operation.entity.entity_id)
        if operation.expected_position is not None and entity.position != tuple(operation.expected_position):
            fail(ErrorCode.PRECONDITION_FAILED, "move expected-position precondition failed")
        position = (float(operation.position[0]), float(operation.position[1]))
        if entity.position == position:
            return False
        entity.position = position
        return True

    def _apply_set_input(self, operation):
        destination = self.require_live(operation.destination.entity_id)
        current = destination.inputs.get(operation.input_index)
        if self._connection_key(current) != self._connection_key(operation.expected_source):
            fail(
                ErrorCode.PRECONDITION_FAILED,
                "destination input expected-source precondition failed",
                destination_id=destination.entity_id,
                input_index=operation.input_index,
            )
        normalized = self._normalized_connection(operation.new_source)
        if self._connection_key(current) == self._connection_key(normalized):
            return False
        if normalized is None:
            destination.inputs.pop(operation.input_index, None)
        else:
            destination.inputs[operation.input_index] = normalized
        return True

    def _apply_set_parameter(self, operation):
        entity = self.require_live(operation.entity.entity_id)
        current = entity.parameters.get(operation.parameter_name)
        if operation.expected_value is not None and current != operation.expected_value:
            fail(
                ErrorCode.PRECONDITION_FAILED,
                "parameter expected-value precondition failed",
                entity_id=entity.entity_id,
                parameter=operation.parameter_name,
            )
        if current == operation.value:
            return False
        entity.parameters[operation.parameter_name] = operation.value
        return True

    def _apply_operation(self, operation):
        if isinstance(operation, CreateNode):
            self._apply_create_node(operation)
            return True
        if isinstance(operation, CreateSubtree):
            self._apply_create_subtree(operation)
            return True
        if isinstance(operation, DeleteSubtree):
            return self._apply_delete_subtree(operation)
        if isinstance(operation, RenameNode):
            return self._apply_rename(operation)
        if isinstance(operation, MoveNode):
            return self._apply_move(operation)
        if isinstance(operation, SetInput):
            return self._apply_set_input(operation)
        if isinstance(operation, SetParameterTuple):
            return self._apply_set_parameter(operation)
        fail(ErrorCode.OPERATION_UNKNOWN_TYPE, "unsupported operation instance")

    def validate_invariants(self):
        if ROOT_ENTITY_ID not in self.entities:
            fail(ErrorCode.APPLICATION_FAILED, "fake-scene root is missing")
        if set(self.entities).intersection(self.tombstones):
            fail(ErrorCode.APPLICATION_FAILED, "live entities overlap tombstones")
        sibling_names = set()
        for entity in self.entities.values():
            if entity.entity_id != ROOT_ENTITY_ID and entity.parent_id not in self.entities:
                fail(ErrorCode.APPLICATION_FAILED, "entity parent is missing")
            sibling_key = (entity.parent_id, entity.name)
            if entity.entity_id != ROOT_ENTITY_ID and sibling_key in sibling_names:
                fail(ErrorCode.APPLICATION_FAILED, "sibling names are not unique")
            sibling_names.add(sibling_key)
            self.path(entity.entity_id)
            for connection in entity.inputs.values():
                if connection.source.entity_id not in self.entities:
                    fail(ErrorCode.APPLICATION_FAILED, "connection source is not live")
        return True

    def apply_transaction(self, transaction, fail_after_operation=None):
        if not isinstance(transaction, Transaction):
            detail = ErrorDetail(MODEL_VERSION, ErrorCode.TRANSACTION_INVALID, "apply requires Transaction")
            return ApplyResult(MODEL_VERSION, False, False, detail)
        semantic = transaction.semantic_json()
        previous = self._applied_transactions.get(transaction.transaction_id)
        if previous is not None:
            if previous == semantic:
                return ApplyResult(MODEL_VERSION, True, False, None)
            detail = ErrorDetail(
                MODEL_VERSION,
                ErrorCode.DUPLICATE_CONFLICT,
                "transaction ID was reused with different immutable content",
            )
            return ApplyResult(MODEL_VERSION, False, False, detail)
        staged = self.clone()
        changed = False
        try:
            if fail_after_operation == 0:
                fail(ErrorCode.APPLICATION_FAILED, "injected failure before first operation")
            for index, operation in enumerate(transaction.operations, 1):
                changed = staged._apply_operation(operation) or changed
                if fail_after_operation == index:
                    fail(
                        ErrorCode.APPLICATION_FAILED,
                        "injected failure between transaction operations",
                        completed=index,
                    )
            staged.validate_invariants()
            staged._applied_transactions[transaction.transaction_id] = semantic
            staged._applied_transactions.move_to_end(transaction.transaction_id)
            while len(staged._applied_transactions) > staged.applied_history_limit:
                staged._applied_transactions.popitem(last=False)
        except DomainError as exc:
            return ApplyResult(MODEL_VERSION, False, False, exc.detail)
        except Exception as exc:
            detail = ErrorDetail(
                MODEL_VERSION,
                ErrorCode.APPLICATION_FAILED,
                "unexpected staged application failure",
                (("exception_type", type(exc).__name__),),
            )
            return ApplyResult(MODEL_VERSION, False, False, detail)
        self.replace_with(staged)
        return ApplyResult(MODEL_VERSION, True, changed, None)

    def semantic_snapshot(self):
        entities = []
        for entity_id in sorted(self.entities):
            entity = self.entities[entity_id]
            entities.append({
                "version": entity.version,
                "entity_id": entity.entity_id,
                "parent_id": entity.parent_id,
                "operator_type": entity.operator_type,
                "name": entity.name,
                "path": self.path(entity_id),
                "position": list(entity.position),
                "parameters": {
                    name: entity.parameters[name].to_dict()
                    for name in sorted(entity.parameters)
                },
                "inputs": {
                    str(index): {
                        "source_entity_id": entity.inputs[index].source.entity_id,
                        "output_index": entity.inputs[index].output_index,
                    }
                    for index in sorted(entity.inputs)
                },
            })
        return {
            "version": MODEL_VERSION,
            "entities": entities,
            "tombstones": [self.tombstones[entity_id].to_dict() for entity_id in sorted(self.tombstones)],
        }

    def semantic_json(self):
        return json.dumps(
            self.semantic_snapshot(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    def semantically_equal(self, other):
        return isinstance(other, FakeScene) and self.semantic_snapshot() == other.semantic_snapshot()
