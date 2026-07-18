"""Fast-scan PySide6 workspaces for the paper-only NICE-PRO engine."""

from datetime import datetime, time
from typing import TYPE_CHECKING

from PySide6.QtCore import QDateTime, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from nice_pro.models.market import (
    ConvictionSnapshot,
    IndicatorSnapshot,
    MarketSnapshot,
    OptionChainSnapshot,
    OptionMetric,
    OptionType,
    Quote,
)

if TYPE_CHECKING:
    from nice_pro.core.application import Application


class DashboardSignals(QObject):
    snapshot = Signal(object)
    analysis = Signal(object)
    options = Signal(object)
    conviction = Signal(object)
    status = Signal(str)


class ConvictionGauge(QWidget):
    """Compact semi-circle that keeps the directional score easy to scan."""

    def __init__(self) -> None:
        super().__init__()
        self._score = 0
        self.setMinimumSize(150, 92)
        self.setMaximumHeight(120)

    def set_score(self, score: int) -> None:
        self._score = max(0, min(100, score))
        self.update()

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(16, 12, -16, -2)
        rect.setHeight(rect.width() // 2)
        painter.setPen(QPen(QColor("#243b53"), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 30 * 16, 120 * 16)
        color = QColor("#22c55e") if self._score >= 55 else QColor("#f59e0b") if self._score >= 40 else QColor("#ef4444")
        painter.setPen(QPen(color, 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawArc(rect, 30 * 16, int(120 * 16 * self._score / 100))
        painter.setPen(QColor("#e5edf8"))
        font = painter.font()
        font.setPointSize(21)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect().adjusted(0, 24, 0, 0), Qt.AlignmentFlag.AlignHCenter, str(self._score))
        painter.end()


class MainWindow(QMainWindow):
    """Dashboard plus live NIFTY, SENSEX, option-chain and plan workspaces."""

    def __init__(self, application: "Application") -> None:
        super().__init__()
        self._application = application
        self._signals = DashboardSignals()
        self._quotes: dict[str, Quote] = {}
        self._analyses: dict[str, IndicatorSnapshot] = {}
        self._chains: dict[str, OptionChainSnapshot] = {}
        self._convictions: dict[str, ConvictionSnapshot] = {}
        self._kite_connected = False
        self._nav_buttons: list[QPushButton] = []
        self._analysis_views: dict[str, dict[str, object]] = {}
        self._option_tables: dict[str, QTableWidget] = {}
        self._option_summaries: dict[str, QLabel] = {}
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
        self._pages.addWidget(self._analysis_page("NIFTY"))
        self._pages.addWidget(self._analysis_page("SENSEX"))
        self._pages.addWidget(self._options_page())
        self._pages.addWidget(self._paper_page())
        self._pages.addWidget(self._placeholder_page("JOURNAL", "Journal and annotated review arrive in the next research milestone."))
        self._pages.addWidget(self._placeholder_page("REPORTS", "Performance reports are scheduled after paper-trade data is collected."))
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
        for index, label in enumerate(("DASHBOARD", "NIFTY", "SENSEX", "OPTIONS", "PAPER TRADE", "JOURNAL", "REPORTS")):
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
        self._nifty_conviction = self._conviction_card("NIFTY INTRADAY CONVICTION")
        self._sensex_conviction = self._conviction_card("SENSEX INTRADAY CONVICTION")
        self._nifty_evidence = self._evidence_card("NIFTY EVIDENCE")
        self._sensex_evidence = self._evidence_card("SENSEX EVIDENCE")
        self._nifty_plan = self._plan_card("NIFTY PAPER PLAN")
        self._sensex_plan = self._plan_card("SENSEX PAPER PLAN")
        for row, widgets in enumerate(((self._nifty_quote, self._sensex_quote), (self._nifty_conviction, self._sensex_conviction), (self._nifty_evidence, self._sensex_evidence), (self._nifty_plan, self._sensex_plan))):
            grid.addWidget(widgets[0]["panel"], row, 0)  # type: ignore[arg-type]
            grid.addWidget(widgets[1]["panel"], row, 1)  # type: ignore[arg-type]
        for row, stretch in enumerate((8, 10, 11, 12)):
            grid.setRowStretch(row, stretch)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        body.addWidget(main, 1)
        body.addWidget(self._rightbar(), 0)
        return page

    def _analysis_page(self, underlying: str) -> QWidget:
        """Full live workspace for a single underlying, rather than a placeholder."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        top = QGridLayout()
        top.setSpacing(8)
        live_panel, live_layout = self._panel(f"{underlying} LIVE MARKET", "blue")
        live = QLabel("Waiting for a live quote")
        live.setObjectName("workspaceQuote")
        quote_meta = self._muted("Bid / Ask: — / —")
        live_layout.addWidget(live)
        live_layout.addWidget(quote_meta)
        score_panel, score_layout = self._panel("CONVICTION, SCORE & GRADE", "green")
        score = QLabel("WAIT | Score unavailable")
        score.setObjectName("workspaceScore")
        score_meta = self._muted("Need aligned market and option evidence")
        score_layout.addWidget(score)
        score_layout.addWidget(score_meta)
        option_panel, option_layout = self._panel("OPTION CONTEXT", "purple")
        option_summary = self._muted("Waiting for ATM option discovery")
        option_layout.addWidget(option_summary)
        top.addWidget(live_panel, 0, 0)
        top.addWidget(score_panel, 0, 1)
        top.addWidget(option_panel, 0, 2)
        for col in range(3):
            top.setColumnStretch(col, 1)
        layout.addLayout(top)
        middle = QHBoxLayout()
        indicators_panel, indicators_layout = self._panel("100-INDICATOR MATRIX", "blue")
        indicator_summary = self._muted("Live price/candle indicators plus explicit feed requirements for volume, options and order-flow indicators.")
        indicators_layout.addWidget(indicator_summary)
        indicator_tabs = QTabWidget()
        indicator_tabs.setObjectName("chainTabs")
        indicator_tables: dict[str, QTableWidget] = {}
        for category in ("Trend", "Momentum", "Volatility", "Levels", "Volume", "Options & Flow"):
            table = self._indicator_table()
            indicator_tabs.addTab(table, category)
            indicator_tables[category] = table
        indicators_layout.addWidget(indicator_tabs, 1)
        middle.addWidget(indicators_panel, 3)
        reasons_panel, reasons_layout = self._panel("EVIDENCE & CONFLICTS", "amber")
        reasons = QLabel("Waiting for conviction evaluation")
        reasons.setObjectName("workspaceReasons")
        reasons.setWordWrap(True)
        reasons_layout.addWidget(reasons)
        middle.addWidget(reasons_panel, 2)
        plan_panel, plan_layout = self._panel("PAPER TRADE PLAN", "purple")
        plan = QLabel("No paper setup")
        plan.setObjectName("workspacePlan")
        plan.setWordWrap(True)
        plan_layout.addWidget(plan)
        middle.addWidget(plan_panel, 2)
        layout.addLayout(middle, 1)
        self._analysis_views[underlying] = {"live": live, "quote_meta": quote_meta, "score": score, "score_meta": score_meta, "option": option_summary, "indicator_summary": indicator_summary, "indicator_tables": indicator_tables, "reasons": reasons, "plan": plan}
        return page

    def _options_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        heading, heading_layout = self._panel("LIVE OPTION CHAIN — OBSERVED STRIKES", "purple")
        heading_layout.addWidget(self._muted("Live LTP, OI, session OI delta, model IV and premium velocity. Values use the currently subscribed ATM range; no order is submitted."))
        layout.addWidget(heading)
        tabs = QTabWidget()
        tabs.setObjectName("chainTabs")
        for underlying in ("NIFTY", "SENSEX"):
            tab = QWidget()
            tab_layout = QVBoxLayout(tab)
            tab_layout.setContentsMargins(6, 6, 6, 6)
            summary = QLabel("Waiting for live option-chain data")
            summary.setObjectName("chainSummary")
            summary.setWordWrap(True)
            tab_layout.addWidget(summary)
            table = self._option_table()
            tab_layout.addWidget(table, 1)
            tabs.addTab(tab, underlying)
            self._option_summaries[underlying] = summary
            self._option_tables[underlying] = table
        layout.addWidget(tabs, 1)
        return page

    def _option_table(self) -> QTableWidget:
        headers = ("CALL LTP", "CALL OI", "CALL ΔOI", "CALL IV", "CALL Vel", "STRIKE", "PUT Vel", "PUT IV", "PUT ΔOI", "PUT OI", "PUT LTP")
        table = QTableWidget(0, len(headers))
        table.setObjectName("optionTable")
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    def _indicator_table(self) -> QTableWidget:
        table = QTableWidget(0, 4)
        table.setObjectName("indicatorTable")
        table.setHorizontalHeaderLabels(("INDICATOR", "LIVE VALUE", "STATE", "REASON"))
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        return table

    def _paper_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for underlying in ("NIFTY", "SENSEX"):
            panel, panel_layout = self._panel(f"{underlying} PAPER-TRADE PLAN", "purple")
            detail = QLabel("No paper setup yet")
            detail.setObjectName("workspacePlan")
            detail.setWordWrap(True)
            panel_layout.addWidget(detail)
            panel_layout.addStretch()
            layout.addWidget(panel)
            self._analysis_views.setdefault(underlying, {})["paper"] = detail
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
        breadth, breadth_layout = self._panel("MARKET BREADTH", "green")
        breadth_layout.addWidget(self._muted("Not connected yet\nAdvance/decline feed arrives in the market-data milestone."))
        layout.addWidget(breadth)
        layout.addStretch()
        return side

    def _rightbar(self) -> QFrame:
        side = QFrame()
        side.setObjectName("sidebar")
        side.setMinimumWidth(180)
        side.setMaximumWidth(210)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        session, session_layout = self._panel("TIME AND SESSION", "blue")
        self._right_clock = QLabel("--:--:--")
        self._right_clock.setObjectName("sessionClock")
        session_layout.addWidget(self._right_clock)
        session_layout.addWidget(self._muted("Intraday session\n09:15 AM - 03:30 PM"))
        layout.addWidget(session)
        system, system_layout = self._panel("SYSTEM STATUS", "green")
        self._system_status = self._muted("Kite: Connecting\nData: Waiting\nOrder status: Paper mode\nEngine: Active")
        system_layout.addWidget(self._system_status)
        layout.addWidget(system)
        pending, pending_layout = self._panel("PENDING DATA FEEDS", "purple")
        pending_layout.addWidget(self._muted("India VIX\nIndex futures\nMarket breadth\nGlobal cues\nBook imbalance"))
        layout.addWidget(pending)
        notices, notices_layout = self._panel("NOTIFICATIONS", "amber")
        notices_layout.addWidget(self._muted("All recommendations are decision support only. Verify the evidence and risk before acting."))
        layout.addWidget(notices)
        layout.addStretch()
        return side

    def _quote_card(self, title: str, key: str) -> dict[str, object]:
        panel, layout = self._panel(title, "blue")
        value = QLabel("--")
        value.setObjectName("quoteValue")
        state = QLabel("WAITING FOR LIVE QUOTE")
        state.setObjectName("quoteState")
        micro = QLabel("Bid / Ask  — / —")
        micro.setObjectName("micro")
        layout.addWidget(value)
        layout.addWidget(state)
        layout.addWidget(micro)
        return {"panel": panel, "value": value, "state": state, "micro": micro, "key": key}

    def _conviction_card(self, title: str) -> dict[str, object]:
        panel, layout = self._panel(title, "green")
        content = QHBoxLayout()
        gauge = ConvictionGauge()
        content.addWidget(gauge, 0)
        details = QVBoxLayout()
        headline = QLabel("WAIT")
        headline.setObjectName("convictionHeadline")
        score = QLabel("Confidence -- | Bull -- / Bear --")
        score.setObjectName("scoreText")
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setTextVisible(False)
        detail = self._muted("Waiting for aligned market and option evidence")
        details.addWidget(headline)
        details.addWidget(score)
        details.addWidget(bar)
        details.addWidget(detail)
        content.addLayout(details, 1)
        layout.addLayout(content)
        return {"panel": panel, "headline": headline, "score": score, "bar": bar, "detail": detail, "gauge": gauge}

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
        self._quotes = snapshot.quotes.copy()
        self._update_quote(self._nifty_quote, snapshot.quote_for("NSE:NIFTY 50"))
        self._update_quote(self._sensex_quote, snapshot.quote_for("BSE:SENSEX"))
        self._refresh_analysis_view("NIFTY")
        self._refresh_analysis_view("SENSEX")

    def _update_quote(self, card: dict[str, object], quote: Quote | None) -> None:
        if quote is None:
            return
        card["value"].setText(f"{quote.last_price:,.2f}")  # type: ignore[union-attr]
        card["state"].setText("LIVE MARKET QUOTE" if _market_is_open() else "LAST RECEIVED QUOTE — MARKET CLOSED")  # type: ignore[union-attr]
        card["micro"].setText(f"Bid / Ask  {_price_or_dash(quote.bid)} / {_price_or_dash(quote.ask)}")  # type: ignore[union-attr]
        name = card["key"]
        overview = self._overview_nifty if name == "NIFTY" else self._overview_sensex
        overview.setText(f"<span style='color:#94a3b8'>{name}</span><span style='float:right; color:#4ade80'>{quote.last_price:,.2f}</span>")

    def update_status(self, message: str) -> None:
        text = message.upper()
        if "CONNECTED" in text or "LIVE QUOTE STREAM ACTIVE" in text:
            self._kite_connected = True
        elif "RECONNECTING" in text or "CLOSED" in text or "ERROR" in text or "LIMIT REACHED" in text:
            self._kite_connected = False
        self._connection_badge.setText("KITE CONNECTED" if self._kite_connected else "DATA STATUS")
        self._connection_badge.setProperty("connected", self._kite_connected)
        self._connection_badge.style().unpolish(self._connection_badge)
        self._connection_badge.style().polish(self._connection_badge)
        self._overview_status.setText(f"<span style='color:#94a3b8'>STATUS</span><span style='float:right; color:#fbbf24'>{message[:18]}</span>")
        connection = "Connected" if self._kite_connected else "Connecting"
        self._system_status.setText(f"Kite: {connection}\nData: {message[:28]}\nOrder status: Paper mode\nEngine: Active")

    def update_analysis(self, analysis: IndicatorSnapshot) -> None:
        underlying = _underlying_for_symbol(analysis.symbol)
        self._analyses[underlying] = analysis
        card = self._nifty_conviction if underlying == "NIFTY" else self._sensex_conviction
        card["detail"].setText(_analysis_summary(analysis))  # type: ignore[union-attr]
        self._refresh_analysis_view(underlying)

    def update_options(self, chain: OptionChainSnapshot) -> None:
        self._chains[chain.underlying] = chain
        self._refresh_option_table(chain)
        self._refresh_analysis_view(chain.underlying)

    def update_conviction(self, snapshot: ConvictionSnapshot) -> None:
        self._convictions[snapshot.underlying] = snapshot
        conviction = self._nifty_conviction if snapshot.underlying == "NIFTY" else self._sensex_conviction
        evidence = self._nifty_evidence if snapshot.underlying == "NIFTY" else self._sensex_evidence
        plan_card = self._nifty_plan if snapshot.underlying == "NIFTY" else self._sensex_plan
        conviction["headline"].setText(f"{snapshot.grade} | {snapshot.side}")  # type: ignore[union-attr]
        matrix_bull, matrix_bear, matrix_names = _matrix_state_counts(
            self._analyses.get(snapshot.underlying), self._chains.get(snapshot.underlying)
        )
        conviction["score"].setText(f"Core: Bull {snapshot.bullish_score} / Bear {snapshot.bearish_score} | Matrix: Bull {matrix_bull} / Bear {matrix_bear}")  # type: ignore[union-attr]
        conviction["bar"].setValue(snapshot.confidence)  # type: ignore[union-attr]
        gauge_score = snapshot.bullish_score if str(snapshot.side) == "BUY" else snapshot.bearish_score
        conviction["gauge"].set_score(gauge_score)  # type: ignore[union-attr]
        evidence["positive"].setText("+ " + ("\n+ ".join(snapshot.bullish_reasons[:3]) or "No bullish evidence"))  # type: ignore[union-attr]
        evidence["negative"].setText("- " + ("\n- ".join(snapshot.bearish_reasons[:3]) or "No bearish evidence"))  # type: ignore[union-attr]
        caution = ("CAUTION: " + snapshot.conflicts[0]) if snapshot.conflicts else ""
        if matrix_bear:
            matrix_note = f"MATRIX WATCH ({matrix_bear} bearish, not core-score votes): " + ", ".join(matrix_names[:3])
            caution = f"{caution}\n{matrix_note}" if caution else matrix_note
        evidence["caution"].setText(caution)  # type: ignore[union-attr]
        self._render_dashboard_plan(snapshot, plan_card)
        self._refresh_analysis_view(snapshot.underlying)

    def _render_dashboard_plan(self, snapshot: ConvictionSnapshot, card: dict[str, object]) -> None:
        if snapshot.plan is None:
            card["status"].setText("NO PAPER SETUP")  # type: ignore[union-attr]
            card["detail"].setText("Need A/A+ grade, ATM quote, and risk inside the configured cap.")  # type: ignore[union-attr]
            return
        plan = snapshot.plan
        card["status"].setText(f"PAPER ONLY | {plan.option_symbol}")  # type: ignore[union-attr]
        card["detail"].setText(f"Entry {plan.entry:.2f} | SL {plan.stop_loss:.2f} | T1 {plan.target_1:.2f} | T2 {plan.target_2:.2f}\nMax loss/lot Rs. {plan.max_loss_per_lot:,.0f} | Lot {plan.lot_size}")  # type: ignore[union-attr]
        self._alert_feed.setText(f"{snapshot.underlying} {snapshot.grade} paper setup\n{plan.option_symbol} | Risk-capped plan available")

    def _refresh_analysis_view(self, underlying: str) -> None:
        view = self._analysis_views.get(underlying)
        if not view:
            return
        quote = self._quotes.get("NSE:NIFTY 50" if underlying == "NIFTY" else "BSE:SENSEX")
        analysis = self._analyses.get(underlying)
        chain = self._chains.get(underlying)
        conviction = self._convictions.get(underlying)
        if quote is not None:
            view["live"].setText(f"{quote.last_price:,.2f}")
            view["quote_meta"].setText(f"Bid / Ask: {_price_or_dash(quote.bid)} / {_price_or_dash(quote.ask)} | Live Kite quote")
        if analysis is not None:
            view["indicator_summary"].setText(f"{len(analysis.readings)} configured rows | completed one-minute data updated {analysis.calculated_at.strftime('%H:%M:%S')}")  # type: ignore[union-attr]
            self._refresh_indicator_tables(view["indicator_tables"], analysis, chain)  # type: ignore[arg-type]
        if chain is not None:
            view["option"].setText(_option_summary_html(chain))
        if conviction is not None:
            matrix_bull, matrix_bear, matrix_names = _matrix_state_counts(analysis, chain)
            view["score"].setText(f"{conviction.grade} | {conviction.side} | Core Bull {conviction.bullish_score} / Bear {conviction.bearish_score}")
            view["score_meta"].setText(f"Core confidence {conviction.confidence}% | Matrix: Bull {matrix_bull} / Bear {matrix_bear}")
            view["reasons"].setText(_reason_html(conviction, matrix_bear, matrix_names))
            plan_text = _plan_html(conviction)
            view["plan"].setText(plan_text)
            if "paper" in view:
                view["paper"].setText(plan_text)  # type: ignore[union-attr]

    def _refresh_indicator_tables(
        self, tables: dict[str, QTableWidget], analysis: IndicatorSnapshot, chain: OptionChainSnapshot | None
    ) -> None:
        """Render every configured reading once, grouped by indicator category."""
        for category, table in tables.items():
            readings = [reading for reading in analysis.readings if reading.category == category]
            overrides = _option_indicator_overrides(chain) if category == "Options & Flow" and chain is not None else {}
            table.setRowCount(len(readings))
            for row, reading in enumerate(readings):
                value, state, reason = overrides.get(reading.name, (reading.value, reading.state, reading.reason))
                state_color = {
                    "BULLISH": "#67e8a5", "BEARISH": "#fda4af", "NEUTRAL": "#facc15",
                    "FEED REQUIRED": "#94a3b8", "WAITING": "#94a3b8",
                }.get(state, "#cfe8ff")
                for column, text in enumerate((reading.name, value, state, reason)):
                    item = QTableWidgetItem(text)
                    item.setForeground(QColor(state_color if column in (1, 2) else "#dce8f6"))
                    table.setItem(row, column, item)

    def _refresh_option_table(self, chain: OptionChainSnapshot) -> None:
        summary = self._option_summaries.get(chain.underlying)
        table = self._option_tables.get(chain.underlying)
        if summary is None or table is None:
            return
        summary.setText(_option_summary_html(chain))
        by_strike: dict[float, dict[OptionType, OptionMetric]] = {}
        for metric in chain.metrics:
            by_strike.setdefault(metric.contract.strike, {})[metric.contract.option_type] = metric
        # Contract discovery occurs before every option receives its first tick.
        # Preserve those strike rows so an empty table never looks like a broken
        # option-chain subscription; pending fields remain an honest em dash.
        strikes = sorted(set(chain.observed_strikes) | set(by_strike))
        table.setRowCount(len(strikes))
        for row, strike in enumerate(strikes):
            call = by_strike.get(strike, {}).get(OptionType.CALL)
            put = by_strike.get(strike, {}).get(OptionType.PUT)
            cells = (_metric_ltp(call), _metric_oi(call), _metric_oi_change(call), _metric_iv(call), _metric_velocity(call), f"{strike:,.0f}", _metric_velocity(put), _metric_iv(put), _metric_oi_change(put), _metric_oi(put), _metric_ltp(put))
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if column == 5:
                    item.setForeground(QColor("#facc15"))
                elif column in (0, 1, 2, 3, 4):
                    item.setForeground(QColor("#67e8a5"))
                else:
                    item.setForeground(QColor("#fda4af"))
                table.setItem(row, column, item)

    def _refresh_clock(self) -> None:
        now = QDateTime.currentDateTime()
        self._clock_label.setText(now.toString("hh:mm:ss AP | ddd, dd MMM"))
        self._session_clock.setText(now.toString("hh:mm:ss AP"))
        self._right_clock.setText(now.toString("hh:mm:ss AP"))

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._application.stop()
        event.accept()


def _underlying_for_symbol(symbol: str) -> str:
    return "NIFTY" if "NIFTY" in symbol else "SENSEX"


def _price_or_dash(value: float | None) -> str:
    return f"{value:,.2f}" if value is not None and value > 0 else "—"


def _analysis_summary(analysis: IndicatorSnapshot) -> str:
    return f"{analysis.regime} | VWAP {_number(analysis.vwap)} | RSI {_number(analysis.rsi, 0)}"


def _indicator_html(analysis: IndicatorSnapshot) -> str:
    rows = [
        ("Regime", str(analysis.regime)), ("VWAP", _number(analysis.vwap)),
        ("EMA 9", _number(analysis.ema_fast)), ("EMA 21", _number(analysis.ema_slow)),
        ("RSI", _number(analysis.rsi, 1)), ("ATR", _number(analysis.atr)),
        ("Relative volume", _number(analysis.relative_volume, 2, suffix="x")),
        ("Opening range", f"{_number(analysis.opening_range_low)} – {_number(analysis.opening_range_high)}"),
    ]
    reasons = "<br>".join(f"<span style='color:#67e8a5'>• {reason}</span>" for reason in analysis.reasons)
    values = "".join(f"<tr><td>{name}</td><td><b>{value}</b></td></tr>" for name, value in rows)
    return f"<table width='100%'>{values}</table><br>{reasons}"


def _option_summary_html(chain: OptionChainSnapshot) -> str:
    return "<br>".join((
        f"ATM strike: <b>{_number(chain.atm_strike, 0)}</b>",
        f"PCR (OI): <b>{_number(chain.put_call_ratio_oi, 2)}</b>",
        f"Observed max pain: <b>{_number(chain.observed_max_pain, 0)}</b>",
        f"ATM IV skew (Put − Call): <b>{_signed(chain.iv_skew, '%')}</b>",
        f"ATM straddle / expected move: <b>{_number(chain.expected_move)}</b>",
        "<span style='color:#facc15'>Observed subscribed strikes only; not a full-exchange chain.</span>",
    ))


def _reason_html(snapshot: ConvictionSnapshot, matrix_bear_count: int = 0, matrix_names: tuple[str, ...] = ()) -> str:
    bulls = "<br>".join(f"<span style='color:#67e8a5'>✓ {reason}</span>" for reason in snapshot.bullish_reasons) or "<span style='color:#94a3b8'>No bullish evidence</span>"
    bears = "<br>".join(f"<span style='color:#fda4af'>✕ {reason}</span>" for reason in snapshot.bearish_reasons) or "<span style='color:#94a3b8'>No bearish evidence</span>"
    cautions = "<br>".join(f"<span style='color:#facc15'>! {reason}</span>" for reason in snapshot.conflicts)
    matrix_watch = ""
    if matrix_bear_count:
        matrix_watch = f"<br><br><b style='color:#facc15'>MATRIX WATCH</b><br><span style='color:#facc15'>{matrix_bear_count} bearish readings not included as core-score votes: {', '.join(matrix_names[:5])}</span>"
    return f"<b style='color:#67e8a5'>BULLISH</b><br>{bulls}<br><br><b style='color:#fda4af'>BEARISH</b><br>{bears}" + (f"<br><br><b style='color:#facc15'>CAUTION</b><br>{cautions}" if cautions else "") + matrix_watch


def _matrix_state_counts(
    analysis: IndicatorSnapshot | None, chain: OptionChainSnapshot | None
) -> tuple[int, int, tuple[str, ...]]:
    """Count display states without turning correlated indicators into votes.

    The conviction engine deliberately retains a smaller independent core. Matrix
    counts are shown for context, not summed into the trade score.
    """
    if analysis is None:
        return 0, 0, ()
    overrides = _option_indicator_overrides(chain) if chain is not None else {}
    states = [(reading.name, overrides.get(reading.name, (reading.value, reading.state, reading.reason))[1]) for reading in analysis.readings]
    bullish = sum(1 for _, state in states if state == "BULLISH")
    bearish_names = tuple(name for name, state in states if state == "BEARISH")
    return bullish, len(bearish_names), bearish_names


def _market_is_open() -> bool:
    """Use local India market hours to avoid presenting Saturday data as live."""
    now = datetime.now().astimezone()
    if now.weekday() >= 5:
        return False
    current = now.time()
    return time(9, 15) <= current <= time(15, 30)


def _plan_html(snapshot: ConvictionSnapshot) -> str:
    if snapshot.plan is None:
        return "<b style='color:#d8b4fe'>NO PAPER SETUP</b><br><br>Requires A/A+ grade, an ATM quote, and risk inside the configured maximum loss per lot."
    plan = snapshot.plan
    return f"<b style='color:#d8b4fe'>PAPER ONLY | {plan.option_symbol}</b><br><br>Entry: <b>{plan.entry:.2f}</b><br>Stop loss: <b>{plan.stop_loss:.2f}</b><br>Target 1: <b>{plan.target_1:.2f}</b><br>Target 2: <b>{plan.target_2:.2f}</b><br>Maximum loss / lot: <b>Rs. {plan.max_loss_per_lot:,.0f}</b><br>Lot size: <b>{plan.lot_size}</b><br><br><span style='color:#facc15'>No order is submitted.</span>"


def _number(value: float | None, decimals: int = 2, suffix: str = "") -> str:
    return f"{value:,.{decimals}f}{suffix}" if value is not None else "—"


def _signed(value: float | None, suffix: str = "") -> str:
    return f"{value:+.2f}{suffix}" if value is not None else "—"


def _metric_ltp(metric: OptionMetric | None) -> str:
    return _number(metric.last_price) if metric else "—"


def _metric_oi(metric: OptionMetric | None) -> str:
    return f"{metric.open_interest:,}" if metric and metric.open_interest is not None else "—"


def _metric_oi_change(metric: OptionMetric | None) -> str:
    return f"{metric.open_interest_change:+,}" if metric and metric.open_interest_change is not None else "—"


def _metric_iv(metric: OptionMetric | None) -> str:
    return _number(metric.implied_volatility, 1, "%") if metric else "—"


def _metric_velocity(metric: OptionMetric | None) -> str:
    return _signed(metric.premium_velocity) if metric else "—"


def _option_indicator_overrides(chain: OptionChainSnapshot) -> dict[str, tuple[str, str, str]]:
    """Bring actually observed option metrics into the 100-indicator matrix."""
    calls = [metric for metric in chain.metrics if metric.contract.option_type is OptionType.CALL]
    puts = [metric for metric in chain.metrics if metric.contract.option_type is OptionType.PUT]
    atm_calls = [metric for metric in calls if metric.contract.strike == chain.atm_strike]
    atm_puts = [metric for metric in puts if metric.contract.strike == chain.atm_strike]
    call_oi, put_oi = sum(metric.open_interest or 0 for metric in calls), sum(metric.open_interest or 0 for metric in puts)
    call_delta = sum(metric.open_interest_change or 0 for metric in calls)
    put_delta = sum(metric.open_interest_change or 0 for metric in puts)
    atm_ivs = [metric.implied_volatility for metric in (*atm_calls, *atm_puts) if metric.implied_volatility is not None]
    call_velocity = atm_calls[0].premium_velocity if atm_calls else None
    put_velocity = atm_puts[0].premium_velocity if atm_puts else None
    pcr_state = "BULLISH" if chain.put_call_ratio_oi is not None and chain.put_call_ratio_oi >= 1.15 else "BEARISH" if chain.put_call_ratio_oi is not None and chain.put_call_ratio_oi <= 0.85 else "NEUTRAL"
    return {
        "PCR (OI)": (_number(chain.put_call_ratio_oi, 2), pcr_state, "Observed put OI divided by observed call OI"),
        "Call OI": (f"{call_oi:,}" if calls else "—", "INFO", "Observed subscribed call open interest"),
        "Put OI": (f"{put_oi:,}" if puts else "—", "INFO", "Observed subscribed put open interest"),
        "Session Call OI Delta": (f"{call_delta:+,}" if calls else "—", "INFO", "Change since NICE-PRO started this session"),
        "Session Put OI Delta": (f"{put_delta:+,}" if puts else "—", "INFO", "Change since NICE-PRO started this session"),
        "ATM IV": (_number(sum(atm_ivs) / len(atm_ivs) if atm_ivs else None, 1, "%"), "INFO", "Model-implied volatility from observed ATM options"),
        "IV Skew": (_signed(chain.iv_skew, "%"), "BULLISH" if chain.iv_skew is not None and chain.iv_skew < 0 else "BEARISH" if chain.iv_skew is not None and chain.iv_skew > 0 else "NEUTRAL", "ATM put IV minus ATM call IV"),
        "Expected Move": (_number(chain.expected_move), "INFO", "Observed ATM CE + PE premium, not a forecast"),
        "Observed Max Pain": (_number(chain.observed_max_pain, 0), "INFO", "Computed from subscribed strikes only"),
        "ATM CE Premium Velocity": (_signed(call_velocity), "BULLISH" if call_velocity is not None and call_velocity > 0 else "BEARISH" if call_velocity is not None and call_velocity < 0 else "NEUTRAL", "Observed ATM call premium change per second"),
        "ATM PE Premium Velocity": (_signed(put_velocity), "BEARISH" if put_velocity is not None and put_velocity > 0 else "BULLISH" if put_velocity is not None and put_velocity < 0 else "NEUTRAL", "Observed ATM put premium change per second"),
    }


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
QLabel#quoteValue, QLabel#workspaceQuote { color: #f8fafc; font-size: 25px; font-weight: 900; }
QLabel#quoteState { color: #52d8ff; font-size: 10px; font-weight: 800; }
QLabel#convictionHeadline, QLabel#workspaceScore { color: #4ade80; font-size: 20px; font-weight: 900; }
QLabel#scoreText { color: #dce8f6; font-size: 11px; font-weight: 800; }
QLabel#workspaceReasons, QLabel#workspacePlan, QLabel#chainSummary { color: #dce8f6; font-size: 12px; }
QProgressBar { height: 7px; border: 0; border-radius: 3px; background: #142942; }
QProgressBar::chunk { border-radius: 3px; background: qlineargradient(x1:0, x2:1, stop:0 #f59e0b, stop:0.55 #b9d43e, stop:1 #22c55e); }
QLabel#positiveEvidence { color: #62e99a; font-size: 11px; }
QLabel#negativeEvidence { color: #fb7185; font-size: 11px; }
QLabel#cautionEvidence { color: #facc15; font-size: 10px; }
QLabel#planStatus { color: #d8b4fe; font-size: 13px; font-weight: 900; }
QLabel#sessionClock { color: #f8fafc; font-size: 22px; font-weight: 900; }
QLabel#muted, QLabel#micro { color: #94a9c2; font-size: 10px; }
QLabel#marketRow { border-bottom: 1px solid #123250; padding: 5px 0; font-size: 11px; }
QLabel#placeholderHeading { color: #b59cff; font-size: 24px; font-weight: 900; }
QFrame#footer { color: #71839d; font-size: 10px; }
QTabWidget#chainTabs::pane { border: 1px solid #164269; background: #071627; }
QTabBar::tab { background: #071627; color: #8ea4be; padding: 8px 18px; border: 1px solid #164269; }
QTabBar::tab:selected { background: #082940; color: #38bdf8; }
QTableWidget#optionTable { background: #06111f; alternate-background-color: #091b2c; border: 1px solid #164269; gridline-color: #16395d; color: #dce8f6; font-size: 11px; }
QTableWidget#indicatorTable { background: #06111f; alternate-background-color: #091b2c; border: 1px solid #164269; gridline-color: #16395d; color: #dce8f6; font-size: 10px; }
QHeaderView::section { background: #0b2137; color: #cfe8ff; border: 0; border-bottom: 1px solid #24618f; padding: 7px 2px; font-weight: 800; }
"""
