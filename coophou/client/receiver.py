import hou

from . import eventTranslation
from ..common import *

from PySide6.QtCore import *


class ClientReceiver(QObject):
    nodeCreated = Signal(hou.Node)

    def onDataReceived(self, payload):

        if DEV_MODE:
            from importlib import reload

            reload(eventTranslation)

        eventType = payload.get("event_type")

        def apply():
            with hou.undos.disabler():

                print("[APPLYING PAYLOAD] ", payload)

                eventTranslation.getEvent(eventType).applyPayload(payload)

                if eventType == "ChildCreated":
                    self.nodeCreated.emit(hou.node(payload["node"]))

        # Delay calling apply until the UI is idle to avoid conflicts with ongoing operations.
        hou.ui.postEventCallback(apply)