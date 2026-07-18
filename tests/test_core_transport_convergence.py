import random
import unittest

from coophou.core.authority import FakeAuthority
from coophou.core.client import ClientState, PortableClient
from coophou.core.errors import DomainError, ErrorCode
from coophou.core.models import (
    MODEL_VERSION,
    AcceptedTransaction,
    CreateSubtree,
    SubtreeConnection,
)
from coophou.core.scene import FakeScene
from coophou.core.transport import DeterministicTransport, EventKind

from core_fixtures import (
    connection,
    create_op,
    delete_tx,
    input_tx,
    parameter_tx,
    ref,
    rename_tx,
    spec,
    transaction,
    value,
)


V = MODEL_VERSION


def seeded_scene():
    scene = FakeScene.initial()
    result = scene.apply_transaction(
        transaction(
            "seed",
            create_op("source-a", "source_a"),
            create_op("source-b", "source_b"),
            create_op("target", "target"),
            author="seed-client",
        )
    )
    if not result.success:
        raise AssertionError(result.error)
    return scene


class TransportConvergenceTests(unittest.TestCase):
    def make_clients(self, initial_scene=None, history_limit=64, queue_limit=1024):
        authority = FakeAuthority(
            history_limit=history_limit,
            deduplication_limit=max(128, history_limit),
        )
        authority.create_session("session", initial_scene=initial_scene)
        transport = DeterministicTransport(authority, queue_limit=queue_limit)
        alice = PortableClient("alice", "session", initial_scene=initial_scene)
        bob = PortableClient("bob", "session", initial_scene=initial_scene)
        for client in (alice, bob):
            transport.join(client)
            transport.request_resume(client)
        transport.deliver_all()
        self.assertEqual(alice.state, ClientState.SYNCHRONIZED)
        self.assertEqual(bob.state, ClientState.SYNCHRONIZED)
        return authority, transport, alice, bob

    def assert_converged(self, authority, *clients):
        canonical = authority.session("session").scene
        for client in clients:
            self.assertTrue(client.confirmed_scene.semantically_equal(canonical))
            self.assertTrue(client.working_scene.semantically_equal(canonical))
            self.assertEqual(client.state, ClientState.SYNCHRONIZED)

    def test_lost_submission_is_retried_with_same_id_after_reconnect(self):
        authority, transport, alice, bob = self.make_clients()
        tx = transaction("stable-id", create_op("node-a", "node_a"), author="alice")
        alice.submit_local(tx)
        transport.submit(alice, tx)
        transport.drop()
        alice.disconnect()
        transport.join(alice)
        transport.request_resume(alice)
        transport.deliver_all()
        self.assertEqual(alice.pending_transaction_ids, ("stable-id",))
        retried = transport.retry_pending(alice)
        self.assertEqual(retried[0].payload.transaction_id, "stable-id")
        self.assertEqual(alice.pending[0].attempts, 2)
        transport.deliver_all()
        self.assert_converged(authority, alice, bob)

    def test_disconnect_before_submit_delivery_can_drop_old_generation_work(self):
        authority, transport, alice, bob = self.make_clients()
        tx = transaction("not-delivered", create_op("node-a", "node_a"), author="alice")
        alice.submit_local(tx)
        transport.submit(alice, tx)
        dropped = transport.disconnect(alice, drop_queued=True)
        self.assertEqual(len(dropped), 1)
        self.assertEqual(authority.session("session").latest_sequence, 0)
        transport.reconnect(alice)
        transport.request_resume(alice)
        transport.deliver_all()
        transport.retry_pending(alice)
        transport.deliver_all()
        self.assert_converged(authority, alice, bob)

    def test_duplicate_submission_and_canonical_delivery_are_safe(self):
        authority, transport, alice, bob = self.make_clients()
        tx = transaction("duplicate", create_op("node-a", "node_a"), author="alice")
        alice.submit_local(tx)
        transport.submit(alice, tx)
        transport.duplicate()
        transport.deliver_all()
        self.assertEqual(authority.session("session").latest_sequence, 1)
        self.assert_converged(authority, alice, bob)

    def test_lost_acceptance_response_is_repaired_by_canonical_delivery(self):
        authority, transport, alice, bob = self.make_clients()
        tx = transaction("tx", create_op("node-a", "node_a"), author="alice")
        alice.submit_local(tx)
        transport.submit(alice, tx)
        transport.deliver_next(EventKind.SUBMIT)
        dropped = transport.deliver_next(EventKind.RESPONSE)
        self.assertIsNotNone(dropped)
        transport.deliver_all()
        self.assert_converged(authority, alice, bob)

    def test_reconnect_after_acceptance_before_receipt_resumes_history(self):
        authority, transport, alice, bob = self.make_clients()
        tx = transaction("accepted-unseen", create_op("node-a", "node_a"), author="alice")
        alice.submit_local(tx)
        transport.submit(alice, tx)
        transport.deliver_next(EventKind.SUBMIT)
        transport.queue = [event for event in transport.queue if event.client_id != "alice"]
        alice.disconnect()
        transport.join(alice)
        transport.request_resume(alice)
        transport.deliver_all()
        self.assert_converged(authority, alice, bob)

    def test_disconnect_after_submit_before_queued_response_ignores_response(self):
        authority, transport, alice, bob = self.make_clients()
        tx = transaction("response-unseen", create_op("node-a", "node_a"), author="alice")
        alice.submit_local(tx)
        transport.submit(alice, tx)
        transport.deliver_next(EventKind.SUBMIT)
        old_generation = alice.connection_generation
        transport.disconnect(alice)
        transport.deliver_next(EventKind.RESPONSE, "alice")
        self.assertEqual(alice.connection_generation, old_generation)
        self.assertEqual(alice.pending_transaction_ids, ("response-unseen",))
        transport.reconnect(alice)
        transport.request_resume(alice)
        transport.deliver_all()
        self.assert_converged(authority, alice, bob)

    def test_out_of_order_canonical_broadcasts_wait_for_gap(self):
        authority, transport, alice, bob = self.make_clients()
        first = transaction("first", create_op("node-a", "node_a"), author="alice")
        second = transaction("second", create_op("node-b", "node_b"), author="bob")
        alice.submit_local(first)
        bob.submit_local(second)
        transport.submit(alice, first)
        transport.submit(bob, second)
        transport.deliver_next(EventKind.SUBMIT)
        transport.deliver_next(EventKind.SUBMIT)
        canonical_for_bob = [
            (index, event)
            for index, event in enumerate(transport.queue)
            if event.kind is EventKind.CANONICAL and event.client_id == "bob"
        ]
        seq2_index = next(index for index, event in canonical_for_bob if event.payload.sequence == 2)
        transport._dispatch(transport.queue.pop(seq2_index))
        self.assertEqual(bob.state, ClientState.CATCHING_UP)
        self.assertEqual(bob.last_confirmed, 0)
        transport.deliver_all()
        self.assert_converged(authority, alice, bob)

    def test_competing_rename_converges_when_rejection_precedes_winner_broadcast(self):
        initial = seeded_scene()
        authority, transport, alice, bob = self.make_clients(initial)
        alice_tx = rename_tx("alice-rename", "target", "target", "alice_name", author="alice")
        bob_tx = rename_tx("bob-rename", "target", "target", "bob_name", author="bob")
        alice.submit_local(alice_tx)
        bob.submit_local(bob_tx)
        transport.submit(alice, alice_tx)
        transport.submit(bob, bob_tx)
        transport.deliver_next(EventKind.SUBMIT, "alice")
        transport.deliver_next(EventKind.SUBMIT, "bob")
        transport.deliver_next(EventKind.RESPONSE, "bob")
        transport.deliver_all()
        self.assertEqual(authority.session("session").scene.path("target"), "/alice_name")
        self.assert_converged(authority, alice, bob)

    def test_competing_rename_adverse_delivery_stops_for_reconciliation(self):
        initial = seeded_scene()
        authority, transport, alice, bob = self.make_clients(initial)
        alice_tx = rename_tx("alice-rename", "target", "target", "alice_name", author="alice")
        bob_tx = rename_tx("bob-rename", "target", "target", "bob_name", author="bob")
        alice.submit_local(alice_tx)
        bob.submit_local(bob_tx)
        transport.submit(alice, alice_tx)
        transport.submit(bob, bob_tx)
        transport.deliver_next(EventKind.SUBMIT, "alice")
        transport.deliver_next(EventKind.SUBMIT, "bob")
        transport.deliver_next(EventKind.CANONICAL, "bob")
        self.assertEqual(bob.state, ClientState.RECONCILIATION_REQUIRED)
        self.assertEqual(bob.last_confirmed, 1)
        self.assertEqual(bob.pending_transaction_ids, ("bob-rename",))
        self.assertTrue(alice.state is not ClientState.FATAL)
        self.assertEqual(authority.session("session").scene.path("target"), "/alice_name")

    def test_competing_set_input_has_one_winner_and_converges(self):
        initial = seeded_scene()
        authority, transport, alice, bob = self.make_clients(initial)
        alice_tx = input_tx(
            "alice-wire", "target", 0, connection("source-a"), author="alice"
        )
        bob_tx = input_tx(
            "bob-wire", "target", 0, connection("source-b"), author="bob"
        )
        alice.submit_local(alice_tx)
        bob.submit_local(bob_tx)
        transport.submit(alice, alice_tx)
        transport.submit(bob, bob_tx)
        transport.deliver_next(EventKind.SUBMIT, "bob")
        transport.deliver_next(EventKind.SUBMIT, "alice")
        transport.deliver_next(EventKind.RESPONSE, "alice")
        transport.deliver_all()
        winner = authority.session("session").scene.require_live("target").inputs[0]
        self.assertEqual(winner.source.entity_id, "source-b")
        self.assert_converged(authority, alice, bob)

    def test_valid_expected_source_rewire_converges(self):
        initial = seeded_scene()
        initial_result = initial.apply_transaction(
            input_tx(
                "seed-wire",
                "target",
                0,
                connection("source-a"),
                author="seed-client",
            )
        )
        self.assertTrue(initial_result.success)
        authority, transport, alice, bob = self.make_clients(initial)
        rewired = input_tx(
            "rewire",
            "target",
            0,
            connection("source-b"),
            connection("source-a"),
            author="alice",
        )
        alice.submit_local(rewired)
        transport.submit(alice, rewired)
        transport.deliver_all()
        winner = authority.session("session").scene.require_live("target").inputs[0]
        self.assertEqual(winner.source.entity_id, "source-b")
        self.assert_converged(authority, alice, bob)

    def test_two_clients_set_different_parameters_and_converge(self):
        initial = seeded_scene()
        authority, transport, alice, bob = self.make_clients(initial)
        alice_tx = parameter_tx(
            "alice-scale", "target", "scale", value(2.0), author="alice"
        )
        bob_tx = parameter_tx(
            "bob-offset", "target", "offset", value(3.0), author="bob"
        )
        for client, tx in ((alice, alice_tx), (bob, bob_tx)):
            client.submit_local(tx)
            transport.submit(client, tx)
        transport.deliver_all()
        parameters = authority.session("session").scene.require_live("target").parameters
        self.assertEqual(parameters["scale"], value(2.0))
        self.assertEqual(parameters["offset"], value(3.0))
        self.assert_converged(authority, alice, bob)

    def test_two_clients_set_same_parameter_in_canonical_order(self):
        initial = seeded_scene()
        authority, transport, alice, bob = self.make_clients(initial)
        alice_tx = parameter_tx(
            "alice-scale", "target", "scale", value(2.0), author="alice"
        )
        bob_tx = parameter_tx(
            "bob-scale", "target", "scale", value(7.0), author="bob"
        )
        alice.submit_local(alice_tx)
        bob.submit_local(bob_tx)
        transport.submit(alice, alice_tx)
        transport.submit(bob, bob_tx)
        transport.deliver_all()
        final_value = authority.session("session").scene.require_live("target").parameters["scale"]
        self.assertEqual(final_value, value(7.0))
        self.assert_converged(authority, alice, bob)

    def test_create_then_remote_parameter_edit_uses_entity_id(self):
        authority, transport, alice, bob = self.make_clients()
        created = transaction("create", create_op("created", "created"), author="alice")
        alice.submit_local(created)
        transport.submit(alice, created)
        transport.deliver_all()
        edited = parameter_tx("edit", "created", "scale", value(4.0), author="bob")
        bob.submit_local(edited)
        transport.submit(bob, edited)
        transport.deliver_all()
        self.assertEqual(
            authority.session("session").scene.require_live("created").parameters["scale"],
            value(4.0),
        )
        self.assert_converged(authority, alice, bob)

    def test_create_connected_copied_subtree_converges_atomically(self):
        authority, transport, alice, bob = self.make_clients()
        copied = CreateSubtree(
            V,
            "op-copy",
            (spec("copy-a", "copy_a"), spec("copy-b", "copy_b", "copy-a")),
            (SubtreeConnection(V, ref("copy-b"), 0, connection("copy-a")),),
        )
        tx = transaction("copy", copied, author="alice")
        alice.submit_local(tx)
        transport.submit(alice, tx)
        transport.deliver_all()
        canonical = authority.session("session").scene
        self.assertEqual(canonical.path("copy-b"), "/copy_a/copy_b")
        self.assertEqual(
            canonical.require_live("copy-b").inputs[0].source.entity_id, "copy-a"
        )
        self.assertEqual(authority.session("session").latest_sequence, 1)
        self.assert_converged(authority, alice, bob)

    def test_rename_then_remote_edit_resolves_by_identity_not_old_path(self):
        initial = seeded_scene()
        authority, transport, alice, bob = self.make_clients(initial)
        renamed = rename_tx(
            "rename", "target", "target", "renamed_target", author="alice"
        )
        alice.submit_local(renamed)
        transport.submit(alice, renamed)
        transport.deliver_all()
        edited = parameter_tx("edit", "target", "scale", value(9.0), author="bob")
        bob.submit_local(edited)
        transport.submit(bob, edited)
        transport.deliver_all()
        canonical = authority.session("session").scene
        self.assertEqual(canonical.path("target"), "/renamed_target")
        self.assertEqual(canonical.require_live("target").parameters["scale"], value(9.0))
        self.assert_converged(authority, alice, bob)

    def test_delete_then_reuse_old_path_does_not_resurrect_identity(self):
        initial = seeded_scene()
        authority, transport, alice, bob = self.make_clients(initial)
        deleted = delete_tx("delete", "target", ("target",), author="alice")
        alice.submit_local(deleted)
        transport.submit(alice, deleted)
        transport.deliver_all()
        replacement = transaction(
            "replacement", create_op("replacement", "target"), author="bob"
        )
        bob.submit_local(replacement)
        transport.submit(bob, replacement)
        transport.deliver_all()
        canonical = authority.session("session").scene
        self.assertIn("target", canonical.tombstones)
        self.assertEqual(canonical.path("replacement"), "/target")
        stale = rename_tx("stale", "target", "target", "wrong", author="alice")
        rejection = authority.submit(stale)
        self.assertEqual(rejection.error.code, ErrorCode.ENTITY_DELETED)
        self.assertEqual(canonical.path("replacement"), "/target")
        self.assert_converged(authority, alice, bob)

    def test_connect_then_delete_source_removes_dangling_wire_everywhere(self):
        initial = seeded_scene()
        authority, transport, alice, bob = self.make_clients(initial)
        connected = input_tx(
            "connect", "target", 0, connection("source-a"), author="alice"
        )
        alice.submit_local(connected)
        transport.submit(alice, connected)
        transport.deliver_all()
        deleted = delete_tx("delete", "source-a", ("source-a",), author="bob")
        bob.submit_local(deleted)
        transport.submit(bob, deleted)
        transport.deliver_all()
        self.assertNotIn(
            0, authority.session("session").scene.require_live("target").inputs
        )
        self.assert_converged(authority, alice, bob)

    def test_disconnect_during_reordered_delivery_ignores_stale_generation(self):
        authority, transport, alice, bob = self.make_clients()
        tx = transaction("tx", create_op("node-a", "node_a"), author="bob")
        bob.submit_local(tx)
        transport.submit(bob, tx)
        transport.deliver_next(EventKind.SUBMIT)
        stale = next(
            event
            for event in transport.queue
            if event.kind is EventKind.CANONICAL and event.client_id == "alice"
        )
        transport.queue.remove(stale)
        alice.disconnect()
        transport.join(alice)
        transport._dispatch(stale)
        self.assertEqual(alice.last_confirmed, 0)
        transport.request_resume(alice)
        transport.deliver_all()
        self.assert_converged(authority, alice, bob)

    def test_history_unavailable_enters_reconciliation(self):
        authority, transport, alice, bob = self.make_clients(history_limit=1)
        alice.disconnect()
        for index in range(2):
            tx = transaction(
                f"bob-{index}", create_op(f"node-{index}", f"node_{index}"), author="bob"
            )
            bob.submit_local(tx)
            transport.submit(bob, tx)
            transport.deliver_all()
        transport.join(alice)
        transport.request_resume(alice)
        transport.deliver_all()
        self.assertEqual(alice.state, ClientState.RECONCILIATION_REQUIRED)
        self.assertEqual(alice.last_error.code, ErrorCode.HISTORY_UNAVAILABLE)

    def test_cross_session_broadcast_isolation(self):
        authority = FakeAuthority()
        authority.create_session("session")
        authority.create_session("other")
        transport = DeterministicTransport(authority)
        alice = PortableClient("alice", "session")
        bob = PortableClient("bob", "other")
        for client in (alice, bob):
            transport.join(client)
            transport.request_resume(client)
        transport.deliver_all()
        tx = transaction("tx", create_op("node-a", "node_a"), author="alice")
        alice.submit_local(tx)
        transport.submit(alice, tx)
        transport.deliver_all()
        self.assertIn("node-a", alice.working_scene.entities)
        self.assertNotIn("node-a", bob.working_scene.entities)
        self.assertEqual(bob.last_confirmed, 0)

    def test_transport_queue_bound_and_cleanup_are_deterministic(self):
        authority = FakeAuthority()
        authority.create_session("session")
        transport = DeterministicTransport(authority, queue_limit=1)
        client = PortableClient("alice", "session")
        transport.join(client)
        transport.request_resume(client)
        with self.assertRaises(DomainError) as caught:
            transport.request_resume(client)
        self.assertEqual(caught.exception.detail.code, ErrorCode.QUEUE_OVERFLOW)
        transport.close()
        transport.close()
        self.assertEqual(transport.queue, [])
        self.assertEqual(transport.clients, {})

    def test_randomized_non_conflicting_convergence_with_duplicates_and_reordering(self):
        for seed in range(20):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                authority, transport, alice, bob = self.make_clients(queue_limit=4096)
                submissions = []
                for index in range(12):
                    client = alice if index % 2 == 0 else bob
                    tx = transaction(
                        f"tx-{seed}-{index}",
                        create_op(f"node-{seed}-{index}", f"node_{seed}_{index}"),
                        author=client.client_id,
                    )
                    client.submit_local(tx)
                    submissions.append(transport.submit(client, tx))
                rng.shuffle(transport.queue)
                duplicate_count = 0
                while any(event.kind is EventKind.SUBMIT for event in transport.queue):
                    event = transport.deliver_next(EventKind.SUBMIT)
                    if rng.random() < 0.2 and duplicate_count < 2:
                        authority.submit(event.payload)
                        duplicate_count += 1
                rng.shuffle(transport.queue)
                transport.deliver_all()
                self.assertEqual(authority.session("session").latest_sequence, 12)
                self.assert_converged(authority, alice, bob)


if __name__ == "__main__":
    unittest.main()
