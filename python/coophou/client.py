"""
from importlib import reload
from coophou import eventTranslation
reload(eventTranslation)
from coophou import client
reload(client)
"""

import json

import hou

from .tcp import TcpClient


def _pprint(t, msg):
    msg = f"  - {t}".ljust(9) + " | " + str(msg)
    print(msg)


def onDataReceived(payload):
    from importlib import reload
    from . import eventTranslation

    reload(eventTranslation)

    eventType = payload.get("event_type")
    _pprint(eventType, payload)

    eventTranslation.getEvent(eventType).applyPayload(payload)


# if hasattr(hou.session, "coophou_client"):
#     CLIENT = hou.session.coophou_client
# else:
#     CLIENT = TcpClient()
#     hou.session.coophou_client = CLIENT

#     CLIENT.dataReceived.connect(onDataReceived)


def start():
    print("Starting client...")

    CLIENT = TcpClient()
    CLIENT.dataReceived.connect(onDataReceived)
