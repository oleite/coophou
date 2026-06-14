import os
import json

from PySide6.QtCore import *

from ..common import *
from .http import HTTPServerThread

from PySide6.QtNetwork import QTcpServer, QHostAddress, QTcpSocket


class CoopHouServer(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.tcpServer = QTcpServer(self)
        self.tcpServer.newConnection.connect(self.onConnection)

        self.users = {}
        self.uidCounter = 0

        self.httpServer = HTTPServerThread()

    def start(self):

        if self.tcpServer.listen(QHostAddress.SpecialAddress.LocalHost, TCP_PORT):
            print(f"TCP Server listening on port {TCP_PORT}")
        else:
            print("Failed to start TCP server.")
            return

        self.httpServer.start()

    def httpRefresh(self):
        self.httpServer.updateData({"users": self.users})

    @Slot()
    def onConnection(self):
        socket = self.tcpServer.nextPendingConnection()

        # Use default arguments in lambda to capture the specific socket instance
        socket.readyRead.connect(lambda s=socket: self.onReadyRead(s))
        socket.disconnected.connect(lambda s=socket: self.onDisconnection(s))

        self.uidCounter += 1
        uid = str(self.uidCounter)
        self.users[uid] = {
            "tcp_socket": socket,
            "udp_address": None,
            "username": "Unnamed",
        }

        print(f"Client [{uid}] connected")
        self.httpRefresh()

    def onDisconnection(self, socket):
        uid = self.uidFromSocket(socket)
        self.users.pop(uid, None)
        socket.deleteLater()
        print(f"Client [{uid}] disconnected")
        self.httpRefresh()

    def onReadyRead(self, socket):
        packet = readData(socket)
        logReceive(packet)

        if packet.get("type") == "handshake_init":
            uid = self.uidFromSocket(socket)
            self.users[uid]["username"] = packet["username"]

            reply = {
                "type": "handshake_reply",
                "uid": uid,
            }
            self.sendMessage(socket, json.dumps(reply))
            return

        uid = packet.get("uid")

        if not uid:
            reply = {"type": "error", "error": "No UID provided"}
            self.sendMessage(socket, json.dumps(reply))
            return

        if uid not in self.users:
            reply = {"type": "error", "error": "Invalid UID provided"}
            self.sendMessage(socket, json.dumps(reply))
            return
        
        # send update to other users 
        for k, v in self.users.items():
            if k == uid:
                continue

            new = packet.copy()
            new["author_uid"] = new.pop("uid", None)
                
            self.sendMessage(v["tcp_socket"], json.dumps(new))

    def uidFromSocket(self, socket):
        for k, v in self.users.items():
            if v["tcp_socket"] == socket:
                return k

    def sendMessage(self, socket, message):
        logSend(message)

        socket.write(message.encode("utf-8"))
        socket.flush()
