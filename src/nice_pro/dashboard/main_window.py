"""Live-quote dashboard shell for Milestone 2."""

from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QFrame, QGridLayout, QLabel, QMainWindow, QVBoxLayout, QWidget

from nice_pro.models.market import IndicatorSnapshot, MarketSnapshot, OptionChainSnapshot

if TYPE_CHECKING:
    from nice_pro.core.application import Application


class DashboardSignals(QObject):
    snapshot = Signal(object)
    analysis = Signal(object)
    options = Signal(object)
    status = Signal(str)


class MainWindow(QMainWindow):
    def __init__(self, application: "Application") -> None:
        super().__init__()
        self._application = application
        self._signals = DashboardSignals()
        self._signals.snapshot.connect(self.update_snapshot)
        self._signals.analysis.connect(self.update_analysis)
        self._signals.options.connect(self.update_options)
        self._signals.status.connect(self.update_status)
        application.add_snapshot_listener(self._signals.snapshot.emit)
        application.add_analysis_listener(self._signals.analysis.emit)
        application.add_option_listener(self._signals.options.emit)
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
        layout.addWidget(QLabel("Milestone 3 | Market structure | Paper trading only", alignment=Qt.AlignmentFlag.AlignCenter))
        self._status_label = QLabel("Data source: starting", alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._status_label)
        cards = QGridLayout()
        self._nifty_price = self._card("NIFTY", "Waiting for a live quote")
        self._sensex_price = self._card("SENSEX", "Waiting for a live quote")
        cards.addWidget(self._nifty_price[0], 0, 0)
        cards.addWidget(self._sensex_price[0], 0, 1)
        self._nifty_regime = self._card("NIFTY Market Structure", "Waiting for 1-minute history")
        self._sensex_regime = self._card("SENSEX Market Structure", "Waiting for 1-minute history")
        cards.addWidget(self._nifty_regime[0], 1, 0)
        cards.addWidget(self._sensex_regime[0], 1, 1)
        self._nifty_options = self._card("NIFTY Options", "Waiting for ATM option discovery")
        self._sensex_options = self._card("SENSEX Options", "Waiting for ATM option discovery")
        cards.addWidget(self._nifty_options[0], 2, 0)
        cards.addWidget(self._sensex_options[0], 2, 1)
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

    def update_analysis(self, analysis: IndicatorSnapshot) -> None:
        label = self._nifty_regime[1] if analysis.symbol == "NSE:NIFTY 50" else self._sensex_regime[1]
        values = [f"{analysis.regime}"]
        if analysis.vwap is not None:
            values.append(f"VWAP {analysis.vwap:,.2f} | EMA 9/21 {analysis.ema_fast:,.2f} / {analysis.ema_slow:,.2f}")
            values.append(f"RSI {analysis.rsi:.0f} | ATR {analysis.atr:,.2f}")
        values.extend(analysis.reasons[:2])
        label.setText("\n".join(values))

    def update_options(self, chain: OptionChainSnapshot) -> None:
        label = self._nifty_options[1] if chain.underlying == "NIFTY" else self._sensex_options[1]
        values = [f"ATM {chain.atm_strike:,.0f}" if chain.atm_strike is not None else "ATM awaiting spot"]
        if chain.put_call_ratio_oi is not None:
            values.append(f"PCR (OI) {chain.put_call_ratio_oi:.2f}")
        else:
            values.append("PCR (OI) awaiting option ticks")
        if chain.metrics:
            ivs = [metric.implied_volatility for metric in chain.metrics if metric.implied_volatility is not None]
            if ivs:
                values.append(f"Model IV range {min(ivs):.1f}%–{max(ivs):.1f}%")
        label.setText("\n".join(values))

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._application.stop()
        event.accept()


def run_dashboard(application: "Application") -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(application)
    window.show()
    application.start()
    return app.exec()
