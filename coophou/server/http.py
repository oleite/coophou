import json

from ..common import *

from http.server import BaseHTTPRequestHandler, HTTPServer
from PySide6.QtCore import Slot, QThread


class CoopHouHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.send_header("Refresh", "2")
        self.end_headers()

        data = self.server.httpThread.getData()

        response = json.dumps(data, indent=4, default=str)
        self.wfile.write(response.encode("utf-8"))

    def log_message(self, format, *args):
        pass


class HTTPServerThread(QThread):
    def __init__(self):
        super().__init__()
        self._data = {}

    @Slot(dict)
    def updateData(self, data):
        self._data = data

    def getData(self):
        return self._data

    def run(self):
        server_address = ("", HTTP_PORT)
        self.httpd = HTTPServer(server_address, CoopHouHTTPHandler)

        print(f"HTTP Server running on http://127.0.0.1:{HTTP_PORT}")

        # Passamos apenas a thread para o handler, não o CoopHouServer
        self.httpd.httpThread = self
        self.httpd.serve_forever()
