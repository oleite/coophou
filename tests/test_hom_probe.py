import tempfile
import unittest

from coophou.client.sender import ClientSender
from coophou.probe.trace import (
    TRACE_VERSION,
    TraceWriter,
    base_record,
    make_runtime_metadata,
    remote_application_suppression,
    suppression_snapshot,
    validate_record,
)


class FakeNodeEventType:
    BeingDeleted = "nodeEventType.BeingDeleted"
    NameChanged = "nodeEventType.NameChanged"
    FlagChanged = "nodeEventType.FlagChanged"
    AppearanceChanged = "nodeEventType.AppearanceChanged"
    PositionChanged = "nodeEventType.PositionChanged"
    InputRewired = "nodeEventType.InputRewired"
    ParmTupleChanged = "nodeEventType.ParmTupleChanged"
    ChildCreated = "nodeEventType.ChildCreated"
    ChildDeleted = "nodeEventType.ChildDeleted"
    ChildReordered = "nodeEventType.ChildReordered"


class FakeNode:
    next_id = 1

    def __init__(self, path, parent=None):
        self._path = path
        self._parent = parent
        self.children = []
        self.callbacks = []
        self.valid = True
        self._session_id = FakeNode.next_id
        FakeNode.next_id += 1
        if parent is not None:
            parent.children.append(self)

    def path(self):
        if not self.valid:
            raise RuntimeError("deleted")
        return self._path

    def parent(self):
        return self._parent

    def sessionId(self):
        return self._session_id

    def userData(self, key):
        return "entity-1" if key == "coophou.entity_id" else None

    def isEditableInsideLockedHDA(self):
        return True

    def allNodes(self):
        result = []
        todo = list(self.children)
        while todo:
            node = todo.pop(0)
            result.append(node)
            todo.extend(node.children)
        return result

    def addEventCallback(self, event_types, callback):
        self.callbacks.append((tuple(event_types), callback))

    def removeEventCallback(self, event_types, callback):
        registration = (tuple(event_types), callback)
        if registration in self.callbacks:
            self.callbacks.remove(registration)


class FakeUI:
    def __init__(self):
        self.callbacks = []

    def addEventLoopCallback(self, callback):
        self.callbacks.append(callback)

    def removeEventLoopCallback(self, callback):
        self.callbacks.remove(callback)


class FakeHipFile:
    def __init__(self):
        self.callbacks = []

    def addEventCallback(self, callback):
        self.callbacks.append(callback)

    def removeEventCallback(self, callback):
        self.callbacks.remove(callback)


class FakeHou:
    nodeEventType = FakeNodeEventType

    def __init__(self):
        self.ui = FakeUI()
        self.hipFile = FakeHipFile()
        self._root = FakeNode("/")
        self.obj = FakeNode("/obj", self._root)

    def root(self):
        return self._root

    def nodeBySessionId(self, session_id):
        for node in (self._root, *self._root.allNodes()):
            if node.sessionId() == session_id and node.valid:
                return node
        return None

    def applicationVersion(self):
        return (21, 0, 729)

    def applicationVersionString(self):
        return "21.0.729"


