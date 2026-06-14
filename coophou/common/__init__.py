import os
import json

# DEV_MODE = os.getenv("COOPHOU_TESTING") == "1"
DEV_MODE = True
TCP_PORT = 8101
HTTP_PORT = 80

def log(t, msg):
    if not DEV_MODE:
        return

    msg = f"  - {t}".ljust(20) + " | " + str(msg)
    print(msg)


def logSend(msg):
    if DEV_MODE:
        print(f"[!] Sent      >>>   {msg}")


def logReceive(msg):
    if DEV_MODE:
        print(f"[!] Received  <<<   {msg}")


def readData(socket) -> dict:
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
