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

    eventTranslation.getEvent(eventType).applyPayload(payload)


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
