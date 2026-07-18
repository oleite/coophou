"""In-memory canonical transaction authority with isolated sessions."""

from collections import OrderedDict, deque
from dataclasses import dataclass

from .errors import ErrorCode, ErrorDetail
from .models import (
    MODEL_VERSION,
    AcceptedTransaction,
    CapabilitySet,
    RejectedTransaction,
    ResumeRequest,
    ResumeResult,
    ResumeStatus,
    Transaction,
    validate_identifier,
)
from .scene import FakeScene


@dataclass
class AuthoritySession:
    session_id: str
    capabilities: CapabilitySet
    scene: FakeScene
    next_sequence: int
    history: deque
    history_limit: int
    deduplication: OrderedDict
    deduplication_limit: int

    @property
    def latest_sequence(self):
        return self.next_sequence - 1

    @property
    def earliest_resumable_sequence(self):
        if not self.history:
            return self.latest_sequence
        return self.history[0].sequence - 1

    def remember(self, transaction_id, semantic_json, result):
        self.deduplication[transaction_id] = (semantic_json, result)
        self.deduplication.move_to_end(transaction_id)
        while len(self.deduplication) > self.deduplication_limit:
            self.deduplication.popitem(last=False)


class FakeAuthority:
    def __init__(
        self,
        authority_id="authority",
        capabilities=None,
        history_limit=256,
        deduplication_limit=1024,
    ):
        if history_limit < 1 or deduplication_limit < history_limit:
            raise ValueError("authority bounds are invalid")
        self.authority_id = validate_identifier(authority_id, "authority_id")
        self.capabilities = capabilities or CapabilitySet.v1()
        self.history_limit = history_limit
        self.deduplication_limit = deduplication_limit
        self.sessions = {}

    def create_session(self, session_id, initial_scene=None, capabilities=None):
        validate_identifier(session_id, "session_id")
        if session_id in self.sessions:
            raise ValueError("session already exists")
        accepted = capabilities or self.capabilities
        if not accepted.compatible_with(self.capabilities):
            raise ValueError("session capabilities exceed authority capabilities")
        self.sessions[session_id] = AuthoritySession(
            session_id=session_id,
            capabilities=accepted,
            scene=(initial_scene or FakeScene.initial()).clone(),
            next_sequence=1,
            history=deque(maxlen=self.history_limit),
            history_limit=self.history_limit,
            deduplication=OrderedDict(),
            deduplication_limit=self.deduplication_limit,
        )
        return self.sessions[session_id]

    def session(self, session_id):
        return self.sessions.get(session_id)

    def join(self, session_id, offered_capabilities):
        session = self.session(session_id)
        if session is None:
            return ErrorDetail(MODEL_VERSION, ErrorCode.SESSION_NOT_FOUND, "session does not exist")
        if not session.capabilities.compatible_with(offered_capabilities):
            return ErrorDetail(
                MODEL_VERSION,
                ErrorCode.CAPABILITY_INCOMPATIBLE,
                "client capabilities are incompatible with session",
            )
        return session.capabilities

    @staticmethod
    def _rejection(transaction, error):
        return RejectedTransaction(
            MODEL_VERSION,
            transaction.transaction_id,
            transaction.session_id,
            error,
        )

    def submit(self, transaction, fail_after_operation=None):
        if not isinstance(transaction, Transaction):
            raise TypeError("authority submit requires Transaction")
        session = self.session(transaction.session_id)
        if session is None:
            return self._rejection(
                transaction,
                ErrorDetail(MODEL_VERSION, ErrorCode.SESSION_NOT_FOUND, "session does not exist"),
            )
        semantic = transaction.semantic_json()
        previous = session.deduplication.get(transaction.transaction_id)
        if previous is not None:
            previous_semantic, previous_result = previous
            if previous_semantic == semantic:
                return previous_result
            return self._rejection(
                transaction,
                ErrorDetail(
                    MODEL_VERSION,
                    ErrorCode.DUPLICATE_CONFLICT,
                    "transaction ID conflicts with previously submitted immutable content",
                ),
            )
        if not session.capabilities.supports(transaction):
            result = self._rejection(
                transaction,
                ErrorDetail(
                    MODEL_VERSION,
                    ErrorCode.CAPABILITY_INCOMPATIBLE,
                    "transaction requires an operation outside session capability",
                ),
            )
            session.remember(transaction.transaction_id, semantic, result)
            return result

        apply_result = session.scene.apply_transaction(
            transaction, fail_after_operation=fail_after_operation
        )
        if not apply_result.success:
            result = self._rejection(transaction, apply_result.error)
            session.remember(transaction.transaction_id, semantic, result)
            return result

        accepted = AcceptedTransaction(
            MODEL_VERSION,
            session.next_sequence,
            self.authority_id,
            transaction,
        )
        session.next_sequence += 1
        session.history.append(accepted)
        session.remember(transaction.transaction_id, semantic, accepted)
        return accepted

    def resume(self, request):
        if not isinstance(request, ResumeRequest):
            raise TypeError("authority resume requires ResumeRequest")
        session = self.session(request.session_id)
        if session is None:
            return ResumeResult(
                MODEL_VERSION,
                ResumeStatus.SESSION_NOT_FOUND,
                request.session_id,
                request.after_sequence,
                0,
                0,
                (),
                ErrorDetail(MODEL_VERSION, ErrorCode.SESSION_NOT_FOUND, "session does not exist"),
            )
        earliest = session.earliest_resumable_sequence
        latest = session.latest_sequence
        if request.after_sequence < earliest:
            return ResumeResult(
                MODEL_VERSION,
                ResumeStatus.HISTORY_UNAVAILABLE,
                request.session_id,
                request.after_sequence,
                earliest,
                latest,
                (),
                ErrorDetail(
                    MODEL_VERSION,
                    ErrorCode.HISTORY_UNAVAILABLE,
                    "requested history predates bounded retention",
                ),
            )
        if request.after_sequence > latest:
            return ResumeResult(
                MODEL_VERSION,
                ResumeStatus.HISTORY_GAP,
                request.session_id,
                request.after_sequence,
                earliest,
                latest,
                (),
                ErrorDetail(
                    MODEL_VERSION,
                    ErrorCode.HISTORY_GAP,
                    "client resume point is ahead of authority history",
                ),
            )
        history = tuple(
            accepted
            for accepted in session.history
            if accepted.sequence > request.after_sequence
        )
        expected = request.after_sequence + 1
        for accepted in history:
            if accepted.sequence != expected:
                return ResumeResult(
                    MODEL_VERSION,
                    ResumeStatus.HISTORY_UNAVAILABLE,
                    request.session_id,
                    request.after_sequence,
                    earliest,
                    latest,
                    (),
                    ErrorDetail(
                        MODEL_VERSION,
                        ErrorCode.HISTORY_UNAVAILABLE,
                        "retained history is not contiguous from requested sequence",
                    ),
                )
            expected += 1
        return ResumeResult(
            MODEL_VERSION,
            ResumeStatus.OK,
            request.session_id,
            request.after_sequence,
            earliest,
            latest,
            history,
            None,
        )
