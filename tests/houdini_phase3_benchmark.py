"""Reproducible Houdini 21.0 native-adapter measurements.

This is evidence, not a microbenchmark claim: external timings include the
plain JSON bridge, while native callback/extractor counters isolate the HDK
handler and supported-state extraction work.
"""

from __future__ import annotations

import json
import math
import platform
import statistics
import sys
import time

import hou
from PySide6.QtCore import qVersion

from coophou.core import MODEL_VERSION
from coophou.core.models import (
    CreateNodeSpec,
    CreateSubtree,
    EntityRef,
    OperationType,
    Transaction,
)
from coophou.houdini_adapter import NativeBridge


def timed(callable_, repeats=1):
    samples = []
    result = None
    for _ in range(repeats):
        started = time.perf_counter_ns()
        result = callable_()
        samples.append(time.perf_counter_ns() - started)
    ordered = sorted(samples)
    p95 = ordered[max(0, math.ceil(len(ordered) * 0.95) - 1)]
    return result, {
        "samples": len(samples),
        "median_ms": statistics.median(samples) / 1_000_000,
        "p95_ms": p95 / 1_000_000,
        "max_ms": max(samples) / 1_000_000,
    }


bridge = NativeBridge(hou)
bridge.stop_capture()


def new_root(name="benchmark_root"):
    hou.hipFile.clear(suppress_save_prompt=True)
    root = hou.node("/obj").createNode("geo", name)
    for child in root.children():
        child.destroy()
    return root


def start(root, max_nodes, *, parameters=False):
    return bridge.start_capture(
        root_path=root.path(),
        root_entity_id="root",
        deterministic_id_prefix="benchmark",
        operator_types=["null"],
        parameter_names=["cacheinput"] if parameters else [],
        parameter_kinds={"cacheinput": "boolean"} if parameters else {},
        max_nodes=max_nodes,
        capture_queue_limit=4096,
        apply_queue_limit=32,
    )


report = {
    "benchmark_schema_version": 1,
    "environment": {
        "houdini_version": hou.applicationVersionString(),
        "python": sys.version.split()[0],
        "qt": qVersion(),
        "platform": platform.platform(),
        "compiler": "MSVC 19.44.35228.0",
    },
    "configured_root_scans": {},
}

for size, repeats in ((10, 20), (100, 10), (1000, 5)):
    root = new_root(f"scan_{size}")
    for index in range(size):
        root.createNode("null", f"n{index:04d}")
    _, bootstrap = timed(lambda: start(root, size + 8))
    _, scan = timed(bridge.extract_snapshot, repeats=repeats)
    state = bridge.capture_state()
    report["configured_root_scans"][str(size)] = {
        "bootstrap_bridge": bootstrap,
        "snapshot_bridge": scan,
        "native_extraction_count": state["snapshot_extraction_count"],
        "native_extraction_mean_ms": (
            state["snapshot_extraction_ns_total"]
            / state["snapshot_extraction_count"]
            / 1_000_000
        ),
        "native_extraction_max_ms": state["snapshot_extraction_ns_max"] / 1_000_000,
    }
    bridge.stop_capture()

root = new_root("burst")
start(root, 1200, parameters=True)
before = bridge.capture_state()
_, create_action = timed(
    lambda: [root.createNode("null", f"burst_{index:04d}") for index in range(1000)]
)
after_create = bridge.capture_state()
settled, settle = timed(bridge.flush_settle)
drained, drain = timed(lambda: bridge.drain_capture(max_count=4096))
event_delta = after_create["events_seen"] - before["events_seen"]
handler_ns = (
    after_create["callback_handler_ns_total"] - before["callback_handler_ns_total"]
)
report["create_observation_burst"] = {
    "created_nodes": 1000,
    "hdk_events": event_delta,
    "action_with_callbacks": create_action,
    "native_callback_handler_mean_us": handler_ns / max(1, event_delta) / 1000,
    "native_callback_handler_max_us": after_create["callback_handler_ns_max"] / 1000,
    "settle_and_supported_scan": settle,
    "bridge_drain": drain,
    "semantic_operations": settled["operation_count"],
    "capture_records": len(drained["records"]),
}

