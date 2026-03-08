import sys
import os
import argparse

from PySide6.QtCore import QMargins
import hou

import coophou


def resizeWindow(window, column: int, columnCount: int = 2):
    screen = window.screen()
    geo = screen.availableGeometry()

    windowHandle = window.windowHandle()
    margins = windowHandle.frameMargins() if windowHandle else QMargins(0, 0, 0, 0)

    cellWidth = geo.width() // columnCount

    width = cellWidth - margins.left() - margins.right()
    height = geo.height() - margins.top() - margins.bottom()

    x = geo.x() + (cellWidth * column) + margins.left()
    y = geo.y() + margins.top()

    window.setGeometry(x, y, width, height)


def start(column: int, columnCount: int, asServer: bool = False):
    resizeWindow(hou.qt.mainWindow(), column, columnCount)

    hou.ui.setHideAllMinimizedStowbars(True)

    if asServer:
        coophou.server.start()
    else:
        coophou.client.start()


def startFromEnv():
    if os.getenv("COOPHOU_TESTING") != "1":
        return

    column = int(os.getenv("COOPHOU_TESTING_COLUMN", "0"))
    columnCount = int(os.getenv("COOPHOU_TESTING_COLUMN_COUNT", "2"))
    asServer = os.getenv("COOPHOU_TESTING_AS_SERVER", "0") == "1"

    start(column, columnCount, asServer)
