"""Versioned JSONL trace records with no Houdini runtime dependencies."""

from contextlib import contextmanager
from collections import deque
import json
import os
import platform
import sys
import threading
import time


TRACE_VERSION = 1
ADAPTERS = frozenset(("hom", "hdk"))
UNDO_STATES = frozenset(("undo", "redo", "undo_or_redo", "not_undo_redo", "unknown"))

_suppression = threading.local()


def _suppression_state():
    state = getattr(_suppression, "state", None)
    if state is None:
        state = {"depth": 0, "label": None}
        _suppression.state = state
    return state


@contextmanager
def remote_application_suppression(label="temporary_remote_application"):
    """Mark callback observations caused by a temporary remote apply.

    This is probe metadata, not the final echo-suppression contract.
    """
    state = _suppression_state()
    previous_label = state["label"]
    state["depth"] += 1
    state["label"] = str(label)
    try:
        yield
    finally:
        state["depth"] -= 1
        state["label"] = previous_label


def suppression_snapshot():
    state = _suppression_state()
    return {"depth": state["depth"], "label": state["label"]}


def make_runtime_metadata(hou_module=None):
    houdini_version = None
    houdini_build = None
    if hou_module is not None:
        try:
            version_tuple = hou_module.applicationVersion()
            houdini_version = hou_module.applicationVersionString()
            houdini_build = int(version_tuple[2])
        except (AttributeError, IndexError, TypeError, ValueError):
            pass

    qt_version = None
    try:
        from PySide6 import QtCore

        qt_version = QtCore.qVersion()
    except (ImportError, AttributeError):
        pass

    return {
        "houdini_version": houdini_version,
        "houdini_build": houdini_build,
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "qt_version": qt_version,
        "hdk_api_version": None,
    }


def validate_record(record):
    """Validate the required v1 trace shape and return the record."""
    required = {
        "trace_version",
        "adapter",
        "scenario",
        "houdini_version",
        "houdini_build",
        "platform",
        "python_version",
        "qt_version",
        "hdk_api_version",
        "scene_generation",
        "observation",
        "timestamp_ns",
        "event",
        "event_reason",
        "node_path",
        "parent_path",
        "entity_id",
        "payload",
        "undo_state",
        "callback_depth",
        "transaction_hint",
        "suppression",
    }
    missing = sorted(required.difference(record))
    if missing:
        raise ValueError("missing trace fields: " + ", ".join(missing))
    if record["trace_version"] != TRACE_VERSION:
        raise ValueError("unsupported trace_version")
    if record["adapter"] not in ADAPTERS:
        raise ValueError("adapter must be 'hom' or 'hdk'")
    if not isinstance(record["scenario"], str) or not record["scenario"]:
        raise ValueError("scenario must be a non-empty string")
    if not isinstance(record["scene_generation"], int) or record["scene_generation"] < 1:
        raise ValueError("scene_generation must be a positive integer")
    if not isinstance(record["observation"], int) or record["observation"] < 1:
        raise ValueError("observation must be a positive integer")
    if not isinstance(record["timestamp_ns"], int) or record["timestamp_ns"] < 0:
        raise ValueError("timestamp_ns must be a non-negative integer")
    if not isinstance(record["event"], str) or not record["event"]:
        raise ValueError("event must be a non-empty string")
    if not isinstance(record["payload"], dict):
        raise ValueError("payload must be an object")
    if record["undo_state"] not in UNDO_STATES:
        raise ValueError("invalid undo_state")
    if not isinstance(record["callback_depth"], int) or record["callback_depth"] < 1:
        raise ValueError("callback_depth must be a positive integer")
    suppression = record["suppression"]
    if not isinstance(suppression, dict):
        raise ValueError("suppression must be an object")
    if not isinstance(suppression.get("depth"), int) or suppression["depth"] < 0:
        raise ValueError("suppression.depth must be a non-negative integer")
    return record


class TraceWriter:
    """Deterministic JSONL sink used outside Houdini callbacks."""

    def __init__(self, path=None, max_retained_records=65536):
        self.path = os.fspath(path) if path else None
        self.records = deque(maxlen=max_retained_records)
        self._stream = None

    def start(self):
        if self._stream is not None or self.path is None:
            return
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        self._stream = open(self.path, "a", encoding="utf-8", newline="\n")

    def write(self, record):
        validate_record(record)
        encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.records.append(record)
        if self._stream is not None:
            self._stream.write(encoded + "\n")
            self._stream.flush()

    def close(self):
        if self._stream is not None:
            self._stream.close()
            self._stream = None


def base_record(adapter, scenario, runtime, scene_generation, observation, **fields):
    record = {
        "trace_version": TRACE_VERSION,
        "adapter": adapter,
        "scenario": scenario,
        **runtime,
        "scene_generation": scene_generation,
        "observation": observation,
        "timestamp_ns": time.time_ns(),
        "event": fields.get("event", "UNKNOWN_EVENT"),
        "event_reason": fields.get("event_reason"),
        "node_path": fields.get("node_path"),
        "parent_path": fields.get("parent_path"),
        "entity_id": fields.get("entity_id"),
        "payload": fields.get("payload", {}),
        "undo_state": fields.get("undo_state", "unknown"),
        "callback_depth": fields.get("callback_depth", 1),
        "transaction_hint": fields.get("transaction_hint"),
        "suppression": fields.get("suppression", {"depth": 0, "label": None}),
    }
    return validate_record(record)