class HOMProbeTests(unittest.TestCase):
    def setUp(self):
        self.hou = FakeHou()
        self.writer = TraceWriter()
        self.probe = ClientSender(
            hou_module=self.hou,
            writer=self.writer,
            scenario="unit_test",
        )

    def tearDown(self):
        self.probe.stopWatcher()

    def test_start_stop_restart_is_idempotent_and_owned(self):
        foreign_loop = lambda: None
        foreign_node = lambda **kwargs: None
        self.hou.ui.callbacks.append(foreign_loop)
        self.hou.obj.callbacks.append((("foreign",), foreign_node))

        self.assertTrue(self.probe.startWatcher())
        self.assertTrue(self.probe.startWatcher())
        self.assertEqual(self.hou.ui.callbacks.count(self.probe._event_loop_callback), 1)
        self.assertEqual(len(self.hou.obj.callbacks), 2)

        self.assertTrue(self.probe.stopWatcher())
        self.assertTrue(self.probe.stopWatcher())
        self.assertIn(foreign_loop, self.hou.ui.callbacks)
        self.assertIn((("foreign",), foreign_node), self.hou.obj.callbacks)

        self.assertTrue(self.probe.startWatcher())
        self.assertEqual(self.hou.ui.callbacks.count(self.probe._event_loop_callback), 1)

    def test_deletion_snapshot_survives_object_invalidation(self):
        node = FakeNode("/obj/to_delete", self.hou.obj)
        self.probe.startWatcher()
        self.probe.callback(node=node, event_type=FakeNodeEventType.BeingDeleted)
        node.valid = False
        self.probe.processEvents()

        deletion = [record for record in self.writer.records if record["event"] == "BeingDeleted"]
        self.assertEqual(len(deletion), 1)
        self.assertEqual(deletion[0]["node_path"], "/obj/to_delete")
        self.assertEqual(deletion[0]["entity_id"], "entity-1")

    def test_bulk_parameter_event_is_explicit(self):
        self.probe.startWatcher()
        self.probe.callback(
            node=self.hou.obj,
            event_type=FakeNodeEventType.ParmTupleChanged,
            parm_tuple=None,
        )
        self.probe.processEvents()
        record = self.writer.records[-1]
        self.assertEqual(record["payload"]["parameter_scope"], "bulk_or_ambiguous")
        self.assertIsNone(record["payload"]["raw_values"])

    def test_scene_generation_changes_after_scene_replacement(self):
        self.probe.startWatcher()
        self.probe.hipFileCallback("hipFileEventType.BeforeLoad")
        before = self.probe.scene_generation
        self.probe.hipFileCallback("hipFileEventType.AfterLoad")
        self.assertEqual(self.probe.scene_generation, before + 1)
        self.probe.processEvents()
        after_record = [record for record in self.writer.records if record["event"] == "AfterLoad"][-1]
        self.assertEqual(after_record["scene_generation"], self.probe.scene_generation)

    def test_load_nested_clear_advances_scene_generation_once(self):
        self.probe.startWatcher()
        initial = self.probe.scene_generation
        self.probe.hipFileCallback("hipFileEventType.BeforeLoad")
        self.probe.hipFileCallback("hipFileEventType.BeforeClear")
        self.probe.hipFileCallback("hipFileEventType.AfterClear")
        self.probe.hipFileCallback("hipFileEventType.AfterLoad")
        self.assertEqual(self.probe.scene_generation, initial + 1)

    def test_unknown_callback_values_do_not_use_object_repr(self):
        class Unknown:
            def __repr__(self):
                raise AssertionError("repr must not be used")

        self.probe.startWatcher()
        self.probe.callback(
            node=self.hou.obj,
            event_type="nodeEventType.FutureEvent",
            future_payload=Unknown(),
        )
        self.probe.processEvents()
        record = self.writer.records[-1]
        self.assertEqual(record["event"], "FutureEvent")
        self.assertEqual(record["payload"]["future_payload"]["value_semantics"], "unverified")


class TraceSchemaTests(unittest.TestCase):
    def test_serialization_shape_validates(self):
        record = base_record(
            "hom",
            "schema_test",
            make_runtime_metadata(),
            1,
            1,
            event="NameChanged",
            payload={"new_name": "box2"},
        )
        self.assertIs(validate_record(record), record)
        self.assertEqual(record["trace_version"], TRACE_VERSION)

    def test_missing_required_field_is_rejected(self):
        record = base_record("hom", "schema_test", make_runtime_metadata(), 1, 1)
        del record["payload"]
        with self.assertRaises(ValueError):
            validate_record(record)

    def test_suppression_context_is_nesting_and_exception_safe(self):
        self.assertEqual(suppression_snapshot()["depth"], 0)
        with self.assertRaises(RuntimeError):
            with remote_application_suppression("outer"):
                with remote_application_suppression("inner"):
                    self.assertEqual(suppression_snapshot()["depth"], 2)
                    raise RuntimeError("probe")
        self.assertEqual(suppression_snapshot(), {"depth": 0, "label": None})


if __name__ == "__main__":
    unittest.main()
