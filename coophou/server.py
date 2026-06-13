import json

import hou

from .tcp import TcpServer
from .common import log

EVENT_TYPES = [
    hou.nodeEventType.BeingDeleted,
    hou.nodeEventType.NameChanged,
    hou.nodeEventType.FlagChanged,
    hou.nodeEventType.AppearanceChanged,
    hou.nodeEventType.PositionChanged,
    hou.nodeEventType.InputRewired,
    hou.nodeEventType.ParmTupleChanged,
    hou.nodeEventType.ChildCreated,
    hou.nodeEventType.ChildDeleted,
    hou.nodeEventType.ChildReordered,
    hou.nodeEventType.ChildSwitched,
    hou.nodeEventType.ChildSelectionChanged,
]
EVENT_BUFFER = []
IS_PROCESSING = False
SERVER = None


def _startServer():
    global SERVER
    if hasattr(hou.session, "coophou_server"):
        SERVER = hou.session.coophou_server
    else:
        SERVER = TcpServer()
        hou.session.coophou_server = SERVER


def sendPayload(eventType, event):
    global SERVER
    if not SERVER:
        print("SERVER not initialized, cannot send payload")
        return

    from importlib import reload
    from . import eventTranslation

    reload(eventTranslation)

    payload = eventTranslation.getEvent(eventType).extractPayload(event)
    payload["event_type"] = eventType
    SERVER.sendMessage(json.dumps(payload) + "\n")


def afterNodeCreated(nodePath):
    node = hou.node(nodePath)

    # Any nodes created at the same time as the parent won't trigger
    # their own ChildCreated event, so we have to add callbacks to them manually.
    for n in node.allNodes():
        n.addEventCallback(EVENT_TYPES, clientCallback)

    EVENT_BUFFER.append(
        {
            "event_type": "CustomNodeDataChanged",
            "node": nodePath,
        },
    )


def processEvents():
    # TODO: Move 
    sendPayload("NetworkCursorMoved", None)
    sendPayload("ViewportCameraChanged", None)

    global EVENT_BUFFER, IS_PROCESSING

    if IS_PROCESSING:
        print("Already processing events, skipping")
        return
    if not EVENT_BUFFER:
        return

    IS_PROCESSING = True

    # Filter out events whose nodes have been deleted or are not editable.
    buf = [
        event
        for event in EVENT_BUFFER
        if hou.node(event["node"])
        and hou.node(event["node"]).isEditableInsideLockedHDA()
    ]

    EVENT_BUFFER.clear()

    try:
        print(f"Processing {len(buf)} events")

        parmTupleChanges = {}

        for event in buf:
            nodePath = event["node"]
            node = hou.node(nodePath)

            eventType = event["event_type"].split(".")[-1]
            log(eventType, event)

            if eventType == "ChildCreated":
                # Gotta wait until the next event loop to check for immediate
                # changes to the newly created node, like children or parm changes.
                childNode = event["child_node"]
                print(f"Scheduling callback for new node: {childNode}")
                hou.ui.postEventCallback(lambda: afterNodeCreated(childNode))

            if eventType == "ParmTupleChanged":
                path = nodePath + "/" + event["parm_tuple"]
                parmTupleChanges[path] = event
            else:
                sendPayload(eventType, event)

        for path, event in parmTupleChanges.items():
            sendPayload("ParmTupleChanged", event)

    except Exception as e:
        print(f"Error processing events: {e}")
    finally:
        IS_PROCESSING = False


def clientCallback(**kwargs):
    global EVENT_BUFFER

    node = kwargs["node"]

    if not node.isEditableInsideLockedHDA():
        return

    eventData = {}
    for k, v in kwargs.items():
        if isinstance(v, hou.OpNode):
            eventData[k] = v.path()
        elif isinstance(v, hou.ParmTuple):
            eventData[k] = v.name()
        else:
            eventData[k] = str(v)

    EVENT_BUFFER.append(eventData)


def _startWatcher():
    for c in hou.ui.eventLoopCallbacks():
        hou.ui.removeEventLoopCallback(c)

    hou.ui.addEventLoopCallback(processEvents)

    for node in hou.root().allNodes():
        node.removeAllEventCallbacks()
        node.addEventCallback(EVENT_TYPES, clientCallback)


def start():
    _startServer()
    _startWatcher()
