"""HOM event probe.

Phase 1 records observations only.  It deliberately emits no synchronization
operations and performs no network I/O.
"""

from collections import deque
import os

try:
    import hou as _hou
except ImportError:  # Pure tests inject a fake HOM module.
    _hou = None

from ..probe import registry
from ..probe.trace import (
    TraceWriter,
    base_record,
    make_runtime_metadata,
    suppression_snapshot,
)


ENTITY_ID_KEY = "coophou.entity_id"
DEFAULT_MAX_BUFFERED = 4096
DEFAULT_MAX_PER_TICK = 256


def _event_name(value):
    text = str(value)
    return text.rsplit(".", 1)[-1] if text else "UNKNOWN_EVENT"


def _plain_value(value, hou_module, depth=0):
    """Copy callback values without retaining HOM objects or using repr()."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if depth >= 4:
        return {"kind": type(value).__name__, "truncated": True}
    if isinstance(value, (tuple, list)):
        return [_plain_value(item, hou_module, depth + 1) for item in value[:128]]
    if isinstance(value, dict):
        return {
            str(key): _plain_value(item, hou_module, depth + 1)
            for key, item in list(value.items())[:128]
        }
    path_method = getattr(value, "path", None)
    if callable(path_method):
        try:
            return {"kind": type(value).__name__, "path": path_method()}
        except Exception:
            return {"kind": type(value).__name__, "path": None, "invalid": True}
    return {"kind": type(value).__name__, "value_semantics": "unverified"}


class ClientSender:
    """Idempotent, coophou-owned HOM observation source."""

    def __init__(
        self,
        parent=None,
        hou_module=None,
        trace_path=None,
        scenario=None,
        writer=None,
        max_buffered=DEFAULT_MAX_BUFFERED,
        max_per_tick=DEFAULT_MAX_PER_TICK,
        initial_observation=0,
        initial_scene_generation=1,
    ):
        del parent  # Kept for compatibility with the old QObject constructor.
        self.hou = hou_module if hou_module is not None else _hou
        self.scenario = scenario or os.environ.get("COOPHOU_PROBE_SCENARIO", "unspecified")
        path = trace_path or os.environ.get("COOPHOU_PROBE_TRACE")
        self.writer = writer or TraceWriter(path)
        self.runtime = make_runtime_metadata(self.hou)
        self.max_per_tick = max_per_tick
        self.eventBuffer = deque(maxlen=max_buffered)
        self.dropped_observations = 0
        self.scene_generation = initial_scene_generation
        self.local_observation = initial_observation
        self.callback_depth = 0
        self._started = False
        self._event_loop_registered = False
        self._hip_registered = False
        self._registered_session_ids = set()
        self._known_nodes = {}
        self._snapshot_scan_ids = deque()
        self._snapshot_scan_members = set()
        self._pending_rescan = False
        self._load_in_progress = False
        self._load_generation_advanced = False
        self._node_callback = self.callback
        self._hip_callback = self.hipFileCallback
        self._event_loop_callback = self.processEvents

    @property
    def started(self):
        return self._started

    def _event_types(self):
        if self.hou is None:
            return tuple()
        names = (
            "BeingDeleted",
            "NameChanged",
            "FlagChanged",
            "AppearanceChanged",
            "PositionChanged",
            "InputRewired",
            "ParmTupleChanged",
            "ChildCreated",
            "ChildDeleted",
            "ChildReordered",
        )
        return tuple(
            getattr(self.hou.nodeEventType, name)
            for name in names
            if hasattr(self.hou.nodeEventType, name)
        )

    def startWatcher(self):
        if self._started:
            return True
        if self.hou is None:
            raise RuntimeError("HOM is not available")
        registry.claim(self)
        self.writer.start()
        self._started = True
        self._register_hip_callback()
        self._register_event_loop_callback()
        self.addCallbacks(self.hou.root())
        self.recordMarker("probe_started", {"registration_owner": "coophou"})
        self.processEvents()
        return True

    start = startWatcher

    def stopWatcher(self):
        if not self._started:
            registry.release(self)
            return True
        self.recordMarker("probe_stopping", {"dropped_observations": self.dropped_observations})
        self.processEvents()
        self._remove_event_loop_callback()
        self._remove_hip_callback()
        self._remove_owned_node_callbacks()
        self._started = False
        self._registered_session_ids.clear()
        self._known_nodes.clear()
        self._snapshot_scan_ids.clear()
        self._snapshot_scan_members.clear()
        registry.release(self)
        self.writer.close()
        return True

    stop = stopWatcher

    def _register_event_loop_callback(self):
        ui = getattr(self.hou, "ui", None)
        add = getattr(ui, "addEventLoopCallback", None)
        if callable(add) and not self._event_loop_registered:
            add(self._event_loop_callback)
            self._event_loop_registered = True

    def _remove_event_loop_callback(self):
        if not self._event_loop_registered:
            return
        ui = getattr(self.hou, "ui", None)
        remove = getattr(ui, "removeEventLoopCallback", None)
        if callable(remove):
            try:
                remove(self._event_loop_callback)
            except Exception as exc:
                self.recordMarker("cleanup_error", {"registration": "event_loop", "error": str(exc)})
        self._event_loop_registered = False

    def _register_hip_callback(self):
        hip_file = getattr(self.hou, "hipFile", None)
        add = getattr(hip_file, "addEventCallback", None)
        if callable(add) and not self._hip_registered:
            add(self._hip_callback)
            self._hip_registered = True

    def _remove_hip_callback(self):
        if not self._hip_registered:
            return
        remove = getattr(getattr(self.hou, "hipFile", None), "removeEventCallback", None)
        if callable(remove):
            try:
                remove(self._hip_callback)
            except Exception as exc:
                self.recordMarker("cleanup_error", {"registration": "hip_file", "error": str(exc)})
        self._hip_registered = False

    def _walk_nodes(self, root):
        yield root
        all_nodes = getattr(root, "allNodes", None)
        if callable(all_nodes):
            try:
                yield from all_nodes()
            except Exception:
                return

    def _session_id(self, node):
        try:
            return int(node.sessionId())
        except Exception:
            return None

    def addCallbacks(self, node):
        if not self._started or node is None:
            return
        event_types = self._event_types()
        for current in self._walk_nodes(node):
            session_id = self._session_id(current)
            if session_id is not None and session_id in self._registered_session_ids:
                continue
            try:
                current.addEventCallback(event_types, self._node_callback)
            except Exception as exc:
                self.recordMarker(
                    "registration_error",
                    {"registration": "node", "node_path": self._safe_path(current), "error": str(exc)},
                )
                continue
            if session_id is not None:
                self._registered_session_ids.add(session_id)
                if session_id not in self._snapshot_scan_members:
                    self._snapshot_scan_members.add(session_id)
                    self._snapshot_scan_ids.append(session_id)
            self._remember_node(current)

    def _remove_owned_node_callbacks(self):
        try:
            root = self.hou.root()
        except Exception:
            return
        event_types = self._event_types()
        for node in self._walk_nodes(root):
            try:
                node.removeEventCallback(event_types, self._node_callback)
            except Exception:
                # Deleted nodes already lost their registrations.  We never use
                # removeAllEventCallbacks(), so unrelated callbacks remain.
                continue

    def _safe_path(self, node):
        try:
            return node.path()
        except Exception:
            return None

    def _remember_node(self, node):
        snapshot = self._node_snapshot(node, use_cache=False)
        session_id = snapshot["session_id"]
        if session_id is not None:
            previous = self._known_nodes.get(session_id, {})
            self._known_nodes[session_id] = {
                key: value if value is not None else previous.get(key)
                for key, value in snapshot.items()
            }
        return snapshot

    def refreshSnapshots(self, max_count=None):
        """Refresh a bounded slice of the plain-data deletion cache."""
        limit = self.max_per_tick if max_count is None else max_count
        lookup = getattr(self.hou, "nodeBySessionId", None)
        if not callable(lookup):
            return
        attempts = min(limit, len(self._snapshot_scan_ids))
        for _ in range(attempts):
            session_id = self._snapshot_scan_ids.popleft()
            if session_id not in self._snapshot_scan_members:
                continue
            try:
                node = lookup(session_id)
            except Exception:
                node = None
            if node is None:
                self._snapshot_scan_members.discard(session_id)
                self._known_nodes.pop(session_id, None)
                continue
            self._remember_node(node)
            self._snapshot_scan_ids.append(session_id)

    def _node_snapshot(self, node, use_cache=True):
        if node is None:
            return {
                "path": None,
                "parent_path": None,
                "entity_id": None,
                "session_id": None,
                "node_type": None,
            }
        path = self._safe_path(node)
        try:
            parent_path = self._safe_path(node.parent())
        except Exception:
            parent_path = None
        try:
            entity_id = node.userData(ENTITY_ID_KEY)
        except Exception:
            entity_id = None
        try:
            node_type = node.type().nameWithCategory()
        except Exception:
            try:
                node_type = node.type().name()
            except Exception:
                node_type = None
        snapshot = {
            "path": path,
            "parent_path": parent_path,
            "entity_id": entity_id,
            "session_id": self._session_id(node),
            "node_type": node_type,
        }
        session_id = snapshot["session_id"]
        if use_cache and session_id is not None:
            previous = self._known_nodes.get(session_id, {})
            snapshot = {
                key: value if value is not None else previous.get(key)
                for key, value in snapshot.items()
            }
            self._known_nodes[session_id] = dict(snapshot)
        return snapshot

    def _parameter_payload(self, parm_tuple):
        if parm_tuple is None:
            return {
                "parameter_scope": "bulk_or_ambiguous",
                "parm_tuple": None,
                "raw_values": None,
                "evaluated_values": None,
            }
        payload = {"parameter_scope": "single_tuple"}
        try:
            payload["parm_tuple"] = parm_tuple.name()
        except Exception:
            payload["parm_tuple"] = None
        try:
            payload["evaluated_values"] = _plain_value(parm_tuple.eval(), self.hou)
        except Exception as exc:
            payload["evaluated_values"] = None
            payload["evaluation_error"] = str(exc)
        raw_values = []
        expression_languages = []
        try:
            parms = tuple(parm_tuple)
        except Exception:
            parms = tuple()
        for parm in parms:
            try:
                raw_values.append(parm.rawValue())
            except Exception:
                raw_values.append(None)
            try:
                expression_languages.append(str(parm.expressionLanguage()).rsplit(".", 1)[-1])
            except Exception:
                expression_languages.append(None)
        payload["raw_values"] = raw_values
        payload["expression_languages"] = expression_languages
        return payload

    def _event_specific_payload(self, event, node, kwargs, target):
        payload = {}
        if event == "ChildCreated":
            payload["created_node_type"] = target.get("node_type")
            try:
                payload["created_node_name"] = node.name()
            except Exception:
                payload["created_node_name"] = None
        if event in ("BeingDeleted", "ChildDeleted"):
            payload["deleted_node_type"] = target.get("node_type")
            payload["deletion_snapshot_source"] = "callback_or_plain_cache"
        if event == "PositionChanged":
            try:
                position = node.position()
                payload["position"] = [float(position[0]), float(position[1])]
            except Exception:
                payload["position"] = None
        if event == "InputRewired":
            input_index = kwargs.get("input_index")
            payload["input_index"] = input_index
            payload["source_node_path"] = None
            payload["source_output_index"] = None
            try:
                for connection in node.inputConnections():
                    if connection.inputIndex() == input_index:
                        payload["source_node_path"] = self._safe_path(connection.inputNode())
                        payload["source_output_index"] = int(connection.outputIndex())
                        break
            except Exception as exc:
                payload["connection_capture_error"] = str(exc)
        if event == "FlagChanged":
            flags = {}
            for name, method_name in (
                ("bypass", "isBypassed"),
                ("display", "isDisplayFlagSet"),
                ("render", "isRenderFlagSet"),
                ("template", "isTemplateFlagSet"),
            ):
                method = getattr(node, method_name, None)
                if callable(method):
                    try:
                        flags[name] = bool(method())
                    except Exception:
                        flags[name] = None
            payload["flags"] = flags
        return payload

    def _undo_state(self):
        # HOM 21.0 exposes stack labels and performUndo/performRedo, but no
        # documented callback-time "currently undoing" query.
        return "unknown"

    def _enqueue(self, record):
        if len(self.eventBuffer) == self.eventBuffer.maxlen:
            self.dropped_observations += 1
        self.eventBuffer.append(record)

    def _new_record(self, **fields):
        self.local_observation += 1
        return base_record(
            "hom",
            self.scenario,
            self.runtime,
            self.scene_generation,
            self.local_observation,
            **fields,
        )

    def callback(self, **kwargs):
        if not self._started:
            return
        self.callback_depth += 1
        try:
            event_type = kwargs.get("event_type")
            event = _event_name(event_type)
            callback_node = kwargs.get("node")
            child_node = kwargs.get("child_node")
            target_node = child_node if event in ("ChildCreated", "ChildDeleted") and child_node is not None else callback_node
            target = self._node_snapshot(target_node)
            callback_source = self._node_snapshot(callback_node)
            payload = {
                "callback_node_path": callback_source["path"],
                "callback_node_session_id": callback_source["session_id"],
            }
            for key, value in kwargs.items():
                if key in ("node", "event_type", "parm_tuple"):
                    continue
                payload[key] = _plain_value(value, self.hou)
            if event == "ParmTupleChanged":
                payload.update(self._parameter_payload(kwargs.get("parm_tuple")))
            payload.update(self._event_specific_payload(event, target_node, kwargs, target))
            try:
                payload["editable_inside_locked_hda"] = bool(
                    target_node.isEditableInsideLockedHDA()
                )
            except Exception:
                payload["editable_inside_locked_hda"] = None
            self._enqueue(
                self._new_record(
                    event=event,
                    event_reason=str(event_type) if event_type is not None else None,
                    node_path=target["path"],
                    parent_path=target["parent_path"],
                    entity_id=target["entity_id"],
                    payload=payload,
                    undo_state=self._undo_state(),
                    callback_depth=self.callback_depth,
                    suppression=suppression_snapshot(),
                )
            )
            if event == "ChildCreated" and child_node is not None:
                self.addCallbacks(child_node)
            if event in ("BeingDeleted", "ChildDeleted") and target["session_id"] is not None:
                self._registered_session_ids.discard(target["session_id"])
                self._snapshot_scan_members.discard(target["session_id"])
                if event == "ChildDeleted":
                    self._known_nodes.pop(target["session_id"], None)
        finally:
            self.callback_depth -= 1

    def hipFileCallback(self, event_type):
        if not self._started:
            return
        event = _event_name(event_type)
        if event == "BeforeLoad":
            self._load_in_progress = True
            self._load_generation_advanced = False
        if event == "AfterClear":
            self.scene_generation += 1
            if self._load_in_progress:
                self._load_generation_advanced = True
        elif event == "AfterLoad":
            if not self._load_generation_advanced:
                self.scene_generation += 1
            self._load_in_progress = False
            self._load_generation_advanced = False
        if event in ("AfterClear", "AfterLoad"):
            self._registered_session_ids.clear()
            self._known_nodes.clear()
            self._snapshot_scan_ids.clear()
            self._snapshot_scan_members.clear()
            self._pending_rescan = True
        self.callback_depth += 1
        try:
            self._enqueue(
                self._new_record(
                    event=event,
                    event_reason=str(event_type),
                    payload={"lifecycle": True},
                    undo_state=self._undo_state(),
                    callback_depth=self.callback_depth,
                    suppression=suppression_snapshot(),
                    transaction_hint="scene_lifecycle",
                )
            )
        finally:
            self.callback_depth -= 1

    def recordMarker(self, event, payload=None, transaction_hint="probe_control"):
        self._enqueue(
            self._new_record(
                event=event,
                event_reason="coophou_probe_marker",
                payload=payload or {},
                callback_depth=max(1, self.callback_depth),
                suppression=suppression_snapshot(),
                transaction_hint=transaction_hint,
            )
        )

    def processEvents(self):
        self.refreshSnapshots()
        processed = 0
        while self.eventBuffer and processed < self.max_per_tick:
            self.writer.write(self.eventBuffer.popleft())
            processed += 1
        if self._pending_rescan:
            self._pending_rescan = False
            try:
                self.addCallbacks(self.hou.root())
            except Exception as exc:
                self.recordMarker("registration_error", {"registration": "scene_rescan", "error": str(exc)})
        return processed


HOMEventProbe = ClientSender
