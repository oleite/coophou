import sys
import signal
from PySide6.QtCore import QCoreApplication

from . import CoopHouServer

def main():
    app = QCoreApplication(sys.argv)
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    server = CoopHouServer()
    server.start()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()