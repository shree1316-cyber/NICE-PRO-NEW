import sys

from PySide6.QtWidgets import *

from PySide6.QtCore import *


class Dashboard(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle("NICE PRO")

        self.resize(1800,950)

        label=QLabel("NICE PRO v0.1")

        label.setAlignment(Qt.AlignCenter)

        self.setCentralWidget(label)


def run_dashboard():

    app=QApplication(sys.argv)

    win=Dashboard()

    win.show()

    sys.exit(app.exec())