moving = root.node("burst_0000")
_, move_action = timed(
    lambda: [moving.setPosition((float(index), float(-index))) for index in range(1000)]
)
move_settled, move_settle = timed(bridge.flush_settle)
move_records = bridge.drain_capture(max_count=64)["records"]
report["move_burst_coalescing"] = {
    "edits": 1000,
    "action_with_callbacks": move_action,
    "settle": move_settle,
    "semantic_operations": move_settled["operation_count"],
    "capture_records": len(move_records),
}

parameter = root.node("burst_0001").parm("cacheinput")
_, parameter_action = timed(lambda: [parameter.set(index % 2) for index in range(1002)])
parameter_settled, parameter_settle = timed(bridge.flush_settle)
bridge.drain_capture(max_count=64)
report["parameter_burst_coalescing"] = {
    "edits": 1002,
    "action_with_callbacks": parameter_action,
    "settle": parameter_settle,
    "semantic_operations": parameter_settled["operation_count"],
}
bridge.stop_capture()

root = new_root("copy_delete")
source = [root.createNode("null", f"source_{index:03d}") for index in range(100)]
start(root, 300)
copies, copy_action = timed(lambda: hou.copyNodesTo(tuple(source), root))
copy_settled, copy_settle = timed(bridge.flush_settle)
bridge.drain_capture(max_count=256)
_, delete_action = timed(lambda: [node.destroy() for node in copies])
delete_settled, delete_settle = timed(bridge.flush_settle)
bridge.drain_capture(max_count=256)
report["copy_delete_100"] = {
    "copy_action_with_callbacks": copy_action,
    "copy_settle": copy_settle,
    "copy_semantic_operations": copy_settled["operation_count"],
    "delete_action_with_callbacks": delete_action,
    "delete_settle": delete_settle,
    "delete_semantic_operations": delete_settled["operation_count"],
}
bridge.stop_capture()

report["native_subtree_apply"] = {}
for size in (10, 100):
    root = new_root(f"apply_{size}")
    generation = start(root, size + 8)["scene_generation"]
    root_ref = EntityRef(MODEL_VERSION, "root", last_known_path=root.path())
    specs = tuple(
        CreateNodeSpec(
            MODEL_VERSION,
            EntityRef(MODEL_VERSION, f"apply-{size}-{index}"),
            root_ref,
            "null",
            f"applied_{index:04d}",
            (float(index), 0.0),
            (),
        )
        for index in range(size)
    )
    operation = CreateSubtree(
        MODEL_VERSION,
        f"operation-apply-{size}",
        specs,
        (),
    )
    transaction = Transaction(
        MODEL_VERSION,
        f"transaction-apply-{size}",
        "benchmark-client",
        "benchmark-session",
        (operation,),
        "benchmark native subtree apply",
        (OperationType.CREATE_SUBTREE,),
    )

    def apply_transaction():
        bridge.enqueue_apply(transaction, generation, f"benchmark-{size}")
        return bridge.drain_apply(max_transactions=1, max_operations=1)

    result, application = timed(apply_transaction)
    assert result["results"][0]["payload"]["status"] == "APPLIED_VERIFIED"
    state = bridge.capture_state()
    report["native_subtree_apply"][str(size)] = {
        "apply_and_postverify": application,
        "native_extraction_count": state["snapshot_extraction_count"],
        "native_extraction_total_ms": state["snapshot_extraction_ns_total"] / 1_000_000,
    }
    bridge.stop_capture()

root = new_root("bridge_overhead")
start(root, 8)
_, bridge_state = timed(bridge.capture_state, repeats=1000)
report["bridge_state_json_roundtrip"] = bridge_state
bridge.stop_capture()

print(json.dumps(report, indent=2, sort_keys=True))
