"""Deterministically controlled in-memory transport and fault surface."""

from dataclasses import dataclass
from enum import Enum

from .errors import DomainError, ErrorCode
from .models import AcceptedTransaction, Transaction


class EventKind(str, Enum):
    SUBMIT = "SUBMIT"
    RESPONSE = "RESPONSE"
    CANONICAL = "CANONICAL"
    RESUME_REQUEST = "RESUME_REQUEST"
    RESUME_RESPONSE = "RESUME_RESPONSE"


@dataclass(frozen=True)
class TransportEvent:
    event_id: int
    kind: EventKind
    client_id: str
    session_id: str
    connection_generation: int
    payload: object
    fail_after_operation: int | None = None


class DeterministicTransport:
    """A manually delivered queue: tests choose every loss/reorder/duplicate."""

    def __init__(self, authority, queue_limit=1024):
        if queue_limit < 1:
            raise ValueError("transport queue limit must be positive")
        self.authority = authority
        self.queue_limit = queue_limit
        self.clients = {}
        self.queue = []
        self._next_event_id = 1
        self.closed = False

    def register(self, client):
        if self.closed:
            raise RuntimeError("transport is closed")
        existing = self.clients.get(client.client_id)
        if existing is not None and existing is not client:
            raise ValueError("client ID is already registered")
        self.clients[client.client_id] = client

    def unregister(self, client_id):
        self.clients.pop(client_id, None)

    def disconnect(self, client, drop_queued=False):
        generation = client.connection_generation
        client.disconnect()
        if drop_queued:
            dropped = tuple(
                event
                for event in self.queue
                if event.client_id == client.client_id
                and event.connection_generation == generation
            )
            self.queue = [event for event in self.queue if event not in dropped]
            return dropped
        return ()

    def reconnect(self, client):
        return self.join(client)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.queue.clear()
        self.clients.clear()

    def _enqueue(
        self,
        kind,
        client_id,
        session_id,
        connection_generation,
        payload,
        fail_after_operation=None,
    ):
        if self.closed:
            raise RuntimeError("transport is closed")
        if len(self.queue) >= self.queue_limit:
            raise DomainError(ErrorCode.QUEUE_OVERFLOW, "transport event queue is full")
        event = TransportEvent(
            self._next_event_id,
            kind,
            client_id,
            session_id,
            connection_generation,
            payload,
            fail_after_operation,
        )
        self._next_event_id += 1
        self.queue.append(event)
        return event

    def join(self, client):
        self.register(client)
        generation = client.begin_join()
        result = self.authority.join(client.session_id, client.capabilities)
        client.accept_join(result, generation)
        return result

    def submit(self, client, transaction, fail_after_operation=None):
        if not isinstance(transaction, Transaction):
            raise TypeError("transport submission requires Transaction")
        return self._enqueue(
            EventKind.SUBMIT,
            client.client_id,
            client.session_id,
            client.connection_generation,
            transaction,
            fail_after_operation,
        )

    def request_resume(self, client):
        return self._enqueue(
            EventKind.RESUME_REQUEST,
            client.client_id,
            client.session_id,
            client.connection_generation,
            client.resume_request(),
        )

    def retry_pending(self, client):
        events = []
        for transaction_id in client.pending_transaction_ids:
            record = client.mark_pending_retried(transaction_id)
            events.append(self.submit(client, record.transaction))
        return tuple(events)

    def queued_events(self):
        return tuple(self.queue)

    def duplicate(self, index=0):
        original = self.queue[index]
        return self._enqueue(
            original.kind,
            original.client_id,
            original.session_id,
            original.connection_generation,
            original.payload,
            original.fail_after_operation,
        )

    def drop(self, index=0):
        return self.queue.pop(index)

    def move(self, source_index, destination_index):
        event = self.queue.pop(source_index)
        self.queue.insert(destination_index, event)
        return event

    def _matching_index(self, kind=None, client_id=None):
        for index, event in enumerate(self.queue):
            if kind is not None and event.kind is not kind:
                continue
            if client_id is not None and event.client_id != client_id:
                continue
            return index
        return None

    def deliver_next(self, kind=None, client_id=None):
        index = self._matching_index(kind=kind, client_id=client_id)
        if index is None:
            return None
        event = self.queue.pop(index)
        self._dispatch(event)
        return event

    def deliver_all(self, limit=10000):
        delivered = []
        while self.queue:
            if len(delivered) >= limit:
                raise RuntimeError("transport delivery limit exceeded")
            delivered.append(self.deliver_next())
        return tuple(delivered)

    def _dispatch(self, event):
        if event.kind is EventKind.SUBMIT:
            result = self.authority.submit(
                event.payload, fail_after_operation=event.fail_after_operation
            )
            self._enqueue(
                EventKind.RESPONSE,
                event.client_id,
                event.session_id,
                event.connection_generation,
                result,
            )
            if isinstance(result, AcceptedTransaction):
                for client_id in sorted(self.clients):
                    client = self.clients[client_id]
                    if (
                        client.session_id == event.session_id
                        and client.transport_connected
                    ):
                        self._enqueue(
                            EventKind.CANONICAL,
                            client.client_id,
                            client.session_id,
                            client.connection_generation,
                            result,
                        )
            return
        client = self.clients.get(event.client_id)
        if client is None:
            return
        if event.kind in (
            EventKind.RESPONSE,
            EventKind.CANONICAL,
            EventKind.RESUME_RESPONSE,
        ) and not client.transport_connected:
            return
        if event.kind is EventKind.RESPONSE:
            client.receive_submission_result(event.payload, event.connection_generation)
        elif event.kind is EventKind.CANONICAL:
            client.receive_canonical(event.payload, event.connection_generation)
        elif event.kind is EventKind.RESUME_REQUEST:
            result = self.authority.resume(event.payload)
            self._enqueue(
                EventKind.RESUME_RESPONSE,
                event.client_id,
                event.session_id,
                event.connection_generation,
                result,
            )
        elif event.kind is EventKind.RESUME_RESPONSE:
            client.receive_resume_result(event.payload, event.connection_generation)
        else:
            raise RuntimeError("unknown transport event kind")
