"""Portable optimistic client state machine for deterministic collaboration tests."""

from collections import OrderedDict
from dataclasses import replace
from enum import Enum

from .errors import DomainError, ErrorCode, ErrorDetail
from .models import (
    MODEL_VERSION,
    AcceptedTransaction,
    CapabilitySet,
    ClientSequenceState,
    PendingLocalTransaction,
    RejectedTransaction,
    ResumeRequest,
    ResumeResult,
    ResumeStatus,
    Transaction,
    validate_identifier,
)
from .scene import FakeScene


class ClientState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    JOINING = "JOINING"
    CATCHING_UP = "CATCHING_UP"
    SYNCHRONIZED = "SYNCHRONIZED"
    DEGRADED = "DEGRADED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    INCOMPATIBLE = "INCOMPATIBLE"
    FATAL = "FATAL"


class PortableClient:
    """Houdini-free client with separate confirmed and optimistic projections."""

    def __init__(
        self,
        client_id,
        session_id,
        capabilities=None,
        initial_scene=None,
        pending_limit=128,
        gap_limit=256,
        applied_history_limit=4096,
        rejection_history_limit=256,
    ):
        if (
            pending_limit < 1
            or gap_limit < 1
            or applied_history_limit < gap_limit
            or rejection_history_limit < 1
        ):
            raise ValueError("client bounds are invalid")
        self.client_id = validate_identifier(client_id, "client_id")
        self.session_id = validate_identifier(session_id, "session_id")
        self.capabilities = capabilities or CapabilitySet.v1()
        self.accepted_capabilities = None
        self.state = ClientState.DISCONNECTED
        self.transport_connected = False
        self.connection_generation = 0
        self.confirmed_scene = (initial_scene or FakeScene.initial()).clone()
        self.working_scene = self.confirmed_scene.clone()
        self.pending_limit = pending_limit
        self.gap_limit = gap_limit
        self.applied_history_limit = applied_history_limit
        self.rejection_history_limit = rejection_history_limit
        self.pending = []
        self.gap_buffer = {}
        self.last_received = 0
        self.last_applied = 0
        self.last_confirmed = 0
        self._submission_order = 0
        self._accepted_by_sequence = OrderedDict()
        self._sequence_by_transaction_id = OrderedDict()
        self.last_error = None
        self.rejections = OrderedDict()

    @property
    def sequence_state(self):
        return ClientSequenceState(
            MODEL_VERSION, self.last_received, self.last_applied, self.last_confirmed
        )

    @property
    def pending_transaction_ids(self):
        return tuple(record.transaction.transaction_id for record in self.pending)

    @property
    def is_synchronized(self):
        return self.state is ClientState.SYNCHRONIZED

    def _set_error(self, code, message, **context):
        self.last_error = ErrorDetail(
            MODEL_VERSION,
            code,
            message,
            tuple(sorted((str(key), str(value)) for key, value in context.items())),
        )

    def _terminal(self, state, code, message, **context):
        self.state = state
        self._set_error(code, message, **context)

    def begin_join(self):
        if self.state in (ClientState.FATAL, ClientState.RECONCILIATION_REQUIRED):
            return self.connection_generation
        self.connection_generation += 1
        self.transport_connected = True
        self.state = ClientState.JOINING
        return self.connection_generation

    def accept_join(self, result, connection_generation):
        if connection_generation != self.connection_generation:
            return False
        if isinstance(result, ErrorDetail):
            self.transport_connected = False
            target = (
                ClientState.INCOMPATIBLE
                if result.code is ErrorCode.CAPABILITY_INCOMPATIBLE
                else ClientState.DISCONNECTED
            )
            self.state = target
            self.last_error = result
            return False
        if not isinstance(result, CapabilitySet):
            self._terminal(
                ClientState.FATAL,
                ErrorCode.SCHEMA_INVALID,
                "join response has an invalid type",
            )
            return False
        self.accepted_capabilities = result
        self.transport_connected = True
        self.state = ClientState.CATCHING_UP
        return True

    def disconnect(self):
        self.transport_connected = False
        if self.state not in (
            ClientState.FATAL,
            ClientState.RECONCILIATION_REQUIRED,
            ClientState.INCOMPATIBLE,
        ):
            self.state = ClientState.DISCONNECTED

    def resume_request(self):
        return ResumeRequest(
            MODEL_VERSION,
            self.session_id,
            self.client_id,
            self.connection_generation,
            self.last_confirmed,
            self.pending_transaction_ids,
        )

    def submit_local(self, transaction):
        if self.state not in (ClientState.SYNCHRONIZED, ClientState.DEGRADED):
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                "local submission requires a connected client without a canonical gap",
                state=self.state.value,
            )
        if transaction.session_id != self.session_id:
            raise DomainError(ErrorCode.SESSION_MISMATCH, "transaction targets another session")
        if transaction.author_client_id != self.client_id:
            raise DomainError(
                ErrorCode.PRECONDITION_FAILED,
                "transaction author does not match client",
            )
        if len(self.pending) >= self.pending_limit:
            self._terminal(
                ClientState.RECONCILIATION_REQUIRED,
                ErrorCode.QUEUE_OVERFLOW,
                "pending local transaction queue is full",
            )
            raise DomainError(ErrorCode.QUEUE_OVERFLOW, "pending local transaction queue is full")
        if transaction.transaction_id in self.pending_transaction_ids:
            raise DomainError(
                ErrorCode.DUPLICATE_CONFLICT,
                "transaction is already pending",
            )
        applied = self.working_scene.apply_transaction(transaction)
        if not applied.success:
            raise DomainError(
                applied.error.code,
                applied.error.message,
                **dict(applied.error.context),
            )
        self._submission_order += 1
        record = PendingLocalTransaction(
            MODEL_VERSION,
            transaction,
            self._submission_order,
            1,
            self.connection_generation,
        )
        self.pending.append(record)
        self.state = ClientState.DEGRADED
        return record

    def mark_pending_retried(self, transaction_id):
        for index, record in enumerate(self.pending):
            if record.transaction.transaction_id == transaction_id:
                updated = replace(
                    record,
                    attempts=record.attempts + 1,
                    connection_generation=self.connection_generation,
                )
                self.pending[index] = updated
                return updated
        return None

    def receive_submission_result(self, result, connection_generation):
        if connection_generation != self.connection_generation:
            return False
        if isinstance(result, AcceptedTransaction):
            return True
        if not isinstance(result, RejectedTransaction):
            self._terminal(
                ClientState.FATAL,
                ErrorCode.SCHEMA_INVALID,
                "submission response has an invalid type",
            )
            return False
        if result.session_id != self.session_id:
            self._terminal(
                ClientState.FATAL,
                ErrorCode.SESSION_MISMATCH,
                "rejection targets another session",
            )
            return False
        matching = [
            record
            for record in self.pending
            if record.transaction.transaction_id == result.transaction_id
        ]
        if not matching:
            return True
        self.pending = [
            record
            for record in self.pending
            if record.transaction.transaction_id != result.transaction_id
        ]
        self.rejections[result.transaction_id] = result.error
        self.rejections.move_to_end(result.transaction_id)
        while len(self.rejections) > self.rejection_history_limit:
            self.rejections.popitem(last=False)
        self.last_error = result.error
        return self._rebuild_working_scene()

    def receive_canonical(self, accepted, connection_generation):
        if connection_generation != self.connection_generation:
            return False
        if not isinstance(accepted, AcceptedTransaction):
            self._terminal(
                ClientState.FATAL,
                ErrorCode.SCHEMA_INVALID,
                "canonical delivery has an invalid type",
            )
            return False
        if accepted.transaction.session_id != self.session_id:
            self._terminal(
                ClientState.FATAL,
                ErrorCode.SESSION_MISMATCH,
                "canonical transaction targets another session",
            )
            return False

        sequence = accepted.sequence
        transaction_id = accepted.transaction.transaction_id
        previous_sequence = self._sequence_by_transaction_id.get(transaction_id)
        if previous_sequence is not None and previous_sequence != sequence:
            self._terminal(
                ClientState.FATAL,
                ErrorCode.SEQUENCE_CONTRADICTION,
                "accepted transaction ID appeared at more than one canonical sequence",
                first_sequence=previous_sequence,
                sequence=sequence,
                transaction_id=transaction_id,
            )
            return False
        known = self._accepted_by_sequence.get(sequence)
        if known is not None:
            if known != accepted.transaction.semantic_json():
                self._terminal(
                    ClientState.FATAL,
                    ErrorCode.SEQUENCE_CONTRADICTION,
                    "canonical sequence was reused for different content",
                    sequence=sequence,
                )
                return False
            return True
        buffered = self.gap_buffer.get(sequence)
        if buffered is not None:
            if buffered.transaction.semantic_json() != accepted.transaction.semantic_json():
                self._terminal(
                    ClientState.FATAL,
                    ErrorCode.SEQUENCE_CONTRADICTION,
                    "buffered canonical sequence has conflicting content",
                    sequence=sequence,
                )
                return False
            return True
        if sequence <= self.last_confirmed:
            return True

        self.last_received = max(self.last_received, sequence)
        expected = self.last_confirmed + 1
        if sequence != expected:
            if len(self.gap_buffer) >= self.gap_limit:
                self._terminal(
                    ClientState.RECONCILIATION_REQUIRED,
                    ErrorCode.QUEUE_OVERFLOW,
                    "canonical gap buffer is full",
                )
                return False
            self.gap_buffer[sequence] = accepted
            self.state = ClientState.CATCHING_UP
            return False

        if not self._apply_contiguous(accepted):
            return False
        while self.last_confirmed + 1 in self.gap_buffer:
            following = self.gap_buffer.pop(self.last_confirmed + 1)
            if not self._apply_contiguous(following):
                return False
        self._refresh_health()
        return True

    def _apply_contiguous(self, accepted):
        expected = self.last_confirmed + 1
        if accepted.sequence != expected:
            self._terminal(
                ClientState.FATAL,
                ErrorCode.SEQUENCE_CONTRADICTION,
                "attempted non-contiguous canonical application",
            )
            return False
        pending = next(
            (
                record
                for record in self.pending
                if record.transaction.transaction_id
                == accepted.transaction.transaction_id
            ),
            None,
        )
        if pending is not None and (
            pending.transaction.semantic_json() != accepted.transaction.semantic_json()
        ):
            self._terminal(
                ClientState.FATAL,
                ErrorCode.DUPLICATE_CONFLICT,
                "canonical content conflicts with the pending transaction ID",
            )
            return False
        result = self.confirmed_scene.apply_transaction(accepted.transaction)
        if not result.success:
            self.state = ClientState.RECONCILIATION_REQUIRED
            self.last_error = result.error
            return False
        self.last_applied = accepted.sequence
        self.last_confirmed = accepted.sequence
        self.last_received = max(self.last_received, accepted.sequence)
        self._accepted_by_sequence[accepted.sequence] = accepted.transaction.semantic_json()
        self._sequence_by_transaction_id[
            accepted.transaction.transaction_id
        ] = accepted.sequence
        while len(self._accepted_by_sequence) > self.applied_history_limit:
            self._accepted_by_sequence.popitem(last=False)
        while len(self._sequence_by_transaction_id) > self.applied_history_limit:
            self._sequence_by_transaction_id.popitem(last=False)
        if pending is not None:
            self.pending.remove(pending)
        return self._rebuild_working_scene(refresh=False)

    def _rebuild_working_scene(self, refresh=True):
        rebuilt = self.confirmed_scene.clone()
        for record in sorted(self.pending, key=lambda value: value.submission_order):
            result = rebuilt.apply_transaction(record.transaction)
            if not result.success:
                self.state = ClientState.RECONCILIATION_REQUIRED
                self.last_error = ErrorDetail(
                    MODEL_VERSION,
                    ErrorCode.RECONCILIATION_REQUIRED,
                    "pending transaction is invalid on the confirmed checkpoint",
                    (
                        ("cause", result.error.code.value),
                        ("transaction_id", record.transaction.transaction_id),
                    ),
                )
                return False
        self.working_scene = rebuilt
        if refresh:
            self._refresh_health()
        return True

    def receive_resume_result(self, result, connection_generation):
        if connection_generation != self.connection_generation:
            return False
        if not isinstance(result, ResumeResult) or result.session_id != self.session_id:
            self._terminal(
                ClientState.FATAL,
                ErrorCode.SCHEMA_INVALID,
                "resume response is invalid for this session",
            )
            return False
        if result.status is not ResumeStatus.OK:
            state = (
                ClientState.INCOMPATIBLE
                if result.status is ResumeStatus.INCOMPATIBLE
                else ClientState.RECONCILIATION_REQUIRED
            )
            self.state = state
            self.last_error = result.error
            return False
        if result.after_sequence != self.last_confirmed:
            self._terminal(
                ClientState.FATAL,
                ErrorCode.SEQUENCE_CONTRADICTION,
                "resume response does not match requested checkpoint",
            )
            return False
        for accepted in result.history:
            if not self.receive_canonical(accepted, connection_generation):
                if self.state is not ClientState.CATCHING_UP:
                    return False
        if self.last_confirmed != result.latest_sequence:
            self.state = ClientState.CATCHING_UP
            self._set_error(
                ErrorCode.HISTORY_GAP,
                "resume did not provide contiguous history through the authority head",
            )
            return False
        self._refresh_health()
        return True

    def _refresh_health(self):
        if self.state in (
            ClientState.FATAL,
            ClientState.RECONCILIATION_REQUIRED,
            ClientState.INCOMPATIBLE,
        ):
            return
        if not self.transport_connected:
            self.state = ClientState.DISCONNECTED
        elif self.gap_buffer:
            self.state = ClientState.CATCHING_UP
        elif self.pending:
            self.state = ClientState.DEGRADED
        else:
            self.state = ClientState.SYNCHRONIZED
