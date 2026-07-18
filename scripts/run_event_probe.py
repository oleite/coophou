"""Run one repeatable HOM or HDK Phase-1 probe scenario under Houdini.

Use a fresh hython process per invocation.  UI-only drag/copy-paste gestures are
represented by their scripted equivalents and remain explicitly unverified.
"""

import argparse
import os
from pathlib import Path
import sys
import tempfile

import hou

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from coophou.client.sender import ClientSender
from coophou.probe import remote_application_suppression

ACTIVE_PROBE = None


def _checkpoint():
    if ACTIVE_PROBE is not None:
        ACTIVE_PROBE.processEvents()


def _obj():
    return hou.node("/obj")


def _geo(name="probe_geo"):
    geo = _obj().createNode("geo", name)
    for child in geo.children():
        child.destroy()
    return geo


def create_node():
    _obj().createNode("geo", "created_node")


def create_immediately_modify():
    node = _obj().createNode("geo", "created_then_modified")
    node.parmTuple("t").set((1.0, 2.0, 3.0))


def copy_paste_one_node():
    node = _obj().createNode("geo", "copy_source")
    node.setUserData("coophou.entity_id", "probe-duplicate-id")
    _checkpoint()
    hou.copyNodesTo((node,), _obj())


def copy_paste_connected_subtree():
    geo = _geo()
    first = geo.createNode("box", "copy_box")
    second = geo.createNode("null", "copy_null")
    second.setInput(0, first)
    first.setUserData("coophou.entity_id", "probe-copy-box-id")
    second.setUserData("coophou.entity_id", "probe-copy-null-id")
    _checkpoint()
    hou.copyNodesTo((first, second), geo)


def delete_node():
    node = _obj().createNode("geo", "delete_me")
    node.setUserData("coophou.entity_id", "probe-delete-id")
    _checkpoint()
    node.destroy()


def delete_subnet():
    subnet = _obj().createNode("subnet", "delete_subnet")
    subnet.createNode("geo", "child_a")
    subnet.createNode("geo", "child_b")
    subnet.destroy()


def rename():
    node = _obj().createNode("geo", "rename_before")
    node.setUserData("coophou.entity_id", "probe-rename-id")
    node.setName("rename_after", unique_name=False)


def drag_move():
    node = _obj().createNode("geo", "scripted_move")
    node.setPosition(hou.Vector2(4.5, -2.25))


def connect_disconnect():
    geo = _geo()
    source = geo.createNode("box", "wire_source")
    destination = geo.createNode("null", "wire_destination")
    destination.setInput(0, source)
    destination.setInput(0, None)


def parameter_types():
    geo = _geo()
    box = geo.createNode("box", "parameter_types")
    box.parm("divrate1").set(7)                 # integer
    box.parm("sizex").set(2.5)                 # float
    box.parm("dodivs").set(True)               # toggle
    geo.parm("shop_materialpath").set("probe/material")  # string
    box.parm("type").set("mesh")               # menu token
    box.parmTuple("size").set((2.0, 3.0, 4.0)) # tuple


def _undo_redo(label, action):
    with hou.undos.group(label):
        action()
    hou.undos.performUndo()
    hou.undos.performRedo()


def undo_redo_candidates():
    geo = _geo()
    node = geo.createNode("box", "undo_subject")
    other = geo.createNode("null", "undo_destination")
    _undo_redo("probe rename", lambda: node.setName("undo_renamed"))
    _undo_redo("probe move", lambda: node.setPosition(hou.Vector2(3.0, 1.0)))
    _undo_redo("probe parameter", lambda: node.parm("sizex").set(5.0))
    _undo_redo("probe connect", lambda: other.setInput(0, node))
    _undo_redo("probe disconnect", lambda: other.setInput(0, None))
    created = []
    _undo_redo("probe create", lambda: created.append(geo.createNode("null", "undo_created")))
    doomed = geo.createNode("null", "undo_deleted")
    _undo_redo("probe delete", doomed.destroy)


def save_load_merge_clear():
    with tempfile.TemporaryDirectory(prefix="coophou_probe_") as directory:
        directory = Path(directory)
        base = directory / "base.hip"
        merge = directory / "merge.hip"
        _obj().createNode("geo", "saved_node")
        hou.hipFile.save(str(base))
        _obj().createNode("geo", "merge_node")
        hou.hipFile.save(str(merge))
        hou.hipFile.load(str(base), suppress_save_prompt=True)
        hou.hipFile.merge(str(merge), node_pattern="*", overwrite_on_conflict=False)
        hou.hipFile.clear(suppress_save_prompt=True)


