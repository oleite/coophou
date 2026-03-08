import sys
import os
import argparse

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


def setupDesktop():
    hou.playbar.showRangeSlider(0)

    for tab in hou.ui.paneTabs():
        tab.close()

    hou.ui.setHideAllMinimizedStowbars(True)
    hou.playbar.showAnimBar(False)

    pane = hou.ui.panes()[0]
    pane.desktop().shelfDock().show(False)
    pane.splitVertically()
    pane.splitVertically()

    panes = hou.ui.panes()

    panes[0].createTab(hou.paneTabType.PythonShell)
    panes[1].createTab(hou.paneTabType.SceneViewer)
    panes[2].createTab(hou.paneTabType.NetworkEditor)

    for p in panes:
        p.setSplitFraction(0.5)
        p.showPaneTabs(False)


def main(column: int, columnCount: int, asServer: bool = False):
    resizeWindow(hou.qt.mainWindow(), column, columnCount)
    setupDesktop()
    
    if asServer:
        coophou.server.addCallbacks()
    else:
        coophou.client.start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Setup Houdini window layout.")
    parser.add_argument("--column", type=int, default=0, help="Column index (0-based)")
    parser.add_argument(
        "--columnCount", type=int, default=2, help="Total number of columns"
    )
    parser.add_argument(
        "--asServer",
        action="store_true",
        help="Indicates if should start in server or client mode",
    )
    args = parser.parse_args()

    from PySide6.QtCore import QTimer

    QTimer.singleShot(5000, lambda: main(args.column, args.columnCount, args.asServer))
