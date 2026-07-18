import unittest

from coophou.core.authority import FakeAuthority
from coophou.core.client import ClientState, PortableClient
from coophou.core.errors import DomainError, ErrorCode
from coophou.core.models import (
    MODEL_VERSION,
    AcceptedTransaction,
    CapabilitySet,
    OperationType,
    RejectedTransaction,
    ResumeRequest,
    ResumeStatus,
)
from coophou.core.scene import FakeScene
from coophou.core.transport import DeterministicTransport, EventKind

from core_fixtures import (
    create_op,
    delete_tx,
    initial_create_tx,
    move_tx,
    rename_tx,
    transaction,
)


V = MODEL_VERSION


def scene_with_node():
    scene = FakeScene.initial()
    result = scene.apply_transaction(initial_create_tx("seed", author="seed-client"))
    if not result.success:
        raise AssertionError(result.error)
    return scene


class AuthorityTests(unittest.TestCase):
    def setUp(self):
        self.authority = FakeAuthority()
        self.authority.create_session("session")

    def test_one_sequence_per_accepted_transaction_and_rejection_does_not_advance(self):
        accepted = self.authority.submit(initial_create_tx())
        self.assertIsInstance(accepted, AcceptedTransaction)
        self.assertEqual(accepted.sequence, 1)
        rejected = self.authority.submit(
            transaction("tx-conflict", create_op("node-b", "node_a"))
        )
        self.assertIsInstance(rejected, RejectedTransaction)
        self.assertEqual(rejected.error.code, ErrorCode.NAME_CONFLICT)
        next_accepted = self.authority.submit(
            transaction("tx-next", create_op("node-c", "node_c"))
        )
        self.assertEqual(next_accepted.sequence, 2)

    def test_multi_operation_transaction_is_one_atomic_sequence(self):
        tx = transaction(
            "tx-pair",
            create_op("node-a", "node_a"),
            create_op("node-b", "node_b"),
        )
        accepted = self.authority.submit(tx)
        self.assertEqual(accepted.sequence, 1)
        self.assertEqual(len(accepted.transaction.operations), 2)
        self.assertEqual(self.authority.session("session").latest_sequence, 1)

    def test_transaction_id_retry_returns_same_result(self):
        tx = initial_create_tx()
        first = self.authority.submit(tx)
        second = self.authority.submit(tx)
        self.assertIs(first, second)
        self.assertEqual(self.authority.session("session").latest_sequence, 1)

    def test_transaction_id_reuse_with_other_content_is_rejected(self):
        self.authority.submit(initial_create_tx("same"))
        conflict = self.authority.submit(
            transaction("same", create_op("node-b", "node_b"))
        )
        self.assertEqual(conflict.error.code, ErrorCode.DUPLICATE_CONFLICT)

    def test_mid_transaction_failure_does_not_mutate_or_sequence(self):
        before = self.authority.session("session").scene.semantic_json()
        failed = self.authority.submit(
            transaction(
                "tx-pair",
                create_op("node-a", "node_a"),
                create_op("node-b", "node_b"),
            ),
            fail_after_operation=1,
        )
        self.assertIsInstance(failed, RejectedTransaction)
        self.assertEqual(failed.error.code, ErrorCode.APPLICATION_FAILED)
        session = self.authority.session("session")
        self.assertEqual(session.scene.semantic_json(), before)
        self.assertEqual(session.latest_sequence, 0)

    def test_sessions_are_isolated(self):
        self.authority.create_session("other")
        self.authority.submit(initial_create_tx())
        self.assertIn("node-a", self.authority.session("session").scene.entities)
        self.assertNotIn("node-a", self.authority.session("other").scene.entities)

    def test_narrow_session_capability_and_client_join(self):
        authority = FakeAuthority()
        create_only = CapabilitySet(V, V, V, V, (OperationType.CREATE_NODE,))
        authority.create_session("session", capabilities=create_only)
        self.assertEqual(authority.join("session", CapabilitySet.v1()), create_only)
        rejected = authority.submit(
            transaction("tx-rename", rename_tx("inner", "x", "a", "b").operations[0])
        )
        self.assertEqual(rejected.error.code, ErrorCode.CAPABILITY_INCOMPATIBLE)
        incompatible = authority.join("session", create_only)
        self.assertEqual(incompatible, create_only)

    def test_history_resume_is_contiguous_and_bounded(self):
        authority = FakeAuthority(history_limit=2, deduplication_limit=4)
        authority.create_session("session")
        for index in range(3):
            authority.submit(
                transaction(f"tx-{index}", create_op(f"node-{index}", f"node_{index}"))
            )
        unavailable = authority.resume(ResumeRequest(V, "session", "alice", 1, 0, ()))
        self.assertEqual(unavailable.status, ResumeStatus.HISTORY_UNAVAILABLE)
        resumed = authority.resume(ResumeRequest(V, "session", "alice", 1, 1, ()))
        self.assertEqual(resumed.status, ResumeStatus.OK)
        self.assertEqual(tuple(item.sequence for item in resumed.history), (2, 3))

    def test_resume_ahead_of_authority_is_gap(self):
        result = self.authority.resume(
            ResumeRequest(V, "session", "alice", 1, 9, ())
        )
        self.assertEqual(result.status, ResumeStatus.HISTORY_GAP)

    def test_resume_at_current_head_is_an_empty_success(self):
        self.authority.submit(initial_create_tx())
        result = self.authority.resume(
            ResumeRequest(V, "session", "alice", 1, 1, ())
        )
        self.assertEqual(result.status, ResumeStatus.OK)
        self.assertEqual(result.history, ())
        self.assertEqual(result.latest_sequence, 1)

    def test_runtime_owner_identifiers_are_validated(self):
        with self.assertRaises(DomainError):
            FakeAuthority(authority_id="../../authority")
        with self.assertRaises(DomainError):
            self.authority.create_session("invalid/session")
        with self.assertRaises(DomainError):
            PortableClient("invalid client", "session")


