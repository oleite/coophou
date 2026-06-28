import json
import hou

from ..common import *
from . import eventTranslation

from PySide6.QtCore import *

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
    # hou.nodeEventType.ChildSwitched,
    # hou.nodeEventType.ChildSelectionChanged,
]


class ClientSender(QObject):
    payloadReady = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.processing = False
        self.eventBuffer = []

        self.ignoredNodes = []

    def startWatcher(self):
        for c in hou.ui.eventLoopCallbacks():
            hou.ui.removeEventLoopCallback(c)

        hou.ui.addEventLoopCallback(self.processEvents)

        self.addCallbacks(hou.root())

    def addCallbacks(self, node):
         for n in node.allNodes():
            n.removeAllEventCallbacks()
            n.addEventCallback(EVENT_TYPES, self.callback)

    def temporarilyIgnoreNode(self, path):
        if not path:
            print("ERROR: Cant ignore None")
            return
        if path in self.ignoredNodes:
            print(f"Path already ignored: {path}    |    Current: {self.ignoredNodes}")
            return
        self.ignoredNodes.append(path)
        print(f"Info: Added to ignore list: {path}")

    def callback(self, **kwargs):
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
        
        self.eventBuffer.append(eventData)

    def processEvents(self):
        # # ====================================
        # # TODO: Move
        # #
        # self.sendPayload("NetworkCursorMoved", None)
        # self.sendPayload("ViewportCameraChanged", None)
        # #
        # # ====================================

        if self.processing:
            print("Already processing events, skipping")
            return
        if not self.eventBuffer:
            return

        print("="*30)
        self.processing = True

        # Filter out events whose nodes have been deleted or are not editable.
        buf = [
            event
            for event in self.eventBuffer
            if hou.node(event["node"])
            and hou.node(event["node"]).isEditableInsideLockedHDA()
        ]

        self.eventBuffer.clear()

        try:
            print(f"Processing {len(buf)} events:")
            for event in buf:
                print(f"  > {event}")
            print("\\/"*15)

            parmTupleChanges = {}

            for event in buf:

                nodePath = event["node"]

                mainPath = event.get("child_node", event.get("node"))
                if mainPath in self.ignoredNodes:
                    print(f"Info: Skipping ignored node {mainPath}")
                    self.ignoredNodes.remove(mainPath)
                    return

                eventType = event["event_type"].split(".")[-1]

                if eventType == "ChildCreated":
                    # Gotta wait until the next event loop to check for immediate
                    # changes to the newly created node, like children or parm changes.
                    childNode = event["child_node"]
                    print(f"Scheduling callback for new node: {childNode}")
                    hou.ui.postEventCallback(lambda: self.afterNodeCreated(childNode))

                if eventType == "ParmTupleChanged":
                    path = nodePath + "/" + event["parm_tuple"]
                    parmTupleChanges[path] = event
                else:
                    self.sendPayload(eventType, event)

            for path, event in parmTupleChanges.items():
                self.sendPayload("ParmTupleChanged", event)

        except Exception as e:
            print(f"Error processing events: {e}")
        finally:
            print("="*30)
            self.processing = False

    def afterNodeCreated(self, nodePath):
        node = hou.node(nodePath)

        # Any nodes created at the same time as the parent won't trigger
        # their own ChildCreated event, so we have to add callbacks to them manually.
        self.addCallbacks(node)

        self.eventBuffer.append(
            {
                "event_type": "CustomNodeDataChanged",
                "node": nodePath,
            },
        )

    def sendPayload(self, eventType, event):
        if DEV_MODE:
            from importlib import reload

            reload(eventTranslation)

        # Skip root level nodes (/obj, /stage)
        # if event["node"].count("/") == 1 and "Child" not in eventType:
        #     return

        payload = eventTranslation.getEvent(eventType).extractPayload(event)
        payload["event_type"] = eventType

        self.payloadReady.emit(payload)
