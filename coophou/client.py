import json

import hou

from .tcp import TcpClient
from .common import log


def onDataReceived(payload):
    from importlib import reload
    from . import eventTranslation

    reload(eventTranslation)

    eventType = payload.get("event_type")
    log(eventType, payload)

    apply = lambda: eventTranslation.getEvent(eventType).applyPayload(payload)

    # Delay calling apply until the UI is idle to avoid conflicts with ongoing operations.
    if hou.isUIAvailable():
        hou.ui.postEventCallback(apply)
    else:
        apply()

CLIENT = None


def start():
    global CLIENT

    print("Starting client...")

    if hasattr(hou.session, "coophou_client"):
        CLIENT = hou.session.coophou_client
    else:
        CLIENT = TcpClient()
        hou.session.coophou_client = CLIENT

        CLIENT.dataReceived.connect(onDataReceived)
