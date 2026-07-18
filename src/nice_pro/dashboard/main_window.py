"""Fast-scan desktop dashboard with functional workspace tabs."""

from typing import TYPE_CHECKING

from PySide6.QtCore import QDateTime, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from nice_pro.models.market import ConvictionSnapshot, IndicatorSnapshot, MarketSnapshot, OptionChainSnapshot

if TYPE_CHECKING:
    from nice_pro.core.application import Application


class DashboardSignals(QObject):
    snapshot = Signal(object)
    analysis = Signal(object)
    options = Signal(object)
    conviction = Signal(object)
    status = Signal(str)


class MainWindow(QMainWindow):
    """One-screen dashboard plus focused NIFTY, SENSEX, options and plan tabs."""

    def __init__(self, application: "Application") -> None:
        super().__init__()
        self._application = application
        self._signals = DashboardSignals()
        self._signals.snapshot.connect(self.update_snapshot)
        self._signals.analysis.connect(self.update_analysis)
        self._signals.options.connect(self.update_options)
        self._signals.conviction.connect(self.update_conviction)
        self._signals.status.connect(self.update_status)
        application.add_snapshot_listener(self._signals.snapshot.emit)
        application.add_analysis_listener(self._signals.analysis.emit)
        application.add_option_listener(self._signals.options.emit)
        application.add_conviction_listener(self._signals.conviction.emit)
        application.add_status_listener(self._signals.status.emit)
        self.setWindowTitle("NICE-PRO | Intraday Conviction Engine")
        self.resize(1600, 920)
        self.setMinimumSize(1100, 650)
        self._nav_buttons: list[QPushButton] = []
        self._build()
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._refresh_clock)
        self._clock.start(1000)
        self._refresh_clock()

    def _build(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(8)
        layout.addWidget(self._header())
        layout.addWidget(self._navigation())
        self._pages = QStackedWidget()
        self._pages.addWidget(self._dashboard_page())
        self._pages.addWidget(self._focus_page("NIFTY ANALYSIS", "NIFTY", "NIFTY focus data will appear here."))
        self._pages.addWidget(self._focus_page("SENSEX ANALYSIS", "SENSEX", "SENSEX focus data will appear here."))
        self._pages.addWidget(self._focus_page("OPTION CHAIN", "OPTIONS", "ATM option-chain data will appear here."))
        self._pages.addWidget(self._focus_page("PAPER TRADE", "PAPER", "Paper-only trade plans will appear here."))
        self._pages.addWidget(self._placeholder_page("JOURNAL", "Journal is scheduled for Milestone 6."))
        self._pages.addWidget(self._placeholder_page("REPORTS", "Performance reports are scheduled for Milestone 6."))
        layout.addWidget(self._pages, 1)
        layout.addWidget(self._footer())
        self.setCentralWidget(root)
        self.setStyleSheet(_STYLESHEET)
        self._switch_page(0)

    def _header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 9, 16, 9)
        brand = QVBoxLayout()
        title = QLabel("NICE-PRO")
        title.setObjectName("brand")
        subtitle = QLabel("NIFTY + SENSEX INTRADAY CONVICTION ENGINE")
        subtitle.setObjectName("subtitle")
        brand.addWidget(title)
        brand.addWidget(subtitle)
        layout.addLayout(brand)
        layout.addStretch()
        self._mode_badge = QLabel("PAPER MODE")
        self._mode_badge.setObjectName("modeBadge")
        layout.addWidget(self._mode_badge)
        right = QVBoxLayout()
        self._connection_badge = QLabel("DATA STATUS")
        self._connection_badge.setObjectName("connectionBadge")
        self._clock_label = QLabel("")
        self._clock_label.setObjectName("clock")
        right.addWidget(self._connection_badge, alignment=Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._clock_label, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(right)
        return header

    def _navigation(self) -> QFrame:
        nav = QFrame()
        nav.setObjectName("navigation")
        layout = QHBoxLayout(nav)
        layout.setContentsMargins(10, 5, 10, 5)
        labels = ("DASHBOARD", "NIFTY", "SENSEX", "OPTIONS", "PAPER TRADE", "JOURNAL", "REPORTS")
        for index, label in enumerate(labels):
            button = QPushButton(label)
            button.setObjectName("navButton")
            button.clicked.connect(lambda checked=False, page=index: self._switch_page(page))
            layout.addWidget(button)
            self._nav_buttons.append(button)
        layout.addStretch()
        return nav

    def _dashboard_page(self) -> QWidget:
        page = QWidget()
        body = QHBoxLayout(page)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)
        body.addWidget(self._sidebar(), 0)

        main = QWidget()
        grid = QGridLayout(main)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self._nifty_quote = self._quote_card("NIFTY 50", "NIFTY")
        self._sensex_quote = self._quote_card("SENSEX", "SENSEX")
        grid.addWidget(self._nifty_quote["panel"], 0, 0)
        grid.addWidget(self._sensex_quote["panel"], 0, 1)
        self._nifty_conviction = self._conviction_card("NIFTY INTRADAY CONVICTION")
        self._sensex_conviction = self._conviction_card("SENSEX INTRADAY CONVICTION")
        grid.addWidget(self._nifty_conviction["panel"], 1, 0)
        grid.addWidget(self._sensex_conviction["panel"], 1, 1)
        self._nifty_evidence = self._evidence_card("NIFTY EVIDENCE")
        self._sensex_evidence = self._evidence_card("SENSEX EVIDENCE")
        grid.addWidget(self._nifty_evidence["panel"], 2, 0)
        grid.addWidget(self._sensex_evidence["panel"], 2, 1)
        self._nifty_plan = self._plan_card("NIFTY PAPER PLAN")
        self._sensex_plan = self._plan_card("SENSEX PAPER PLAN")
        grid.addWidget(self._nifty_plan["panel"], 3, 0)
        grid.addWidget(self._sensex_plan["panel"], 3, 1)
        for row, stretch in enumerate((8, 10, 11, 12)):
            grid.setRowStretch(row, stretch)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        body.addWidget(main, 1)
        return page

    def _sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setMinimumWidth(205)
        side.setMaximumWidth(240)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        overview, overview_layout = self._panel("MARKET OVERVIEW", "blue")
        self._overview_nifty = self._market_row(overview_layout, "NIFTY", "--")
        self._overview_sensex = self._market_row(overview_layout, "SENSEX", "--")
        self._overview_status = self._market_row(overview_layout, "STATUS", "Starting")
        layout.addWidget(overview)
        session, session_layout = self._panel("TIME AND SESSION", "purple")
        self._session_clock = QLabel("--:--:--")
        self._session_clock.setObjectName("sessionClock")
        session_layout.addWidget(self._session_clock)
        session_layout.addWidget(self._muted("Paper-only. No live orders are sent."))
        layout.addWidget(session)
        alerts, alerts_layout = self._panel("ALERTS", "amber")
        self._alert_feed = self._muted("No A/A+ paper setup yet.\nAlert cooldown is active.")
        alerts_layout.addWidget(self._alert_feed)
        layout.addWidget(alerts)
        layout.addStretch()
        return side

    def _focus_page(self, title: str, key: str, initial_text: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        panel, panel_layout = self._panel(title, "blue")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        detail = QLabel(initial_text)
        detail.setObjectName("focusDetail")
        detail.setWordWrap(True)
        panel_layout.addWidget(detail)
        panel_layout.addStretch()
        layout.addWidget(panel)
        if key == "NIFTY":
            self._nifty_focus = detail
        elif key == "SENSEX":
            self._sensex_focus = detail
        elif key == "OPTIONS":
            self._options_focus = detail
        else:
            self._paper_focus = detail
        return page

    def _placeholder_page(self, title: str, text: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        panel, panel_layout = self._panel(title, "purple")
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        heading = QLabel("COMING NEXT")
        heading.setObjectName("placeholderHeading")
        panel_layout.addWidget(heading)
        panel_layout.addWidget(self._muted(text))
        panel_layout.addStretch()
        layout.addWidget(panel)
        return page

    def _quote_card(self, title: str, key: str) -> dict[str, object]:
        panel, layout = self._panel(title, "blue")
        value = QLabel("--")
        value.setObjectName("quoteValue")
        state = QLabel("WAITING FOR LIVE QUOTE")
        state.setObjectName("quoteState")
        micro = QLabel("Bid / Ask  -- / --")
        micro.setObjectName("micro")
        layout.addWidget(value)
        layout.addWidget(state)
        layout.addWidget(micro)
        return {"panel": panel, "value": value, "state": state, "micro": micro, "key": key}

    def _conviction_card(self, title: str) -> dict[str, object]:
        panel, layout = self._panel(title, "green")
        headline = QLabel("WAIT")
        headline.setObjectName("convictionHeadline")
        score = QLabel("Confidence -- | Bull -- / Bear --")
        score.setObjectName("scoreText")
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setTextVisible(False)
        detail = self._muted("Waiting for aligned market and option evidence")
        layout.addWidget(headline)
        layout.addWidget(score)
        layout.addWidget(bar)
        layout.addWidget(detail)
        return {"panel": panel, "headline": headline, "score": score, "bar": bar, "detail": detail}

    def _evidence_card(self, title: str) -> dict[str, object]:
        panel, layout = self._panel(title, "amber")
        positive = QLabel("+ Bullish evidence will appear here")
        positive.setObjectName("positiveEvidence")
        negative = QLabel("- Bearish evidence will appear here")
        negative.setObjectName("negativeEvidence")
        caution = QLabel("")
        caution.setObjectName("cautionEvidence")
        for label in (positive, negative, caution):
            label.setWordWrap(True)
            layout.addWidget(label)
        return {"panel": panel, "positive": positive, "negative": negative, "caution": caution}

    def _plan_card(self, title: str) -> dict[str, object]:
        panel, layout = self._panel(title, "purple")
        status = QLabel("NO PAPER SETUP")
        status.setObjectName("planStatus")
        detail = self._muted("A plan requires A/A+ evidence, an ATM quote, and risk inside the configured cap.")
        layout.addWidget(status)
        layout.addWidget(detail)
        return {"panel": panel, "status": status, "detail": detail}

    @staticmethod
    def _panel(title: str, accent: str) -> tuple[QFrame, QVBoxLayout]:
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setProperty("accent", accent)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(11, 9, 11, 9)
        layout.setSpacing(4)
        heading = QLabel(title)
        heading.setObjectName("panelTitle")
        layout.addWidget(heading)
        return panel, layout

    @staticmethod
    def _muted(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("muted")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _market_row(layout: QVBoxLayout, name: str, value: str) -> QLabel:
        row = QLabel(f"<span style='color:#94a3b8'>{name}</span><span style='float:right; color:#e5e7eb'>{value}</span>")
        row.setObjectName("marketRow")
        layout.addWidget(row)
        return row

    @staticmethod
    def _footer() -> QFrame:
        footer = QFrame()
        footer.setObjectName("footer")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.addWidget(QLabel("Data: Zerodha Kite | Mode: PAPER ONLY | Decision support only - no orders"))
        layout.addStretch()
        layout.addWidget(QLabel("NICE-PRO"))
        return footer

    def _switch_page(self, index: int) -> None:
        self._pages.setCurrentIndex(index)
        for position, button in enumerate(self._nav_buttons):
            button.setProperty("active", position == index)
            button.style().unpolish(button)
            button.style().polish(button)

    def update_snapshot(self, snapshot: MarketSnapshot) -> None:
        self._update_quote(self._nifty_quote, snapshot.quote_for("NSE:NIFTY 50"))
        self._update_quote(self._sensex_quote, snapshot.quote_for("BSE:SENSEX"))

    def _update_quote(self, card: dict[str, object], quote) -> None:  # type: ignore[no-untyped-def]
        if quote is None:
            return
        card["value"].setText(f"{quote.last_price:,.2f}")  # type: ignore[union-attr]
        card["state"].setText("LIVE MARKET QUOTE")  # type: ignore[union-attr]
        card["micro"].setText(f"Bid / Ask  {quote.bid or 0:,.2f} / {quote.ask or 0:,.2f}")  # type: ignore[union-attr]
        name = card["key"]
        overview = self._overview_nifty if name == "NIFTY" else self._overview_sensex
        overview.setText(f"<span style='color:#94a3b8'>{name}</span><span style='float:right; color:#4ade80'>{quote.last_price:,.2f}</span>")
        focus = self._nifty_focus if name == "NIFTY" else self._sensex_focus
        focus.setText(f"<b>{name} LIVE</b><br><br>LTP: <b>{quote.last_price:,.2f}</b><br>Bid / Ask: {quote.bid or 0:,.2f} / {quote.ask or 0:,.2f}")

    def update_status(self, message: str) -> None:
        text = message.upper()
        connected = "CONNECTED" in text or "ACTIVE" in text
        self._connection_badge.setText("KITE CONNECTED" if connected else "DATA STATUS")
        self._connection_badge.setProperty("connected", connected)
        self._connection_badge.style().unpolish(self._connection_badge)
        self._connection_badge.style().polish(self._connection_badge)
        self._overview_status.setText(f"<span style='color:#94a3b8'>STATUS</span><span style='float:right; color:#fbbf24'>{message[:18]}</span>")

    def update_analysis(self, analysis: IndicatorSnapshot) -> None:
        card = self._nifty_conviction if analysis.symbol == "NSE:NIFTY 50" else self._sensex_conviction
        text = f"{analysis.regime} | VWAP {analysis.vwap:,.2f}" if analysis.vwap is not None else str(analysis.regime)
        card["detail"].setText(text)  # type: ignore[union-attr]
        focus = self._nifty_focus if analysis.symbol == "NSE:NIFTY 50" else self._sensex_focus
        if analysis.vwap is not None:
            focus.setText(
                f"<b>{analysis.symbol}</b><br><br>Regime: <b>{analysis.regime}</b><br>VWAP: {analysis.vwap:,.2f}<br>"
                f"EMA 9 / 21: {analysis.ema_fast:,.2f} / {analysis.ema_slow:,.2f}<br>RSI: {analysis.rsi:.0f} | ATR: {analysis.atr:,.2f}"
            )

    def update_options(self, chain: OptionChainSnapshot) -> None:
        data = [
            f"<b>{chain.underlying} ATM</b>: {chain.atm_strike:,.0f}" if chain.atm_strike is not None else f"<b>{chain.underlying}</b>: awaiting ATM",
            f"PCR (OI): {chain.put_call_ratio_oi:.2f}" if chain.put_call_ratio_oi is not None else "PCR (OI): warming up",
        ]
        ivs = [metric.implied_volatility for metric in chain.metrics if metric.implied_volatility is not None]
        if ivs:
            data.append(f"Model IV: {min(ivs):.1f}% to {max(ivs):.1f}%")
        self._options_focus.setText("<br><br>".join(data))

    def update_conviction(self, snapshot: ConvictionSnapshot) -> None:
        conviction = self._nifty_conviction if snapshot.underlying == "NIFTY" else self._sensex_conviction
        evidence = self._nifty_evidence if snapshot.underlying == "NIFTY" else self._sensex_evidence
        plan_card = self._nifty_plan if snapshot.underlying == "NIFTY" else self._sensex_plan
        conviction["headline"].setText(f"{snapshot.grade} | {snapshot.side}")  # type: ignore[union-attr]
        conviction["score"].setText(f"Confidence {snapshot.confidence}%   Bull {snapshot.bullish_score} / Bear {snapshot.bearish_score}")  # type: ignore[union-attr]
        conviction["bar"].setValue(snapshot.confidence)  # type: ignore[union-attr]
        evidence["positive"].setText("+ " + ("\n+ ".join(snapshot.bullish_reasons[:3]) or "No bullish evidence"))  # type: ignore[union-attr]
        evidence["negative"].setText("- " + ("\n- ".join(snapshot.bearish_reasons[:3]) or "No bearish evidence"))  # type: ignore[union-attr]
        evidence["caution"].setText(("CAUTION: " + snapshot.conflicts[0]) if snapshot.conflicts else "")  # type: ignore[union-attr]
        if snapshot.plan is None:
            plan_card["status"].setText("NO PAPER SETUP")  # type: ignore[union-attr]
            plan_card["detail"].setText("Need A/A+ grade, ATM quote, and risk inside the configured cap.")  # type: ignore[union-attr]
        else:
            plan = snapshot.plan
            plan_card["status"].setText(f"PAPER ONLY | {plan.option_symbol}")  # type: ignore[union-attr]
            plan_card["detail"].setText(
                f"Entry {plan.entry:.2f} | SL {plan.stop_loss:.2f} | T1 {plan.target_1:.2f} | T2 {plan.target_2:.2f}\n"
                f"Max loss/lot Rs. {plan.max_loss_per_lot:,.0f} | Lot {plan.lot_size}"
            )  # type: ignore[union-attr]
            self._alert_feed.setText(f"{snapshot.underlying} {snapshot.grade} paper setup\n{plan.option_symbol} | Risk-capped plan available")
            self._paper_focus.setText(
                f"<b>{snapshot.underlying} PAPER PLAN</b><br><br>{plan.option_symbol}<br>Entry: {plan.entry:.2f}<br>"
                f"Stop Loss: {plan.stop_loss:.2f}<br>Target 1: {plan.target_1:.2f}<br>Target 2: {plan.target_2:.2f}<br>"
                f"Maximum loss/lot: Rs. {plan.max_loss_per_lot:,.0f}<br><br><i>No order is submitted.</i>"
            )

    def _refresh_clock(self) -> None:
        now = QDateTime.currentDateTime()
        self._clock_label.setText(now.toString("hh:mm:ss AP | ddd, dd MMM"))
        self._session_clock.setText(now.toString("hh:mm:ss AP"))

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._application.stop()
        event.accept()


def run_dashboard(application: "Application") -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(application)
    window.show()
    application.start()
    return app.exec()


_STYLESHEET = """
QMainWindow { background: #000000; color: #e5edf8; font-family: 'Segoe UI'; }
QFrame#header { background: #050d17; border: 1px solid #164a7a; border-radius: 11px; }
QLabel#brand { color: #b59cff; font-size: 26px; font-weight: 900; letter-spacing: 1px; }
QLabel#subtitle { color: #7194bd; font-size: 10px; font-weight: 700; }
QLabel#modeBadge { background: #103d2a; color: #4ade80; border: 1px solid #28714d; border-radius: 6px; padding: 8px 12px; font-weight: 900; }
QLabel#connectionBadge { color: #facc15; font-size: 11px; font-weight: 900; }
QLabel#connectionBadge[connected="true"] { color: #4ade80; }
QLabel#clock { color: #cbd5e1; font-size: 11px; }
QFrame#navigation, QFrame#footer { background: #050d17; border: 1px solid #173657; border-radius: 8px; }
QPushButton#navButton { background: transparent; color: #8ea4be; border: none; border-radius: 5px; padding: 7px 11px; font-size: 11px; font-weight: 800; }
QPushButton#navButton:hover { color: #d7efff; background: #0b2944; }
QPushButton#navButton[active="true"] { color: #38bdf8; background: #082940; border-bottom: 2px solid #38bdf8; }
QFrame#sidebar { background: #030a12; border: 1px solid #16395d; border-radius: 9px; }
QFrame#panel { background: #071627; border: 1px solid #164269; border-radius: 8px; }
QFrame#panel[accent="green"] { border-top: 2px solid #3fa76b; }
QFrame#panel[accent="blue"] { border-top: 2px solid #2589cf; }
QFrame#panel[accent="purple"] { border-top: 2px solid #9b63e5; }
QFrame#panel[accent="amber"] { border-top: 2px solid #d79c2f; }
QLabel#panelTitle { color: #f2f6fb; font-size: 12px; font-weight: 900; }
QLabel#quoteValue { color: #f8fafc; font-size: 25px; font-weight: 900; }
QLabel#quoteState { color: #52d8ff; font-size: 10px; font-weight: 800; }
QLabel#convictionHeadline { color: #4ade80; font-size: 22px; font-weight: 900; }
QLabel#scoreText { color: #dce8f6; font-size: 11px; font-weight: 800; }
QProgressBar { height: 7px; border: 0; border-radius: 3px; background: #142942; }
QProgressBar::chunk { border-radius: 3px; background: qlineargradient(x1:0, x2:1, stop:0 #f59e0b, stop:0.55 #b9d43e, stop:1 #22c55e); }
QLabel#positiveEvidence { color: #62e99a; font-size: 11px; }
QLabel#negativeEvidence { color: #fb7185; font-size: 11px; }
QLabel#cautionEvidence { color: #facc15; font-size: 10px; }
QLabel#planStatus { color: #d8b4fe; font-size: 13px; font-weight: 900; }
QLabel#sessionClock { color: #f8fafc; font-size: 22px; font-weight: 900; }
QLabel#muted, QLabel#micro { color: #94a9c2; font-size: 10px; }
QLabel#marketRow { border-bottom: 1px solid #123250; padding: 5px 0; font-size: 11px; }
QLabel#focusDetail { color: #dbeafe; font-size: 15px; }
QLabel#placeholderHeading { color: #b59cff; font-size: 24px; font-weight: 900; }
QFrame#footer { color: #71839d; font-size: 10px; }
"""
