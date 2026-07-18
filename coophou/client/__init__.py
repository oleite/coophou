import json
import getpass
from importlib import reload

try:
    import hou
except ImportError:
    hou = None

try:
    from PySide6.QtCore import QObject, Slot
    from PySide6.QtNetwork import QAbstractSocket, QTcpSocket
except ImportError:
    QObject = object

    def Slot(*args, **kwargs):
        del args, kwargs
        return lambda function: function

    QAbstractSocket = None
    QTcpSocket = None

from ..common import *
from . import sender

if hou is not None:
    from . import receiver
else:
    receiver = None


class CoopHouClient(QObject):

    def __init__(self, parent=None):
        super().__init__(parent)

        if DEV_MODE:
            reload(sender)
            reload(receiver)

        self.sender = sender.ClientSender()

        self.receiver = receiver.ClientReceiver()
        self.receiver.nodeCreated.connect(self.sender.addCallbacks)

        self.tcpSocket = QTcpSocket(self)

        self.tcpSocket.connected.connect(self.onConnected)
        self.tcpSocket.disconnected.connect(self.onDisconnected)
        self.tcpSocket.errorOccurred.connect(self.onError)
        self.tcpSocket.readyRead.connect(self.onReadyRead)

        self.connecting = False
        self.reconnect = True

        self.udpClient = (
            None  # TODO: Implement UDP client for discovery and broadcasting
        )

        self.username = getpass.getuser()
        self.uid = None

    def start(self):
        if self.connecting:
            "Skipped start: already attempting connection"
            return

        print("Connecting...")
        self.connecting = True
        self.tcpSocket.connectToHost("127.0.0.1", TCP_PORT)

    def afterHandshake(self):
        print(f"Handshake complete! Server assigned UID: {self.uid}")

        self.connecting = False
        self.sender.startWatcher()

    def onConnected(self):
        print("Connection established, sending handshake...")

        packet = {
            "type": "handshake_init",
            "username": self.username,
        }
        self.sendMessage(json.dumps(packet))

    def onDisconnected(self):
        print("DISCONNECTED FROM SERVER.")
        self.sender.stopWatcher()
        if self.reconnect:
            self.start()

    def onError(self, e):
        print(f"ERROR: {e}")

        if e == QAbstractSocket.SocketError.ConnectionRefusedError:
            self.connecting = False
            if self.reconnect:
                self.start()

    def onReadyRead(self):
        packet = readData(self.tcpSocket)
        if not packet:
            return

        logReceive(packet)

        if packet.get("type") == "handshake_reply":
            self.uid = packet["uid"]
            self.afterHandshake()
            return

        # Phase 1 is observation-only.  Do not feed legacy relay payloads into
        # eventTranslation or mutate the scene while gathering probe evidence.
        print("Ignoring legacy relay payload while the event probe is active.")

    def sendPayload(self, payload):
        payload["uid"] = self.uid
        self.sendMessage(json.dumps(payload))

    @Slot(str)
    def sendMessage(self, message):
        logSend(message)

        if self.tcpSocket.state() != QTcpSocket.SocketState.ConnectedState:
            print("ERROR: Can't send message, not connected to Server")
            return

        self.tcpSocket.write(message.encode("utf-8"))
        self.tcpSocket.flush()


CLIENT = None


def start():
    global CLIENT
    if not CLIENT:
        CLIENT = CoopHouClient()
    CLIENT.start()
