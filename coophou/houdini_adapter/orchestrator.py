"""Single-process Phase 3 orchestration around the native adapter."""

from __future__ import annotations

import uuid

from coophou.core import (
    AcceptedTransaction,
    CapabilitySet,
    FakeAuthority,
    FakeScene,
    MODEL_VERSION,
    PortableClient,
    Transaction,
)
from coophou.core.models import operation_from_dict

from .bridge import NativeBridge, NativeBridgeError


class SingleProcessOrchestrator:
    """Converts native candidates to frozen Phase 2 records.

    Local changes are already visible in Houdini, so their accepted canonical
    echo updates only the portable projections. Remote accepted transactions
    are sent through the native application gateway explicitly.
    """

    def __init__(
        self,
        bridge=None,
        *,
        client_id="houdini-client",
        session_id="single-process-session",
        authority_id="single-process-authority",
        initial_scene=None,
        id_factory=None,
    ):
        self.bridge = bridge or NativeBridge()
        self.client_id = client_id
        self.session_id = session_id
        self._id_factory = id_factory or (lambda prefix: f"{prefix}-{uuid.uuid4()}")
        scene = (initial_scene or FakeScene.initial()).clone()
        self.authority = FakeAuthority(authority_id=authority_id)
        self.authority.create_session(session_id, initial_scene=scene)
        self.client = PortableClient(client_id, session_id, initial_scene=scene)
        generation = self.client.begin_join()
        accepted = self.authority.join(session_id, CapabilitySet.v1())
        if not self.client.accept_join(accepted, generation):
            raise RuntimeError("portable client could not join the single-process authority")
        resume = self.authority.resume(self.client.resume_request())
        if not self.client.receive_resume_result(resume, generation):
            raise RuntimeError("portable client could not complete initial resume")
        self.connection_generation = generation

    def _id(self, prefix):
        value = self._id_factory(prefix)
        if not isinstance(value, str):
            raise TypeError("id_factory must return a string")
        return value

    def transaction_from_change_set(self, record):
        if record.get("bridge_schema_version") != 1:
            raise NativeBridgeError(
                "BRIDGE_UNSUPPORTED_VERSION", "capture record has an unsupported version"
            )
        if record.get("record_type") != "capture.change_set":
            raise ValueError("record is not a native capture change set")
        candidates = record.get("operations")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("capture change set has no operation candidates")
        operations = []
        for candidate in candidates:
            if not isinstance(candidate, dict) or "operation_id" in candidate:
                raise ValueError("native operation candidate shape is invalid")
            operations.append(
                operation_from_dict(
                    {**candidate, "operation_id": self._id("operation")}
                )
            )
        required = tuple(dict.fromkeys(operation.operation_type for operation in operations))
        return Transaction(
            MODEL_VERSION,
            self._id("transaction"),
            self.client_id,
            self.session_id,
            tuple(operations),
            "Houdini local edit",
            required,
        )

    def capture_local(self, max_count=64):
        self.bridge.flush_settle()
        drained = self.bridge.drain_capture(max_count=max_count)
        accepted_transactions = []
        adapter_records = []
        for record in drained["records"]:
            if record.get("record_type") != "capture.change_set":
                adapter_records.append(record)
                continue
            transaction = self.transaction_from_change_set(record)
            self.client.submit_local(transaction)
            result = self.authority.submit(transaction)
            self.client.receive_submission_result(result, self.connection_generation)
            if not isinstance(result, AcceptedTransaction):
                raise NativeBridgeError(
                    "LOCAL_TRANSACTION_REJECTED",
                    result.error.message,
                    dict(result.error.context),
                )
            if not self.client.receive_canonical(result, self.connection_generation):
                raise NativeBridgeError(
                    "PORTABLE_CONFIRMATION_FAILED",
                    "accepted local transaction did not confirm",
                )
            accepted_transactions.append(result)
        return accepted_transactions, adapter_records, drained["remaining"]

    def apply_remote(self, transaction, scene_generation, correlation_id=None):
        if not isinstance(transaction, Transaction):
            raise TypeError("remote application requires a Transaction")
        correlation_id = correlation_id or self._id("correlation")
        self.bridge.enqueue_apply(transaction, scene_generation, correlation_id)
        drained = self.bridge.drain_apply(
            max_transactions=1,
            max_operations=len(transaction.operations),
        )
        results = drained["results"]
        if len(results) != 1:
            raise NativeBridgeError(
                "APPLICATION_NOT_DRAINED", "native gateway did not return one result"
            )
        result = results[0]
        if not result.get("ok"):
            error = result.get("error") or {}
            raise NativeBridgeError(
                error.get("code", "APPLICATION_FAILED"),
                error.get("message", "native application failed"),
                error.get("context"),
            )
        return result["payload"]
