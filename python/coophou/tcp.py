from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtNetwork import QTcpServer, QHostAddress, QTcpSocket
import json

PORT = 8101


def _readData(socket) -> dict:
    dataBytes = bytes(socket.readAll().data())
    data = {}
    if dataBytes:
        messageString = dataBytes.decode("utf-8").strip()

        for line in messageString.split("\n"):
            line = line.strip()
            if line:
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    pass
    return data


class TcpServer(QObject):
    dataReceived = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tcpServer = QTcpServer(self)
        self.connectedClients = []

        self.tcpServer.newConnection.connect(self.handleNewConnection)

        if self.tcpServer.listen(QHostAddress.SpecialAddress.LocalHost, PORT):
            print(f"Server listening on port {PORT}...")
        else:
            print("Failed to start server.")

    @Slot()
    def handleNewConnection(self):
        newClient = self.tcpServer.nextPendingConnection()
        self.connectedClients.append(newClient)

        # Use default arguments in lambda to capture the specific socket instance
        newClient.readyRead.connect(lambda client=newClient: self.readData(client))
        newClient.disconnected.connect(
            lambda client=newClient: self.handleDisconnection(client)
        )
        print("New client connected.")

    @Slot()
    def readData(self, clientSocket):
        self.dataReceived.emit(_readData(clientSocket))

    @Slot()
    def handleDisconnection(self, clientSocket):
        if clientSocket in self.connectedClients:
            self.connectedClients.remove(clientSocket)
        clientSocket.deleteLater()
        print("Client disconnected.")

    @Slot(str)
    def sendMessage(self, message):
        for client in self.connectedClients:
            if client.state() == QTcpSocket.SocketState.ConnectedState:
                client.write(message.encode("utf-8"))
                client.flush()


class TcpClient(QObject):
    dataReceived = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tcpSocket = QTcpSocket(self)

        self.tcpSocket.connected.connect(self.handleConnection)
        self.tcpSocket.readyRead.connect(self.readData)

        self.tcpSocket.connectToHost("127.0.0.1", PORT)

    @Slot()
    def handleConnection(self):
        print("Connected to server.")

    @Slot()
    def readData(self):
        self.dataReceived.emit(_readData(self.tcpSocket))

    @Slot(str)
    def sendMessage(self, message):
        if self.tcpSocket.state() == QTcpSocket.SocketState.ConnectedState:
            self.tcpSocket.write(message.encode("utf-8"))
            self.tcpSocket.flush()