def locked_hda_boundary():
    with tempfile.TemporaryDirectory(prefix="coophou_hda_probe_") as directory:
        hda_path = str(Path(directory) / "probe_locked.hda")
        subnet = _obj().createNode("subnet", "locked_boundary")
        inside = subnet.createNode("geo", "inside")
        hda = subnet.createDigitalAsset(
            name="coophou::probe_locked::1.0",
            hda_file_name=hda_path,
            description="coophou probe locked boundary",
        )
        hda.matchCurrentDefinition()
        locked_inside = hda.node(inside.name())
        mutation_result = "succeeded"
        try:
            locked_inside.parmTuple("t").set((1.0, 0.0, 0.0))
        except hou.PermissionError:
            mutation_result = "permission_error"
        if ACTIVE_PROBE is not None:
            ACTIVE_PROBE.recordMarker(
                "locked_hda_result",
                {
                    "asset_locked": bool(hda.isLockedHDA()),
                    "inside_editable": bool(locked_inside.isEditableInsideLockedHDA()),
                    "mutation_result": mutation_result,
                },
                transaction_hint="permission_boundary",
            )


def remote_suppression():
    node = _obj().createNode("geo", "suppressed_change")
    with remote_application_suppression("probe_remote_application"):
        node.parmTuple("t").set((9.0, 8.0, 7.0))


def lifecycle_restart_reload():
    global ACTIVE_PROBE
    _obj().createNode("geo", "lifecycle_node")
    if ACTIVE_PROBE is None:
        return
    old_probe = ACTIVE_PROBE
    old_probe.processEvents()
    generation = old_probe.scene_generation
    trace_path = old_probe.writer.path
    old_probe.stopWatcher()
    observation = old_probe.local_observation

    import importlib
    import coophou.client.sender as sender_module

    sender_module = importlib.reload(sender_module)
    replacement = sender_module.ClientSender(
        trace_path=trace_path,
        scenario="lifecycle_restart_reload",
        initial_observation=observation,
        initial_scene_generation=generation,
    )
    replacement.startWatcher()
    replacement.startWatcher()
    ACTIVE_PROBE = replacement
    _obj().createNode("geo", "after_reload")


SCENARIOS = {
    "create_node": create_node,
    "create_immediately_modify": create_immediately_modify,
    "copy_paste_one_node": copy_paste_one_node,
    "copy_paste_connected_subtree": copy_paste_connected_subtree,
    "delete_node": delete_node,
    "delete_subnet": delete_subnet,
    "rename": rename,
    "drag_move": drag_move,
    "connect_disconnect": connect_disconnect,
    "parameter_types": parameter_types,
    "undo_redo_candidates": undo_redo_candidates,
    "save_load_merge_clear": save_load_merge_clear,
    "locked_hda_boundary": locked_hda_boundary,
    "remote_suppression": remote_suppression,
    "lifecycle_restart_reload": lifecycle_restart_reload,
}


def default_output(adapter, scenario, hdk_api):
    version = hou.applicationVersionString()
    platform_name = "windows" if sys.platform == "win32" else sys.platform
    return (
        REPOSITORY_ROOT
        / "tests"
        / "fixtures"
        / "events"
        / f"houdini-{version}"
        / f"hdk-api-{hdk_api}"
        / platform_name
        / adapter
        / f"{scenario}.jsonl"
    )


def run(adapter, scenario, output):
    global ACTIVE_PROBE
    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    os.environ["COOPHOU_PROBE_SCENARIO"] = scenario
    os.environ["COOPHOU_PROBE_TRACE"] = str(output)
    hou.hipFile.clear(suppress_save_prompt=True)

    probe = None
    if adapter == "hom":
        probe = ClientSender(trace_path=output, scenario=scenario)
        ACTIVE_PROBE = probe
        probe.startWatcher()
        probe.startWatcher()
    else:
        output_text, error_text = hou.hscript("coop_start")
        if error_text:
            raise RuntimeError(error_text or output_text or "coop_start failed")
        hou.hscript("coop_start")

    try:
        SCENARIOS[scenario]()
        if adapter == "hom":
            probe = ACTIVE_PROBE
        if probe is not None:
            probe.processEvents()
    finally:
        if probe is not None:
            probe.stopWatcher()
            probe.stopWatcher()
            ACTIVE_PROBE = None
        else:
            hou.hscript("coop_stop")
            hou.hscript("coop_stop")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter", choices=("hom", "hdk"), required=True)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--hdk-api", default="21000693")
    args = parser.parse_args()
    output = args.output or default_output(args.adapter, args.scenario, args.hdk_api)
    run(args.adapter, args.scenario, output.resolve())
    print(output.resolve())


if __name__ == "__main__":
    main()
