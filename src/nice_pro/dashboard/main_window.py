"""High-density desktop dashboard designed for a rapid intraday scan."""

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
    QScrollArea,
    QSizePolicy,
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
    """A visual layer only: live values arrive through thread-safe Qt signals."""

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
        self.resize(1600, 980)
        self.setMinimumSize(1180, 760)
        self._build()
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._refresh_clock)
        self._clock.start(1000)
        self._refresh_clock()

    def _build(self) -> None:
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 12, 14, 14)
        root_layout.setSpacing(10)
        root_layout.addWidget(self._header())
        root_layout.addWidget(self._navigation())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        body = QHBoxLayout(content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        body.addWidget(self._sidebar(), 0)
        body.addWidget(self._main_area(), 1)
        scroll.setWidget(content)
        root_layout.addWidget(scroll, 1)
        root_layout.addWidget(self._footer())
        self.setCentralWidget(root)
        self.setStyleSheet(_STYLESHEET)

    def _header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 11, 18, 11)
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
        self._connection_badge = QLabel("CONNECTING")
        self._connection_badge.setObjectName("connectionBadge")
        self._clock_label = QLabel("")
        self._clock_label.setObjectName("clock")
        right.addWidget(self._connection_badge, alignment=Qt.AlignmentFlag.AlignRight)
        right.addWidget(self._clock_label, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(right)
        return header

    @staticmethod
    def _navigation() -> QFrame:
        nav = QFrame()
        nav.setObjectName("navigation")
        layout = QHBoxLayout(nav)
        layout.setContentsMargins(12, 7, 12, 7)
        for index, label in enumerate(("DASHBOARD", "NIFTY", "SENSEX", "OPTIONS", "PAPER TRADE", "JOURNAL", "REPORTS")):
            item = QLabel(label)
            item.setObjectName("navActive" if index == 0 else "navItem")
            layout.addWidget(item)
        layout.addStretch()
        return nav

    def _sidebar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setMinimumWidth(240)
        side.setMaximumWidth(280)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        overview, overview_layout = self._panel("MARKET OVERVIEW", "blue")
        self._overview_nifty = self._market_row(overview_layout, "NIFTY", "--")
        self._overview_sensex = self._market_row(overview_layout, "SENSEX", "--")
        self._overview_status = self._market_row(overview_layout, "STATUS", "Awaiting feed")
        layout.addWidget(overview)

        session, session_layout = self._panel("TIME AND SESSION", "purple")
        self._session_clock = QLabel("--:--:--")
        self._session_clock.setObjectName("sessionClock")
        self._session_note = QLabel("Market data drives the analysis.\nNo live orders are sent.")
        self._session_note.setObjectName("muted")
        session_layout.addWidget(self._session_clock)
        session_layout.addWidget(self._session_note)
        layout.addWidget(session)

        alerts, alerts_layout = self._panel("ALERTS", "amber")
        self._alert_feed = QLabel("No A/A+ paper setup yet.\nAlerts have a cooldown to reduce noise.")
        self._alert_feed.setWordWrap(True)
        self._alert_feed.setObjectName("muted")
        alerts_layout.addWidget(self._alert_feed)
        layout.addWidget(alerts)
        layout.addStretch()
        return side

    def _main_area(self) -> QWidget:
        area = QWidget()
        grid = QGridLayout(area)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
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

        self._nifty_plan = self._plan_card("NIFTY PAPER TRADE PLAN")
        self._sensex_plan = self._plan_card("SENSEX PAPER TRADE PLAN")
        grid.addWidget(self._nifty_plan["panel"], 3, 0)
        grid.addWidget(self._sensex_plan["panel"], 3, 1)

        scalp, scalp_layout = self._panel("SCALP BOX | 10s / 30s", "cyan")
        scalp.setObjectName("widePanel")
        self._scalp_label = QLabel("Scalp engine is reserved for a later milestone.\nUse the conviction panels for the current paper-only setup.")
        self._scalp_label.setObjectName("muted")
        scalp_layout.addWidget(self._scalp_label)
        grid.addWidget(scalp, 4, 0)

        options, options_layout = self._panel("OPTION CHAIN SNAPSHOT", "blue")
        self._option_snapshot = QLabel("Waiting for ATM option discovery and live option ticks.")
        self._option_snapshot.setObjectName("muted")
        self._option_snapshot.setWordWrap(True)
        options_layout.addWidget(self._option_snapshot)
        grid.addWidget(options, 4, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        return area

    def _quote_card(self, title: str, key: str) -> dict[str, object]:
        panel, layout = self._panel(title, "blue")
        panel.setObjectName("quotePanel")
        value = QLabel("--")
        value.setObjectName("quoteValue")
        change = QLabel("Waiting for a live quote")
        change.setObjectName("muted")
        micro = QLabel("Bid / Ask: -- / --")
        micro.setObjectName("micro")
        layout.addWidget(value)
        layout.addWidget(change)
        layout.addWidget(micro)
        return {"panel": panel, "value": value, "change": change, "micro": micro, "key": key}

    def _conviction_card(self, title: str) -> dict[str, object]:
        panel, layout = self._panel(title, "green")
        headline = QLabel("WAIT")
        headline.setObjectName("convictionHeadline")
        score = QLabel("Confidence --")
        score.setObjectName("scoreText")
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        detail = QLabel("Waiting for aligned market and option evidence")
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        layout.addWidget(headline)
        layout.addWidget(score)
        layout.addWidget(bar)
        layout.addWidget(detail)
        return {"panel": panel, "headline": headline, "score": score, "bar": bar, "detail": detail}

    def _evidence_card(self, title: str) -> dict[str, object]:
        panel, layout = self._panel(title, "amber")
        positive = QLabel("Bullish evidence will appear here")
        positive.setObjectName("positiveEvidence")
        negative = QLabel("Bearish evidence will appear here")
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
        detail = QLabel("A plan appears only for A/A+ evidence with a defined risk cap.")
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        layout.addWidget(status)
        layout.addWidget(detail)
        return {"panel": panel, "status": status, "detail": detail}

    @staticmethod
    def _panel(title: str, accent: str) -> tuple[QFrame, QVBoxLayout]:
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setProperty("accent", accent)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(13, 11, 13, 12)
        layout.setSpacing(6)
        heading = QLabel(title)
        heading.setObjectName("panelTitle")
        layout.addWidget(heading)
        return panel, layout

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
        layout.setContentsMargins(12, 7, 12, 7)
        layout.addWidget(QLabel("Data: Zerodha Kite | Mode: PAPER ONLY | Plans are decision support, not orders"))
        layout.addStretch()
        layout.addWidget(QLabel("NICE-PRO"))
        return footer

    def update_snapshot(self, snapshot: MarketSnapshot) -> None:
        self._update_quote(self._nifty_quote, snapshot.quote_for("NSE:NIFTY 50"))
        self._update_quote(self._sensex_quote, snapshot.quote_for("BSE:SENSEX"))

    def _update_quote(self, card: dict[str, object], quote) -> None:  # type: ignore[no-untyped-def]
        if quote is None:
            return
        card["value"].setText(f"{quote.last_price:,.2f}")  # type: ignore[union-attr]
        card["change"].setText("LIVE MARKET QUOTE")  # type: ignore[union-attr]
        card["micro"].setText(f"Bid / Ask: {quote.bid or 0:,.2f} / {quote.ask or 0:,.2f}")  # type: ignore[union-attr]
        overview = self._overview_nifty if card["key"] == "NIFTY" else self._overview_sensex
        overview.setText(f"<span style='color:#94a3b8'>{card['key']}</span><span style='float:right; color:#4ade80'>{quote.last_price:,.2f}</span>")

    def update_status(self, message: str) -> None:
        upper = message.upper()
        connected = "CONNECTED" in upper or "ACTIVE" in upper
        self._connection_badge.setText("KITE CONNECTED" if connected else "DATA STATUS")
        self._connection_badge.setProperty("connected", connected)
        self._connection_badge.style().unpolish(self._connection_badge)
        self._connection_badge.style().polish(self._connection_badge)
        self._overview_status.setText(f"<span style='color:#94a3b8'>STATUS</span><span style='float:right; color:#fbbf24'>{message[:18]}</span>")

    def update_analysis(self, analysis: IndicatorSnapshot) -> None:
        card = self._nifty_conviction if analysis.symbol == "NSE:NIFTY 50" else self._sensex_conviction
        card["detail"].setText(
            f"{analysis.regime} | VWAP {analysis.vwap:,.2f}" if analysis.vwap is not None else str(analysis.regime)
        )  # type: ignore[union-attr]

    def update_options(self, chain: OptionChainSnapshot) -> None:
        metrics = [
            f"{chain.underlying} ATM: {chain.atm_strike:,.0f}" if chain.atm_strike is not None else f"{chain.underlying}: awaiting ATM",
            f"PCR (OI): {chain.put_call_ratio_oi:.2f}" if chain.put_call_ratio_oi is not None else "PCR (OI): warming up",
        ]
        ivs = [metric.implied_volatility for metric in chain.metrics if metric.implied_volatility is not None]
        if ivs:
            metrics.append(f"Model IV: {min(ivs):.1f}% to {max(ivs):.1f}%")
        self._option_snapshot.setText(" | ".join(metrics))

    def update_conviction(self, snapshot: ConvictionSnapshot) -> None:
        conviction = self._nifty_conviction if snapshot.underlying == "NIFTY" else self._sensex_conviction
        evidence = self._nifty_evidence if snapshot.underlying == "NIFTY" else self._sensex_evidence
        plan_card = self._nifty_plan if snapshot.underlying == "NIFTY" else self._sensex_plan
        conviction["headline"].setText(f"{snapshot.grade}  |  {snapshot.side}")  # type: ignore[union-attr]
        conviction["score"].setText(f"Confidence {snapshot.confidence}%   Bull {snapshot.bullish_score} / Bear {snapshot.bearish_score}")  # type: ignore[union-attr]
        conviction["bar"].setValue(snapshot.confidence)  # type: ignore[union-attr]
        conviction["detail"].setText("Paper-only decision support. Wait for confirmation before acting.")  # type: ignore[union-attr]
        evidence["positive"].setText("+ " + ("\n+ ".join(snapshot.bullish_reasons[:3]) or "No bullish evidence"))  # type: ignore[union-attr]
        evidence["negative"].setText("- " + ("\n- ".join(snapshot.bearish_reasons[:3]) or "No bearish evidence"))  # type: ignore[union-attr]
        evidence["caution"].setText(("CAUTION: " + snapshot.conflicts[0]) if snapshot.conflicts else "")  # type: ignore[union-attr]
        if snapshot.plan is None:
            plan_card["status"].setText("NO PAPER SETUP")  # type: ignore[union-attr]
            plan_card["detail"].setText("Need A/A+ grade, an ATM quote, and risk within the configured cap.")  # type: ignore[union-attr]
        else:
            plan = snapshot.plan
            plan_card["status"].setText(f"PAPER ONLY | {plan.option_symbol}")  # type: ignore[union-attr]
            plan_card["detail"].setText(
                f"Entry {plan.entry:.2f} | SL {plan.stop_loss:.2f} | T1 {plan.target_1:.2f} | T2 {plan.target_2:.2f}\n"
                f"Max loss/lot Rs. {plan.max_loss_per_lot:,.0f} | Lot size {plan.lot_size}"
            )  # type: ignore[union-attr]
            self._alert_feed.setText(f"{snapshot.underlying} {snapshot.grade} paper setup\n{plan.option_symbol} | Risk-capped plan available")

    def _refresh_clock(self) -> None:
        now = QDateTime.currentDateTime()
        stamp = now.toString("hh:mm:ss AP | ddd, dd MMM")
        self._clock_label.setText(stamp)
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
QMainWindow { background: #07111f; color: #dce8f8; font-family: 'Segoe UI'; }
QScrollArea { background: transparent; }
QFrame#header { background: #0a1930; border: 1px solid #1f426d; border-radius: 12px; }
QLabel#brand { color: #bca7ff; font-size: 27px; font-weight: 800; letter-spacing: 1px; }
QLabel#subtitle { color: #71839d; font-size: 10px; font-weight: 700; }
QLabel#modeBadge { background: #153b2c; color: #4ade80; border: 1px solid #256b49; border-radius: 7px; padding: 8px 12px; font-weight: 800; }
QLabel#connectionBadge { color: #fbbf24; font-size: 11px; font-weight: 800; }
QLabel#connectionBadge[connected="true"] { color: #4ade80; }
QLabel#clock { color: #cbd5e1; font-size: 12px; }
QFrame#navigation, QFrame#footer { background: #0b1a2d; border: 1px solid #1c3555; border-radius: 8px; }
QLabel#navActive { color: #38bdf8; font-weight: 800; border-bottom: 2px solid #38bdf8; padding: 4px 9px; }
QLabel#navItem { color: #8fa3bd; font-size: 11px; font-weight: 700; padding: 4px 9px; }
QFrame#sidebar { background: #09182a; border: 1px solid #1c3555; border-radius: 10px; }
QFrame#panel { background: #0b1d31; border: 1px solid #1a385b; border-radius: 9px; }
QFrame#panel[accent="green"] { border-top: 2px solid #39895c; }
QFrame#panel[accent="blue"] { border-top: 2px solid #287cb5; }
QFrame#panel[accent="purple"] { border-top: 2px solid #7c55b6; }
QFrame#panel[accent="amber"] { border-top: 2px solid #a6782d; }
QFrame#panel[accent="cyan"] { border-top: 2px solid #22a7b8; }
QFrame#quotePanel { background: #0a2038; }
QLabel#panelTitle { color: #dce8f8; font-size: 12px; font-weight: 800; }
QLabel#quoteValue { color: #f8fafc; font-size: 26px; font-weight: 800; }
QLabel#convictionHeadline { color: #4ade80; font-size: 24px; font-weight: 900; }
QLabel#scoreText { color: #d6e3f1; font-weight: 700; }
QProgressBar { height: 8px; border: 0; border-radius: 4px; background: #172b43; }
QProgressBar::chunk { border-radius: 4px; background: qlineargradient(x1:0, x2:1, stop:0 #f59e0b, stop:0.52 #cbdc3e, stop:1 #22c55e); }
QLabel#positiveEvidence { color: #71e49a; font-size: 12px; }
QLabel#negativeEvidence { color: #fb7185; font-size: 12px; }
QLabel#cautionEvidence { color: #facc15; font-size: 11px; }
QLabel#planStatus { color: #d8b4fe; font-size: 14px; font-weight: 900; }
QLabel#sessionClock { color: #e5e7eb; font-size: 24px; font-weight: 800; }
QLabel#muted, QLabel#micro { color: #93a9c2; font-size: 11px; }
QLabel#marketRow { border-bottom: 1px solid #16304d; padding: 6px 0; font-size: 12px; }
QFrame#footer { color: #71839d; font-size: 11px; }
"""
