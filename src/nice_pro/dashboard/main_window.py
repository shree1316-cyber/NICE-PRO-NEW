"""Live-quote dashboard shell for Milestone 2."""

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QLabel, QMainWindow, QVBoxLayout, QWidget

from nice_pro.models.market import MarketSnapshot

if TYPE_CHECKING:
    from nice_pro.core.application import Application


class DashboardSignals(QObject):
    snapshot = Signal(object)
    status = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self, application: "Application") -> None:
        super().__init__()
        self._application = application
        self._signals = DashboardSignals()
        self._signals.snapshot.connect(self.update_snapshot)
        self._signals.status.connect(self.update_status)
        application.add_snapshot_listener(self._signals.snapshot.emit)
        application.add_status_listener(self._signals.status.emit)
        self.setWindowTitle("NICE-PRO | Intraday Conviction Engine")
        self.resize(1280, 760)
        self._build()

    def _build(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        title = QLabel("NICE-PRO")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addWidget(QLabel("Milestone 2 | Live quotes | Paper trading only", alignment=Qt.AlignmentFlag.AlignCenter))
        self._status_label = QLabel("Data source: starting", alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)
        cards = QGridLayout()
        self._nifty_price = self._card("NIFTY", "Waiting for a live quote")
        self._sensex_price = self._card("SENSEX", "Waiting for a live quote")
        cards.addWidget(self._nifty_price[0], 0, 0)
        cards.addWidget(self._sensex_price[0], 0, 1)
        cards.addWidget(self._card("Conviction", "Scheduled for Milestone 4")[0], 1, 0)
        cards.addWidget(self._card("Trade Plan", "Scheduled for Milestone 5")[0], 1, 1)
        layout.addLayout(cards)
        layout.addStretch()
        self.setCentralWidget(root)
        self.setStyleSheet(
            "QMainWindow { background: #111827; color: #e5e7eb; } QLabel { color: #d1d5db; font-size: 15px; }"
            "QLabel#title { color: #f9fafb; font-size: 30px; font-weight: 700; }"
            "QFrame { background: #1f2937; border: 1px solid #374151; border-radius: 10px; }"
        )

    @staticmethod
    def _card(heading: str, detail: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        layout = QVBoxLayout(card)
        layout.addWidget(QLabel(heading, styleSheet="font-size: 19px; font-weight: 700; color: #f3f4f6;"))
        detail_label = QLabel(detail)
        layout.addWidget(detail_label)
        return card, detail_label

    def update_snapshot(self, snapshot: MarketSnapshot) -> None:
        self._update_price(self._nifty_price[1], snapshot.quote_for("NSE:NIFTY 50"))
        self._update_price(self._sensex_price[1], snapshot.quote_for("BSE:SENSEX"))

    @staticmethod
    def _update_price(label: QLabel, quote) -> None:  # type: ignore[no-untyped-def]
        if quote is not None:
            label.setText(f"LTP  {quote.last_price:,.2f}\nBid/Ask  {quote.bid or 0:,.2f} / {quote.ask or 0:,.2f}")

    def update_status(self, message: str) -> None:
        self._status_label.setText(f"Data source: {message}")

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._application.stop()
        event.accept()


def run_dashboard(application: "Application") -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(application)
    window.show()
    application.start()
    return app.exec()
