"""Milestone 1 dashboard shell, intentionally paper-trading only."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QLabel, QMainWindow, QVBoxLayout, QWidget

from nice_pro.config.settings import Settings


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.setWindowTitle("NICE-PRO | Intraday Conviction Engine")
        self.resize(1280, 760)
        root = QWidget()
        layout = QVBoxLayout(root)
        title = QLabel("NICE-PRO")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status = "Kite credentials detected" if settings.kite_configured else "Kite credentials not configured"
        layout.addWidget(title)
        layout.addWidget(QLabel("Milestone 1 • Foundation • Paper trading only", alignment=Qt.AlignmentFlag.AlignCenter))
        layout.addWidget(QLabel(f"Data source: {status}", alignment=Qt.AlignmentFlag.AlignCenter))
        cards = QGridLayout()
        for index, heading in enumerate(("NIFTY", "SENSEX", "Conviction", "Trade Plan")):
            cards.addWidget(self._card(heading), index // 2, index % 2)
        layout.addLayout(cards)
        layout.addStretch()
        self.setCentralWidget(root)
        self.setStyleSheet(
            "QMainWindow { background: #111827; color: #e5e7eb; } QLabel { color: #d1d5db; font-size: 15px; }"
            "QLabel#title { color: #f9fafb; font-size: 30px; font-weight: 700; }"
            "QFrame { background: #1f2937; border: 1px solid #374151; border-radius: 10px; }"
        )

    @staticmethod
    def _card(heading: str) -> QFrame:
        card = QFrame()
        layout = QVBoxLayout(card)
        layout.addWidget(QLabel(heading, styleSheet="font-size: 19px; font-weight: 700; color: #f3f4f6;"))
        layout.addWidget(QLabel("Waiting for Milestone 2 live market data"))
        return card


def run_dashboard(settings: Settings) -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(settings)
    window.show()
    return app.exec()