class ClientTests(unittest.TestCase):
    def make_system(self, initial_scene=None, **client_options):
        authority = FakeAuthority(history_limit=8, deduplication_limit=16)
        authority.create_session("session", initial_scene=initial_scene)
        client = PortableClient(
            "alice", "session", initial_scene=initial_scene, **client_options
        )
        transport = DeterministicTransport(authority)
        transport.join(client)
        return authority, client, transport

    def synchronize(self, client, transport):
        transport.request_resume(client)
        transport.deliver_all()
        self.assertEqual(client.state, ClientState.SYNCHRONIZED)

    def test_connected_is_not_synchronized_until_resume_completes(self):
        _, client, transport = self.make_system()
        self.assertTrue(client.transport_connected)
        self.assertEqual(client.state, ClientState.CATCHING_UP)
        self.assertFalse(client.is_synchronized)
        self.synchronize(client, transport)
        self.assertTrue(client.is_synchronized)

    def test_optimistic_submit_then_own_canonical_rebuilds_without_double_apply(self):
        authority, client, transport = self.make_system()
        self.synchronize(client, transport)
        tx = initial_create_tx(author="alice")
        client.submit_local(tx)
        self.assertIn("node-a", client.working_scene.entities)
        self.assertNotIn("node-a", client.confirmed_scene.entities)
        self.assertEqual(client.state, ClientState.DEGRADED)
        transport.submit(client, tx)
        transport.deliver_all()
        self.assertEqual(client.pending, [])
        self.assertIn("node-a", client.confirmed_scene.entities)
        self.assertTrue(client.confirmed_scene.semantically_equal(client.working_scene))
        self.assertEqual(client.last_confirmed, 1)
        self.assertEqual(client.state, ClientState.SYNCHRONIZED)
        self.assertTrue(client.confirmed_scene.semantically_equal(authority.session("session").scene))

    def test_rejection_removes_only_matching_pending_and_rebuilds(self):
        initial = scene_with_node()
        authority, client, transport = self.make_system(initial)
        self.synchronize(client, transport)
        remote = move_tx("remote", "node-a", (0.0, 0.0), (5.0, 5.0), author="bob")
        accepted_remote = authority.submit(remote)
        stale = move_tx("stale", "node-a", (0.0, 0.0), (2.0, 2.0), author="alice")
        later = transaction("later", create_op("node-b", "node_b"), author="alice")
        client.submit_local(stale)
        client.submit_local(later)
        rejection = authority.submit(stale)
        self.assertIsInstance(rejection, RejectedTransaction)
        client.receive_submission_result(rejection, client.connection_generation)
        self.assertEqual(client.pending_transaction_ids, ("later",))
        self.assertIn("node-b", client.working_scene.entities)
        self.assertEqual(client.working_scene.require_live("node-a").position, (0.0, 0.0))
        client.receive_canonical(accepted_remote, client.connection_generation)
        self.assertEqual(client.working_scene.require_live("node-a").position, (5.0, 5.0))
        self.assertIn("node-b", client.working_scene.entities)

    def test_gap_blocks_advancement_then_drains_in_order(self):
        _, client, transport = self.make_system()
        self.synchronize(client, transport)
        first = AcceptedTransaction(V, 1, "authority", initial_create_tx("tx-1", author="bob"))
        second = AcceptedTransaction(
            V, 2, "authority", rename_tx("tx-2", "node-a", "node_a", "renamed", author="bob")
        )
        self.assertFalse(client.receive_canonical(second, client.connection_generation))
        self.assertEqual(client.last_confirmed, 0)
        self.assertEqual(client.state, ClientState.CATCHING_UP)
        self.assertTrue(client.receive_canonical(first, client.connection_generation))
        self.assertEqual(client.last_confirmed, 2)
        self.assertEqual(client.working_scene.path("node-a"), "/renamed")
        self.assertEqual(client.state, ClientState.SYNCHRONIZED)

    def test_duplicate_delivery_is_safe_but_sequence_conflict_is_fatal(self):
        _, client, transport = self.make_system()
        self.synchronize(client, transport)
        first = AcceptedTransaction(V, 1, "authority", initial_create_tx("tx-1", author="bob"))
        self.assertTrue(client.receive_canonical(first, client.connection_generation))
        self.assertTrue(client.receive_canonical(first, client.connection_generation))
        conflict = AcceptedTransaction(
            V,
            1,
            "authority",
            transaction("different", create_op("node-b", "node_b"), author="bob"),
        )
        self.assertFalse(client.receive_canonical(conflict, client.connection_generation))
        self.assertEqual(client.state, ClientState.FATAL)
        self.assertEqual(client.last_error.code, ErrorCode.SEQUENCE_CONTRADICTION)

    def test_one_transaction_id_at_two_sequences_is_fatal(self):
        _, client, transport = self.make_system()
        self.synchronize(client, transport)
        tx = initial_create_tx("tx-1", author="bob")
        first = AcceptedTransaction(V, 1, "authority", tx)
        second = AcceptedTransaction(V, 2, "authority", tx)
        self.assertTrue(client.receive_canonical(first, client.connection_generation))
        self.assertFalse(client.receive_canonical(second, client.connection_generation))
        self.assertEqual(client.state, ClientState.FATAL)
        self.assertEqual(client.last_error.code, ErrorCode.SEQUENCE_CONTRADICTION)

    def test_pending_invalid_after_remote_apply_requires_reconciliation(self):
        initial = scene_with_node()
        _, client, transport = self.make_system(initial)
        self.synchronize(client, transport)
        pending = rename_tx("pending", "node-a", "node_a", "mine", author="alice")
        client.submit_local(pending)
        deleted = AcceptedTransaction(
            V,
            1,
            "authority",
            delete_tx("remote-delete", "node-a", ("node-a",), author="bob"),
        )
        self.assertFalse(client.receive_canonical(deleted, client.connection_generation))
        self.assertEqual(client.state, ClientState.RECONCILIATION_REQUIRED)
        self.assertEqual(client.pending_transaction_ids, ("pending",))
        self.assertIn("node-a", client.working_scene.entities)
        self.assertIn("node-a", client.confirmed_scene.tombstones)

    def test_failed_canonical_application_does_not_advance_sequences(self):
        _, client, transport = self.make_system()
        self.synchronize(client, transport)
        invalid = AcceptedTransaction(
            V,
            1,
            "authority",
            rename_tx("missing", "missing-node", "old", "new", author="bob"),
        )
        self.assertFalse(client.receive_canonical(invalid, client.connection_generation))
        self.assertEqual(client.last_confirmed, 0)
        self.assertEqual(client.last_applied, 0)
        self.assertEqual(client.state, ClientState.RECONCILIATION_REQUIRED)

    def test_stale_generation_deliveries_are_ignored(self):
        _, client, transport = self.make_system()
        old_generation = client.connection_generation
        client.disconnect()
        client.begin_join()
        accepted = AcceptedTransaction(V, 1, "authority", initial_create_tx(author="bob"))
        self.assertFalse(client.receive_canonical(accepted, old_generation))
        self.assertEqual(client.last_confirmed, 0)

    def test_pending_and_gap_bounds_fail_closed(self):
        _, client, transport = self.make_system(pending_limit=1, gap_limit=1)
        self.synchronize(client, transport)
        client.submit_local(initial_create_tx("pending", author="alice"))
        with self.assertRaises(DomainError):
            client.submit_local(
                transaction("overflow", create_op("node-b", "node_b"), author="alice")
            )
        self.assertEqual(client.state, ClientState.RECONCILIATION_REQUIRED)

        _, other, other_transport = self.make_system(pending_limit=1, gap_limit=1)
        self.synchronize(other, other_transport)
        two = AcceptedTransaction(V, 2, "authority", initial_create_tx("two", author="bob"))
        three = AcceptedTransaction(
            V,
            3,
            "authority",
            transaction("three", create_op("node-b", "node_b"), author="bob"),
        )
        other.receive_canonical(two, other.connection_generation)
        other.receive_canonical(three, other.connection_generation)
        self.assertEqual(other.state, ClientState.RECONCILIATION_REQUIRED)

    def test_reconnect_resume_preserves_pending_ids_and_attempt_count(self):
        authority, client, transport = self.make_system()
        self.synchronize(client, transport)
        tx = initial_create_tx("stable-id", author="alice")
        client.submit_local(tx)
        transport.submit(client, tx)
        transport.deliver_next(EventKind.SUBMIT)
        transport.queue.clear()
        client.disconnect()
        transport.join(client)
        transport.request_resume(client)
        transport.deliver_all()
        self.assertEqual(client.pending, [])
        self.assertEqual(client.last_confirmed, 1)
        self.assertEqual(client.state, ClientState.SYNCHRONIZED)
        self.assertTrue(client.confirmed_scene.semantically_equal(authority.session("session").scene))

    def test_offline_edits_are_disallowed(self):
        _, client, _ = self.make_system()
        client.disconnect()
        with self.assertRaises(DomainError):
            client.submit_local(initial_create_tx(author="alice"))


if __name__ == "__main__":
    unittest.main()
