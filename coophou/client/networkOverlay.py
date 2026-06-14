import hou

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *


class NetworkOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowTransparentForInput
        )

        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.cursor = QLabel("", self)
        self.show()

        self.pixmaps = [
            hou.qt.Icon("BUTTONS_editable", width=32, height=32).pixmap(32, 32),
            hou.qt.Icon("TOP_sendcommand", width=32, height=32).pixmap(32, 32),
        ]

    def refresh(self, cursorPos):
        ne = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)

        if not ne or not cursorPos:
            self.hide()
            return

        geo = ne.qtScreenGeometry()
        size = ne.screenBounds().size()
        geo.setX(geo.x() + geo.width() - size.x())
        geo.setY(geo.y() + geo.height() - size.y())
        geo.setSize(QSize(size.x(), size.y()))

        self.setGeometry(geo)

        bounds = ne.visibleBounds()
        withinBounds = bounds.contains(cursorPos)
        if not withinBounds:
            cursorPos = bounds.closestPoint(cursorPos)

        pos = ne.posToScreen(cursorPos)
        pos = QPoint(pos.x(), ne.screenBounds().size().y() - pos.y())

        self.cursor.move(
            pos - QPoint(self.cursor.width() // 2, self.cursor.height() // 2)
        )
        self.cursor.setPixmap(self.pixmaps[0] if withinBounds else self.pixmaps[1])
