"""Fast-scan PySide6 workspaces for the paper-only NICE-PRO engine."""

from datetime import datetime, time
from threading import Thread
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
    QScrollArea,
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
    OptionHeroSnapshot,
    OptionMetric,
    OptionType,
    Quote,
    ScalpSnapshot,
    Side,
    TradePlan,
)

if TYPE_CHECKING:
    from nice_pro.core.application import Application


class DashboardSignals(QObject):
    snapshot = Signal(object)
    analysis = Signal(object)
    options = Signal(object)
    option_hero = Signal(object)
    scalp = Signal(object)
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
        self._analyses: dict[str, dict[int, IndicatorSnapshot]] = {"NIFTY": {}, "SENSEX": {}}
        self._rendered_matrix_versions: dict[str, tuple[object, ...]] = {"NIFTY": (), "SENSEX": ()}
        self._chains: dict[str, OptionChainSnapshot] = {}
        self._option_heroes: dict[str, OptionHeroSnapshot] = {}
        self._scalps: dict[str, ScalpSnapshot] = {}
        self._convictions: dict[str, ConvictionSnapshot] = {}
        self._kite_connected = False
        self._nav_buttons: list[QPushButton] = []
        self._analysis_views: dict[str, dict[str, object]] = {}
        self._option_tables: dict[str, QTableWidget] = {}
        self._option_summaries: dict[str, QLabel] = {}
        self._option_hero_cards: dict[str, QLabel] = {}
        self._scalp_cards: dict[str, QLabel] = {}
        self._signals.snapshot.connect(self.update_snapshot)
        self._signals.analysis.connect(self.update_analysis)
        self._signals.options.connect(self.update_options)
        self._signals.option_hero.connect(self.update_option_hero)
        self._signals.scalp.connect(self.update_scalp)
        self._signals.conviction.connect(self.update_conviction)
        self._signals.status.connect(self.update_status)
        application.add_snapshot_listener(self._signals.snapshot.emit)
        application.add_analysis_listener(self._signals.analysis.emit)
        application.add_option_listener(self._signals.options.emit)
        application.add_option_hero_listener(self._signals.option_hero.emit)
        application.add_scalp_listener(self._signals.scalp.emit)
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
        self._pages.addWidget(self._scrollable_page(self._dashboard_page()))
        self._pages.addWidget(self._scrollable_page(self._analysis_page("NIFTY")))
        self._pages.addWidget(self._scrollable_page(self._analysis_page("SENSEX")))
        self._pages.addWidget(self._scrollable_page(self._options_page()))
        self._pages.addWidget(self._scrollable_page(self._paper_page()))
        self._pages.addWidget(self._scrollable_page(self._journal_page()))
        self._pages.addWidget(self._scrollable_page(self._reports_page()))
        layout.addWidget(self._pages, 1)
        layout.addWidget(self._footer())
        self.setCentralWidget(root)
        self.setStyleSheet(_STYLESHEET)
        self._switch_page(0)
        self._refresh_research_views()

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

    @staticmethod
    def _scrollable_page(content: QWidget) -> QScrollArea:
        """Keep every workspace reachable at smaller window sizes or with long live data."""
        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        scroll.setWidget(content)
        return scroll

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
        score.setObjectName("convictionBox")
        score.setWordWrap(True)
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
        indicators_panel, indicators_layout = self._panel("100-INDICATOR MULTI-TIMEFRAME MATRIX", "blue")
        indicator_summary = self._muted("Rows are indicators; columns are 10s, 30s, 1m, 5m, 15m, 30m and 1h. Each cell is calculated only from its own timeframe.")
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
        heading, heading_layout = self._panel("LIVE OPTION CHAIN — COMPLETE NEAREST EXPIRY", "purple")
        heading_layout.addWidget(self._muted("Live LTP, OI, session OI delta, model IV and premium velocity for every subscribed CE/PE strike in the nearest expiry. Later expiries are separate chains; no order is submitted."))
        layout.addWidget(heading)

        hero_row = QHBoxLayout()
        hero_row.setSpacing(8)
        for underlying in ("NIFTY", "SENSEX"):
            hero_panel, hero_layout = self._panel(f"{underlying} FULL-CHAIN HERO — PAPER ONLY", "green")
            hero = QLabel(f"{underlying}: waiting for full-chain evidence")
            hero.setObjectName("optionHero")
            hero.setWordWrap(True)
            hero_layout.addWidget(hero)
            hero_row.addWidget(hero_panel, 1)
            self._option_hero_cards[underlying] = hero
        layout.addLayout(hero_row)

        scalp_row = QHBoxLayout()
        scalp_row.setSpacing(8)
        for underlying in ("NIFTY", "SENSEX"):
            scalp_panel, scalp_layout = self._panel(f"{underlying} OPTION SCALPING BOX — PAPER ONLY", "amber")
            scalp_layout.addWidget(self._muted("Requires aligned 10s/30s timing, ATM top-five book, estimated CVD, OTM continuation, premium velocity, and an acceptable spread."))
            scalp = QLabel(f"{underlying}: waiting for live scalp conditions")
            scalp.setObjectName("scalpBox")
            scalp.setWordWrap(True)
            scalp_layout.addWidget(scalp)
            scalp_row.addWidget(scalp_panel, 1)
            self._scalp_cards[underlying] = scalp
        layout.addLayout(scalp_row)
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
        headers = ("INDICATOR", "10s", "30s", "1m", "5m", "15m", "30m", "1h", "REASON")
        table = QTableWidget(0, len(headers))
        table.setObjectName("indicatorTable")
        table.setHorizontalHeaderLabels(headers)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for column in range(1, 8):
            table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        return table

    def _paper_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for underlying in ("NIFTY", "SENSEX"):
            panel, panel_layout = self._panel(f"{underlying} PAPER-FORWARD PLAN", "purple")
            active = QLabel("NO ACTIVE FORWARD PAPER POSITION")
            active.setObjectName("workspacePlan")
            active.setWordWrap(True)
            candidate = self._muted("Current qualified candidate: waiting for a completed 5-minute decision.")
            policy = self._muted("Forward policy: loading")
            panel_layout.addWidget(active)
            panel_layout.addWidget(candidate)
            panel_layout.addWidget(policy)
            panel_layout.addStretch()
            layout.addWidget(panel)
            view = self._analysis_views.setdefault(underlying, {})
            view["paper"] = candidate
            view["paper_active"] = active
            view["paper_policy"] = policy
        return page

    def _journal_page(self) -> QWidget:
        """Decision-time audit trail for paper-trade review and optimisation."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        overview, overview_layout = self._panel("RESEARCH JOURNAL — DECISION-TIME SNAPSHOTS", "purple")
        self._journal_overview = self._muted(
            "Every completed 5-minute core candle is saved locally with all timeframe readings, the 100-indicator matrix, full nearest-expiry chain metrics, Hero/Scalp evidence, filters, conflicts and paper-plan context."
        )
        overview_layout.addWidget(self._journal_overview)
        overview_layout.addWidget(self._muted("Times are displayed in IST; raw records remain stored in UTC for consistent research. These records preserve what the engine knew at the time, not hindsight scoring."))
        layout.addWidget(overview)
        table_panel, table_layout = self._panel("LATEST DECISION RECORDS", "blue")
        self._journal_table = QTableWidget(0, 8)
        self._journal_table.setObjectName("journalTable")
        self._journal_table.setHorizontalHeaderLabels(("TIME (IST)", "MARKET", "SIDE", "GRADE", "MTF", "ALIGNMENT", "5M BULL", "5M BEAR"))
        self._journal_table.verticalHeader().setVisible(False)
        self._journal_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._journal_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._journal_table.setAlternatingRowColors(True)
        self._journal_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table_layout.addWidget(self._journal_table, 1)
        layout.addWidget(table_panel, 1)
        return page

    def _reports_page(self) -> QWidget:
        """Observed paper-results summary. It stays honest when no sample exists."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        summary, summary_layout = self._panel("10-DAY PAPER-FORWARD PERFORMANCE", "green")
        self._report_summary = QLabel("Collecting paper-trade outcomes")
        self._report_summary.setObjectName("reportSummary")
        self._report_summary.setWordWrap(True)
        summary_layout.addWidget(self._report_summary)
        layout.addWidget(summary)
        policy, policy_layout = self._panel("FORWARD-TEST POLICY & LIVE PROGRESS", "purple")
        self._report_policy = self._muted("Forward-test policy loading")
        policy_layout.addWidget(self._report_policy)
        layout.addWidget(policy)
        method, method_layout = self._panel("OPTIMISATION & REVERSE-ENGINEERING DATA", "amber")
        method_layout.addWidget(self._muted(
            "For each saved decision, NICE-PRO retains: 10s/30s/1m/5m/15m/30m/1h regimes and readings; category-level matrix states; core and MTF scores; gate/alignment; bullish, bearish and conflict reasons; ATM plan; PCR, OI and OI changes; IV/skew, expected move, spread, book imbalance, estimated CVD, OTM continuation; Hero and Scalp scores."
        ))
        method_layout.addWidget(self._muted(
            "Use at least 10 trading days as an initial review window. Compare only enough observations, keep a hold-out period, and adjust one small weight set at a time. A paper result is not evidence of guaranteed future performance."
        ))
        layout.addWidget(method)
        per_market, market_layout = self._panel("RESULTS BY MARKET", "blue")
        self._report_by_market = self._muted("No closed paper trades in the selected window.")
        market_layout.addWidget(self._report_by_market)
        layout.addWidget(per_market)
        layout.addStretch()
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
        feed_health, feed_health_layout = self._panel("DATA FEED HEALTH", "purple")
        self._feed_health = self._muted("Stream: connecting\nFutures proxy: subscribing\nOption depth: subscribing")
        feed_health_layout.addWidget(self._feed_health)
        layout.addWidget(feed_health)
        notices, notices_layout = self._panel("NOTIFICATIONS", "amber")
        notices_layout.addWidget(self._muted("All recommendations are decision support only. Verify the evidence and risk before acting."))
        layout.addWidget(notices)
        layout.addStretch()
        return side

    def _quote_card(self, title: str, key: str) -> dict[str, object]:
        panel, layout = self._panel(title, "blue")
        content = QHBoxLayout()
        quote_column = QVBoxLayout()
        value = QLabel("--")
        value.setObjectName("quoteValue")
        state = QLabel("WAITING FOR LIVE QUOTE")
        state.setObjectName("quoteState")
        micro = QLabel("Bid / Ask  — / —")
        micro.setObjectName("micro")
        quote_column.addWidget(value)
        quote_column.addWidget(state)
        quote_column.addWidget(micro)
        content.addLayout(quote_column, 1)
        matrix = QLabel("5M INDICATOR MATRIX\nWaiting for 5-minute data")
        matrix.setObjectName("matrixSummary")
        matrix.setTextFormat(Qt.TextFormat.RichText)
        matrix.setWordWrap(True)
        content.addWidget(matrix, 1)
        layout.addLayout(content)
        return {"panel": panel, "value": value, "state": state, "micro": micro, "matrix": matrix, "key": key}

    def _conviction_card(self, title: str) -> dict[str, object]:
        panel, layout = self._panel(title, "green")
        content = QHBoxLayout()
        gauge = ConvictionGauge()
        content.addWidget(gauge, 0)
        details = QVBoxLayout()
        headline = QLabel("WAIT")
        headline.setObjectName("convictionHeadline")
        score = QLabel("MTF CONVICTION\n-- / 100")
        score.setObjectName("mtfScoreBadge")
        score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        timeframe_strip = QLabel("10s •  30s •  1m •  5m •  15m •  30m •  1h •")
        timeframe_strip.setObjectName("timeframeStrip")
        timeframe_strip.setTextFormat(Qt.TextFormat.RichText)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setTextVisible(False)
        detail = self._muted("Waiting for aligned market and option evidence")
        ml_shadow = self._muted("ML SHADOW: MODEL NOT TRAINED")
        ml_shadow.setObjectName("mlShadow")
        details.addWidget(headline)
        details.addWidget(score)
        details.addWidget(timeframe_strip)
        details.addWidget(bar)
        details.addWidget(detail)
        details.addWidget(ml_shadow)
        content.addLayout(details, 1)
        layout.addLayout(content)
        return {"panel": panel, "headline": headline, "score": score, "timeframes": timeframe_strip, "bar": bar, "detail": detail, "ml_shadow": ml_shadow, "gauge": gauge}

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
        if index in {5, 6}:
            self._refresh_research_views()
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
        self._analyses.setdefault(underlying, {})[analysis.timeframe_seconds] = analysis
        if analysis.timeframe_seconds == 300:
            card = self._nifty_quote if underlying == "NIFTY" else self._sensex_quote
            card["matrix"].setText(_matrix_summary_html(analysis))  # type: ignore[union-attr]
        self._refresh_analysis_view(underlying)

    def update_options(self, chain: OptionChainSnapshot) -> None:
        self._chains[chain.underlying] = chain
        self._refresh_option_table(chain)
        self._refresh_analysis_view(chain.underlying)

    def update_option_hero(self, hero: OptionHeroSnapshot) -> None:
        self._option_heroes[hero.underlying] = hero
        card = self._option_hero_cards.get(hero.underlying)
        if card is not None:
            card.setText(_option_hero_html(hero))

    def update_scalp(self, scalp: ScalpSnapshot) -> None:
        self._scalps[scalp.underlying] = scalp
        card = self._scalp_cards.get(scalp.underlying)
        if card is not None:
            card.setText(_scalp_html(scalp))

    def update_conviction(self, snapshot: ConvictionSnapshot) -> None:
        self._convictions[snapshot.underlying] = snapshot
        policy_status = self._application.forward_policy_status(snapshot.underlying)
        conviction = self._nifty_conviction if snapshot.underlying == "NIFTY" else self._sensex_conviction
        evidence = self._nifty_evidence if snapshot.underlying == "NIFTY" else self._sensex_evidence
        plan_card = self._nifty_plan if snapshot.underlying == "NIFTY" else self._sensex_plan
        conviction["headline"].setText(f"MTF DIRECTION: {_decision_direction(snapshot)}")  # type: ignore[union-attr]
        matrix_bull, matrix_bear, matrix_names = _matrix_state_counts(
            self._analyses.get(snapshot.underlying, {}).get(300), self._chains.get(snapshot.underlying)
        )
        conviction["score"].setText(
            "MTF ALIGNMENT SCORE<br>"
            f"{max(snapshot.mtf_bullish_score, snapshot.mtf_bearish_score)} / 100"
        )  # type: ignore[union-attr]
        conviction["timeframes"].setText(_timeframe_strip_html(snapshot))  # type: ignore[union-attr]
        conviction["bar"].setValue(snapshot.confidence)  # type: ignore[union-attr]
        # A blocked MTF gate is intentionally Side.NEUTRAL.  Still show the
        # dominant evidence on the gauge; otherwise a 30/100 bullish backdrop
        # is misleadingly rendered as zero merely because it is not tradable.
        gauge_score = (
            snapshot.mtf_bullish_score
            if snapshot.side is Side.BUY
            else snapshot.mtf_bearish_score
            if snapshot.side is Side.SELL
            else max(snapshot.mtf_bullish_score, snapshot.mtf_bearish_score)
        )
        conviction["gauge"].set_score(gauge_score)  # type: ignore[union-attr]
        conviction["detail"].setText(
            f"{snapshot.mtf_alignment} | Entry: {snapshot.entry_timing} | "
            f"5m core audit: {snapshot.grade} {snapshot.bullish_score}/{snapshot.bearish_score} | "
            f"{_plan_status(snapshot, policy_status)}"
        )  # type: ignore[union-attr]
        ml_shadow = self._application.ml_shadow_status(snapshot.underlying)
        if ml_shadow is None:
            ml_text = "ML SHADOW: WAITING FOR CORE SNAPSHOT"
        elif ml_shadow.score is None:
            ml_text = f"ML SHADOW: {ml_shadow.status} | Regime: {ml_shadow.regime}"
        else:
            drivers = "; ".join(item.split(":", 1)[0] for item in ml_shadow.top_reasons)
            ml_text = (
                f"ML SHADOW: {ml_shadow.score:.0%} | {ml_shadow.status} | "
                f"Regime: {ml_shadow.regime} | Top: {drivers or 'n/a'}"
            )
        conviction["ml_shadow"].setText(ml_text)  # type: ignore[union-attr]
        evidence["positive"].setText("+ " + ("\n+ ".join(snapshot.bullish_reasons[:3]) or "No bullish evidence"))  # type: ignore[union-attr]
        evidence["negative"].setText("- " + ("\n- ".join(snapshot.bearish_reasons[:3]) or "No bearish evidence"))  # type: ignore[union-attr]
        caution = ("CAUTION: " + snapshot.conflicts[0]) if snapshot.conflicts else ""
        if matrix_bear:
            matrix_note = f"MATRIX WATCH ({matrix_bear} bearish, not core-score votes): " + ", ".join(matrix_names[:3])
            caution = f"{caution}\n{matrix_note}" if caution else matrix_note
        evidence["caution"].setText(caution)  # type: ignore[union-attr]
        self._render_dashboard_plan(snapshot, plan_card, policy_status)
        self._refresh_analysis_view(snapshot.underlying)

    def _render_dashboard_plan(
        self, snapshot: ConvictionSnapshot, card: dict[str, object], policy_status: dict[str, object]
    ) -> None:
        active_plan = self._application.paper_trades.active_plan(snapshot.underlying)
        if active_plan is not None:
            card["status"].setText(f"ACTIVE FORWARD PAPER | {active_plan.option_symbol}")  # type: ignore[union-attr]
            card["detail"].setText(_active_plan_detail(active_plan))  # type: ignore[union-attr]
            return
        if snapshot.plan is None:
            card["status"].setText("NO PAPER SETUP")  # type: ignore[union-attr]
            reason = next((item for item in snapshot.conflicts if "rejected" in item.lower()), None)
            card["detail"].setText(reason or "No eligible plan: check the MTF gate, grade, ATM quote, and per-lot risk cap.")  # type: ignore[union-attr]
            return
        plan = snapshot.plan
        if not policy_status.get("market_eligible"):
            card["status"].setText(f"OBSERVATION ONLY | {plan.option_symbol}")  # type: ignore[union-attr]
            card["detail"].setText(
                f"Entry {plan.entry:.2f} | SL {plan.stop_loss:.2f} | T1 {plan.target_1:.2f} | T2 {plan.target_2:.2f}\n"
                "This market is journaled but is not validated for the active forward policy. "
                "No forward paper position can open."
            )  # type: ignore[union-attr]
            return
        card["status"].setText(f"FORWARD-POLICY CANDIDATE | {plan.option_symbol}")  # type: ignore[union-attr]
        card["detail"].setText(
            f"Entry {plan.entry:.2f} | SL {plan.stop_loss:.2f} | T1 {plan.target_1:.2f} | T2 {plan.target_2:.2f}\n"
            f"Candidate only: waits for a fresh completed 5m decision and policy checks. "
            f"Max loss/lot Rs. {plan.max_loss_per_lot:,.0f} | Lot {plan.lot_size}"
        )  # type: ignore[union-attr]
        self._alert_feed.setText(f"{snapshot.underlying} {snapshot.grade} qualified candidate\n{plan.option_symbol} | Forward-policy checks apply")

    def _refresh_analysis_view(self, underlying: str) -> None:
        view = self._analysis_views.get(underlying)
        if not view:
            return
        quote = self._quotes.get("NSE:NIFTY 50" if underlying == "NIFTY" else "BSE:SENSEX")
        analyses = self._analyses.get(underlying, {})
        analysis = analyses.get(300)
        chain = self._chains.get(underlying)
        conviction = self._convictions.get(underlying)
        if quote is not None:
            view["live"].setText(f"{quote.last_price:,.2f}")
            view["quote_meta"].setText(f"Bid / Ask: {_price_or_dash(quote.bid)} / {_price_or_dash(quote.ask)} | Live Kite quote")
        matrix_version = (
            tuple(sorted((timeframe, snapshot.calculated_at) for timeframe, snapshot in analyses.items())),
            chain.calculated_at if chain is not None else None,
        )
        if analyses and matrix_version != self._rendered_matrix_versions.get(underlying, ()):
            view["indicator_summary"].setText(_timeframe_summary(analyses))  # type: ignore[union-attr]
            self._refresh_indicator_tables(view["indicator_tables"], analyses, chain)  # type: ignore[arg-type]
            self._rendered_matrix_versions[underlying] = matrix_version
        if chain is not None:
            view["option"].setText(_option_summary_html(chain))
        if conviction is not None:
            matrix_bull, matrix_bear, matrix_names = _matrix_state_counts(analysis, chain)
            policy_status = self._application.forward_policy_status(underlying)
            view["score"].setText(_conviction_box_html(conviction, policy_status))
            view["score_meta"].setText(
                f"5m core score: Bull {conviction.bullish_score} / Bear {conviction.bearish_score}. "
                "The core is an audit layer; the MTF gate controls paper-plan eligibility."
            )
            view["reasons"].setText(_reason_html(conviction, matrix_bear, matrix_names))
            active_plan = self._application.paper_trades.active_plan(underlying)
            plan_text = _active_plan_html(active_plan) if active_plan is not None else _plan_html(conviction, policy_status)
            view["plan"].setText(plan_text)
            if "paper" in view:
                view["paper"].setText(plan_text)  # type: ignore[union-attr]

    def _refresh_indicator_tables(
        self, tables: dict[str, QTableWidget], analyses: dict[int, IndicatorSnapshot], chain: OptionChainSnapshot | None
    ) -> None:
        """Render every indicator row across all requested timeframes."""
        primary = analyses.get(300) or next(iter(analyses.values()))
        for category, table in tables.items():
            readings = [reading for reading in primary.readings if reading.category == category]
            is_chain_snapshot = category == "Options & Flow" and chain is not None
            overrides = _option_indicator_overrides(chain) if is_chain_snapshot else {}
            table.setRowCount(len(readings))
            for row, reading in enumerate(readings):
                cells: list[tuple[str, str, str]] = [(reading.name, "#dce8f6", reading.reason)]
                for timeframe in (10, 30, 60, 300, 900, 1800, 3600):
                    timeframe_snapshot = analyses.get(timeframe)
                    candidate = next(
                        (item for item in timeframe_snapshot.readings if item.name == reading.name), None
                    ) if timeframe_snapshot is not None else None
                    value, state, reason = overrides.get(reading.name, (candidate.value, candidate.state, candidate.reason)) if candidate is not None else ("—", "WAITING", "Awaiting timeframe history")
                    color = _state_color(state)
                    if is_chain_snapshot and reading.name in overrides:
                        value = f"{value} (current)"
                        reason = f"{reason}. Current nearest-expiry chain snapshot shared across timeframe columns; not historical {timeframe}s data."
                    cells.append((f"{value}\n{state}", color, reason))
                reason_text = (
                    "Current nearest-expiry option-chain snapshot shared across all timeframe columns."
                    if is_chain_snapshot and reading.name in overrides
                    else reading.reason
                )
                cells.append((reason_text, "#94a9c2", reason_text))
                for column, (text, color, tooltip) in enumerate(cells):
                    item = QTableWidgetItem(text)
                    item.setForeground(QColor(color))
                    item.setToolTip(tooltip)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter if 0 < column < 8 else Qt.AlignmentFlag.AlignLeft)
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
        self._refresh_feed_health()
        if now.time().second() % 5 == 0:
            self._refresh_research_views()

    def _refresh_feed_health(self) -> None:
        """Render direct, derived, stale, and unavailable feeds separately."""
        if not hasattr(self, "_feed_health"):
            return
        health = self._application.feed_health()
        feeds = self._application.data_feed_statuses()
        age = health.get("last_tick_age_seconds")
        age_text = f"{float(age):.1f}s" if isinstance(age, (int, float)) else "--"
        stream_state = str(health.get("state") or "OFFLINE")
        badge_text = {
            "LIVE": "KITE LIVE",
            "CONNECTED": "KITE CONNECTED — WAITING TICKS",
            "RECONNECTING": "KITE RECONNECTING",
            "STALE": "KITE STALE",
            "FAILED": "KITE FAILED",
            "STOPPED": "KITE STOPPED",
            "OFFLINE": "DATA STATUS",
        }.get(stream_state, f"KITE {stream_state}")
        is_live = stream_state in {"LIVE", "CONNECTED"}
        self._connection_badge.setText(badge_text)
        self._connection_badge.setProperty("connected", is_live)
        self._connection_badge.style().unpolish(self._connection_badge)
        self._connection_badge.style().polish(self._connection_badge)
        self._feed_health.setText(
            f"Stream: {stream_state} | last tick: {age_text} | reconnects: {health.get('reconnect_count', 0)}\n"
            f"Futures: {feeds['index_futures']}\n"
            f"Option book: {feeds['option_book']}\n"
            f"Flow: {feeds['derived']}\n"
            f"India VIX / breadth / global: NOT CONNECTED"
        )

    def _refresh_forward_paper_view(self, underlying: str) -> dict[str, object]:
        """Keep active paper positions distinct from merely qualified candidates."""
        status = self._application.forward_policy_status(underlying)
        view = self._analysis_views.get(underlying, {})
        active = self._application.paper_trades.active_position(underlying)
        active_label = view.get("paper_active")
        policy_label = view.get("paper_policy")
        if isinstance(active_label, QLabel):
            if active is None:
                active_label.setText("NO ACTIVE FORWARD PAPER POSITION")
            else:
                opened = active.opened_at.astimezone().strftime("%d %b %I:%M %p")
                active_label.setText(
                    f"ACTIVE FORWARD PAPER | {active.plan.option_symbol}\n"
                    f"Opened {opened} | Entry {active.plan.entry:.2f} | "
                    f"SL {active.plan.stop_loss:.2f} | T1 {active.plan.target_1:.2f}"
                )
        if isinstance(policy_label, QLabel):
            if not status.get("enabled"):
                policy_label.setText("Forward policy is disabled; no new forward-test paper trades can open.")
            elif not status.get("market_eligible"):
                policy_label.setText(
                    "No separately validated 308-session candidate is loaded for this market. "
                    "It remains journaled, but no forward-policy position can open yet."
                )
            else:
                cooldown = status.get("cooldown_until")
                cooldown_text = cooldown.astimezone().strftime("%I:%M %p") if isinstance(cooldown, datetime) else "ready"
                policy_label.setText(
                    f"Policy {status.get('policy_id')}: MTF {status.get('minimum_mtf_score')}+ | "
                    f"grade {status.get('minimum_grade')}+ | {status.get('cooldown_minutes')}m cooldown | "
                    f"{status.get('entries_today')}/{status.get('max_trades_per_day')} entries today | "
                    f"next eligibility {cooldown_text}."
                )
        return status

    def _refresh_research_views(self) -> None:
        """Refresh local SQLite-derived research widgets without touching Kite."""
        if not hasattr(self, "_journal_table"):
            return
        decisions = self._application.journal.recent_decisions(25)
        self._journal_table.setRowCount(len(decisions))
        for row, decision in enumerate(decisions):
            values = (
                decision["created_at_ist"],
                decision["underlying"], decision["side"], decision["grade"],
                str(decision["mtf_score"]), decision["alignment"],
                str(decision["core_bull"]), str(decision["core_bear"]),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 2:
                    item.setForeground(QColor("#4ade80") if value == "BUY" else QColor("#fda4af") if value == "SELL" else QColor("#facc15"))
                self._journal_table.setItem(row, column, item)
        self._journal_overview.setText(
            f"{len(decisions)} latest decision snapshots shown. Full raw inputs are stored locally at {self._application.journal.path}. "
            "Times shown here are IST. A snapshot is created once per completed 5-minute core candle, not per tick."
        )
        policy_states = [self._refresh_forward_paper_view(item) for item in ("NIFTY", "SENSEX")]
        policy = self._application.forward_policy
        report = self._application.journal.performance_summary(10, source=policy.source)
        if hasattr(self, "_report_policy"):
            active_markets = [str(state.get("active_symbol")) for state in policy_states if state.get("active")]
            self._report_policy.setText(
                f"Active policy: {policy.policy_id} | Entry window {policy.entry_start:%H:%M}-{policy.entry_end:%H:%M} IST | "
                f"MTF {policy.minimum_mtf_score}+ | grade {policy.minimum_grade.value}+ | {policy.cooldown_minutes}-minute cooldown | "
                f"maximum {policy.max_trades_per_day} entries/market/day | force exit {policy.force_exit_time:%H:%M} IST. "
                f"Validated markets: {', '.join(policy.eligible_underlyings)}. Forward source: {policy.source}. "
                f"Active positions: {', '.join(active_markets) if active_markets else 'none'}."
            )
        if report["closed_trades"] == 0:
            summary = (
                f"Observed sessions: {report['observed_sessions']}/10 | No closed forward-policy paper trades yet. "
                "Win rate appears only after a policy position reaches its model stop, Target 1, or an end-of-day exit."
            )
        else:
            rate = f"{report['win_rate']:.1f}%" if report["win_rate"] is not None else "—"
            average_r = f"{report['average_r']:.2f}R" if report["average_r"] is not None else "—"
            summary = (
                f"Observed sessions: {report['observed_sessions']}/10 | Closed: {report['closed_trades']} | "
                f"Resolved: {report['resolved_trades']} | Wins: {report['wins']} | Losses: {report['losses']} | "
                f"Time exits: {report['time_exits']} | Observed win rate: {rate} | Net P/L per lot: ₹{report['net_pnl_per_lot']:,.0f} | Average: {average_r}"
            )
        self._report_summary.setText(summary)
        by_market = report["by_underlying"]
        if by_market:
            self._report_by_market.setText("\n".join(
                _market_performance_line(market, stats)
                for market, stats in sorted(by_market.items())
            ))
        else:
            self._report_by_market.setText("No closed paper trades in the selected 10-day window.")

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._application.stop()
        event.accept()


def _underlying_for_symbol(symbol: str) -> str:
    return "NIFTY" if "NIFTY" in symbol else "SENSEX"


def _market_performance_line(market: str, stats: dict[str, object]) -> str:
    win_rate = stats.get("win_rate")
    rate = f"{float(win_rate):.1f}%" if isinstance(win_rate, (float, int)) else "â€”"
    return (
        f"{market}: {stats['trades']} closed across {stats['observed_sessions']} sessions | "
        f"{stats['wins']} wins | {stats['losses']} losses | {stats['time_exits']} time exits | "
        f"observed win rate {rate}"
    )


def _price_or_dash(value: float | None) -> str:
    return f"{value:,.2f}" if value is not None and value > 0 else "—"


def _analysis_summary(analysis: IndicatorSnapshot) -> str:
    return f"{analysis.regime} | VWAP {_number(analysis.vwap)} | RSI {_number(analysis.rsi, 0)}"


def _matrix_summary_html(analysis: IndicatorSnapshot) -> str:
    """Show a compact weighted 5-minute indicator audit in the quote card."""
    category_weights = {
        "Trend": 20,
        "Momentum": 20,
        "Volatility": 15,
        "Levels": 15,
        "Volume": 15,
        "Options & Flow": 15,
    }
    rows: list[str] = []
    bull_total = bear_total = 0.0
    for category, weight in category_weights.items():
        readings = [item for item in analysis.readings if item.category == category]
        count = len(readings)
        bulls = sum(item.state == "BULLISH" for item in readings)
        bears = sum(item.state == "BEARISH" for item in readings)
        bull_weight = weight * bulls / count if count else 0.0
        bear_weight = weight * bears / count if count else 0.0
        bull_total += bull_weight
        bear_total += bear_weight
        rows.append(
            f"<span style='color:#a5b4fc'>{category}</span> "
            f"<span style='color:#4ade80'>B {bulls} (+{bull_weight:.0f})</span> "
            f"<span style='color:#fb7185'>R {bears} (−{bear_weight:.0f})</span>"
        )
    return (
        "<span style='color:#d8b4fe; font-size:13px; font-weight:900'>5M INDICATOR MATRIX</span><br>"
        f"<span style='color:#4ade80; font-size:19px; font-weight:900'>BULL {bull_total:.0f}</span> "
        f"<span style='color:#fb7185; font-size:19px; font-weight:900'>BEAR {bear_total:.0f}</span><br>"
        + "<br>".join(rows)
    )


def _decision_direction(snapshot: ConvictionSnapshot) -> str:
    if snapshot.side is Side.BUY:
        return "BUY CALL"
    if snapshot.side is Side.SELL:
        return "BUY PUT"
    return "WAIT"


def _plan_status(
    snapshot: ConvictionSnapshot, policy_status: dict[str, object] | None = None
) -> str:
    """Separate raw model direction from forward-policy eligibility."""
    if snapshot.plan is None:
        return "No core paper plan"
    if policy_status is None:
        return "Core candidate; policy not assessed"
    if not policy_status.get("enabled"):
        return "Core candidate; forward policy disabled"
    if not policy_status.get("market_eligible"):
        return "Observation only; market not policy-validated"
    return "Forward-policy candidate; checks pending"


def _timeframe_strip_html(snapshot: ConvictionSnapshot) -> str:
    """One compact, colour-coded view of every timeframe direction."""
    if not snapshot.timeframe_signals:
        return "<span style='color:#94a3b8'>10s •  30s •  1m •  5m •  15m •  30m •  1h •</span>"
    parts: list[str] = []
    for signal in snapshot.timeframe_signals:
        if signal.side is Side.BUY:
            arrow, color = "↑", "#4ade80"
        elif signal.side is Side.SELL:
            arrow, color = "↓", "#fb7185"
        else:
            arrow, color = "•", "#94a3b8"
        parts.append(f"<span style='color:{color}; font-weight:900'>{signal.label} {arrow}</span>")
    return "&nbsp;&nbsp;".join(parts)


def _conviction_box_html(
    snapshot: ConvictionSnapshot, policy_status: dict[str, object] | None = None
) -> str:
    """Fast-scan multi-timeframe summary used on the NIFTY/SENSEX workspaces."""
    mtf_score = max(snapshot.mtf_bullish_score, snapshot.mtf_bearish_score)
    conflict = snapshot.conflicts[0] if snapshot.conflicts else "None"
    conflict_color = "#fda4af" if snapshot.conflicts else "#67e8a5"
    action = _decision_direction(snapshot)
    decision_color = "#67e8a5" if snapshot.side is not Side.NEUTRAL else "#facc15"
    return (
        f"<span style='color:#d8b4fe; font-size:17px; font-weight:900'>MTF ALIGNMENT SCORE: {mtf_score} / 100</span><br>"
        f"<span style='font-size:12px'>{_timeframe_strip_html(snapshot)}</span><br>"
        f"<span>Alignment: <b>{snapshot.mtf_alignment}</b></span><br>"
        f"<span>Entry timing: <b>{snapshot.entry_timing}</b></span><br>"
        f"<span>MTF direction: <b style='color:{decision_color}'>{action}</b></span><br>"
        f"<span>5m core audit: <b>{snapshot.grade} | Bull {snapshot.bullish_score} / Bear {snapshot.bearish_score}</b></span><br>"
        f"<span>Forward-policy status: <b>{_plan_status(snapshot, policy_status)}</b></span><br>"
        f"<span>Conflict: <b style='color:{conflict_color}'>{conflict}</b></span>"
    )


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
    coverage = (
        f"Nearest expiry coverage: <b>{chain.fresh_contracts}/{chain.registered_contracts} fresh</b> "
        f"({chain.quoted_contracts} quoted)"
        if chain.registered_contracts
        else "Nearest expiry coverage: <b>waiting for contracts</b>"
    )
    quote_age = (
        f"Oldest quote age: <b>{chain.oldest_quote_age_seconds:.1f}s</b> | "
        f"ATM pair age: <b>{chain.atm_quote_age_seconds:.1f}s</b>"
        if chain.oldest_quote_age_seconds is not None and chain.atm_quote_age_seconds is not None
        else "Quote freshness: <b>ATM pair warming up</b>"
    )
    return "<br>".join((
        f"ATM strike: <b>{_number(chain.atm_strike, 0)}</b>",
        f"PCR (OI): <b>{_number(chain.put_call_ratio_oi, 2)}</b>",
        f"Nearest-expiry max pain: <b>{_number(chain.observed_max_pain, 0)}</b>",
        f"ATM IV skew (Put − Call): <b>{_signed(chain.iv_skew, '%')}</b>",
        f"ATM straddle / expected move: <b>{_number(chain.expected_move)}</b>",
        f"ATM bid-ask spread (direct): <b>{_number(chain.atm_bid_ask_spread)}</b>",
        f"ATM top-5 book imbalance (direct): <b>{_signed(chain.atm_book_imbalance)}</b>",
        f"ATM CVD estimate (derived, not true tape): <b>{_number(chain.atm_estimated_cvd, 0)}</b>",
        f"OTM continuation (derived): <b>{_signed(chain.otm_continuation)}</b>",
        coverage,
        quote_age,
        "<span style='color:#67e8a5'>Direct: LTP/OI/bid/ask/top-5 depth. Derived: estimated CVD/OTM continuation. Later expiries are excluded.</span>",
    ))


def _option_hero_html(hero: OptionHeroSnapshot) -> str:
    """Compact raw chain-bias card; it never implies executable approval."""
    score = max(hero.bullish_score, hero.bearish_score)
    color = "#67e8a5" if hero.side is Side.BUY else "#fda4af" if hero.side is Side.SELL else "#facc15"
    action = "BUY CALL" if hero.side is Side.BUY else "BUY PUT" if hero.side is Side.SELL else "WAIT"
    evidence = "<br>".join(hero.reasons[:2]) or "Waiting for sufficient chain evidence"
    if hero.plan is None:
        plan = "Chain-only paper setup blocked / waiting"
    else:
        plan = (
            f"{hero.plan.option_symbol}<br>"
            f"LTP/Entry {hero.plan.entry:.2f} | SL {hero.plan.stop_loss:.2f}<br>"
            f"T1 {hero.plan.target_1:.2f} | T2 {hero.plan.target_2:.2f} | Loss/lot ₹{hero.plan.max_loss_per_lot:,.0f}"
        )
    return (
        f"<b>{hero.underlying}</b><br>"
        f"<span style='color:{color}; font-size:15px; font-weight:900'>RAW CHAIN BIAS: {hero.grade} | {action} | {score}/100</span><br>"
        f"<span style='color:#dce8f6'>Bull {hero.bullish_score} / Bear {hero.bearish_score} | Evidence quality {hero.confidence}%</span><br>"
        f"<span style='color:#a7f3d0'>{evidence}</span><br>"
        f"<span style='color:#f5d0fe'>{plan}</span><br>"
        "<span style='color:#94a3b8'>Chain-only evidence; not forward-policy validation or a probability of profit.</span>"
    )


def _scalp_html(scalp: ScalpSnapshot) -> str:
    execution_action = "BUY CE" if scalp.side is Side.BUY else "BUY PE" if scalp.side is Side.SELL else "WAIT / CONFLICT"
    raw_action = "BUY CE" if scalp.raw_side is Side.BUY else "BUY PE" if scalp.raw_side is Side.SELL else "NEUTRAL"
    color = "#67e8a5" if scalp.side is Side.BUY else "#fb7185" if scalp.side is Side.SELL else "#facc15"
    reasons = "<br>".join(scalp.reasons[:2]) or "Waiting for aligned live scalp evidence"
    if scalp.plan is None:
        plan = "No scalp paper setup — timing, liquidity, and microstructure must all align."
    else:
        plan = (
            f"{scalp.plan.option_symbol}<br>"
            f"LTP/Entry {scalp.plan.entry:.2f} | SL {scalp.plan.stop_loss:.2f} | "
            f"T1 {scalp.plan.target_1:.2f} | T2 {scalp.plan.target_2:.2f} | Loss/lot ₹{scalp.plan.max_loss_per_lot:,.0f}"
        )
    return (
        f"<b>{scalp.underlying}</b> "
        f"<span style='color:{color}; font-size:14px; font-weight:900'>{execution_action} | Raw evidence {scalp.score}/100 | Evidence quality {scalp.confidence}%</span><br>"
        f"<span style='color:#dce8f6'>Raw directional bias: {raw_action} | Setup status: {scalp.setup_status}</span><br>"
        f"<span style='color:#a7f3d0'>{reasons}</span><br>"
        f"<span style='color:#f5d0fe'>{plan}</span>"
    )


def _reason_html(snapshot: ConvictionSnapshot, matrix_bear_count: int = 0, matrix_names: tuple[str, ...] = ()) -> str:
    bulls = "<br>".join(f"<span style='color:#67e8a5'>✓ {reason}</span>" for reason in snapshot.bullish_reasons) or "<span style='color:#94a3b8'>No bullish evidence</span>"
    bears = "<br>".join(f"<span style='color:#fda4af'>✕ {reason}</span>" for reason in snapshot.bearish_reasons) or "<span style='color:#94a3b8'>No bearish evidence</span>"
    cautions = "<br>".join(f"<span style='color:#facc15'>! {reason}</span>" for reason in snapshot.conflicts)
    matrix_watch = ""
    if matrix_bear_count:
        matrix_watch = f"<br><br><b style='color:#facc15'>MATRIX WATCH</b><br><span style='color:#facc15'>{matrix_bear_count} bearish readings not included as core-score votes: {', '.join(matrix_names[:5])}</span>"
    timeframe = ""
    if snapshot.timeframe_signals:
        signal_lines = "<br>".join(
            f"<span style='color:{_side_color(signal.side)}'>{signal.label}: {signal.side} ({signal.weight}%) — {signal.reason}</span>"
            for signal in snapshot.timeframe_signals
        )
        timeframe = (
            "<br><br><b style='color:#c4b5fd'>MULTI-TIMEFRAME GATE</b><br>"
            f"<span style='color:#dce8f6'>Alignment: {snapshot.mtf_alignment} | Entry: {snapshot.entry_timing}</span><br>{signal_lines}"
        )
    return f"<b style='color:#67e8a5'>BULLISH</b><br>{bulls}<br><br><b style='color:#fda4af'>BEARISH</b><br>{bears}" + (f"<br><br><b style='color:#facc15'>CAUTION</b><br>{cautions}" if cautions else "") + timeframe + matrix_watch


def _side_color(side: Side) -> str:
    if side is Side.BUY:
        return "#67e8a5"
    if side is Side.SELL:
        return "#fda4af"
    return "#facc15"


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


def _state_color(state: str) -> str:
    return {
        "BULLISH": "#67e8a5",
        "BEARISH": "#fda4af",
        "NEUTRAL": "#facc15",
        "FEED REQUIRED": "#94a3b8",
        "WAITING": "#94a3b8",
        "INFO": "#cfe8ff",
    }.get(state, "#cfe8ff")


def _timeframe_summary(analyses: dict[int, IndicatorSnapshot]) -> str:
    labels = {10: "10s", 30: "30s", 60: "1m", 300: "5m", 900: "15m", 1800: "30m", 3600: "1h"}
    summaries = []
    for timeframe, label in labels.items():
        snapshot = analyses.get(timeframe)
        if snapshot is None:
            summaries.append(f"{label}: waiting")
        else:
            summaries.append(f"{label}: {snapshot.regime}")
    return " | ".join(summaries)


def _plan_html(snapshot: ConvictionSnapshot, policy_status: dict[str, object] | None = None) -> str:
    if snapshot.plan is None:
        return (
            "<b style='color:#d8b4fe'>NO PAPER SETUP</b><br><br>"
            f"MTF gate: <b>{snapshot.mtf_alignment}</b> | Entry timing: <b>{snapshot.entry_timing}</b><br>"
            "Requires 1m/5m alignment, no opposing higher timeframe, A/A+ grade, an ATM quote, and risk inside the configured maximum loss per lot."
        )
    plan = snapshot.plan
    if policy_status is not None and not policy_status.get("market_eligible"):
        heading = "OBSERVATION ONLY â€” NOT FORWARD-POLICY VALIDATED"
        note = "This market remains journaled for research. No forward paper position can open under the active policy."
    else:
        heading = "FORWARD-POLICY CANDIDATE"
        note = "A fresh completed 5m decision and forward-policy checks are still required. No order is submitted."
    return f"<b style='color:#d8b4fe'>{heading} | {plan.option_symbol}</b><br><br>Entry: <b>{plan.entry:.2f}</b><br>Stop loss: <b>{plan.stop_loss:.2f}</b><br>Target 1: <b>{plan.target_1:.2f}</b><br>Target 2: <b>{plan.target_2:.2f}</b><br>Maximum loss / lot: <b>Rs. {plan.max_loss_per_lot:,.0f}</b><br>Lot size: <b>{plan.lot_size}</b><br><br><span style='color:#facc15'>{note}</span>"


def _active_plan_detail(plan: TradePlan) -> str:
    return (
        f"Entry {plan.entry:.2f} | SL {plan.stop_loss:.2f} | T1 {plan.target_1:.2f} | T2 {plan.target_2:.2f}\n"
        f"Forward paper position is active. Max loss/lot Rs. {plan.max_loss_per_lot:,.0f} | Lot {plan.lot_size}"
    )


def _active_plan_html(plan: TradePlan) -> str:
    return (
        f"<b style='color:#67e8a5'>ACTIVE FORWARD PAPER | {plan.option_symbol}</b><br><br>"
        f"Entry: <b>{plan.entry:.2f}</b><br>Stop loss: <b>{plan.stop_loss:.2f}</b><br>"
        f"Target 1: <b>{plan.target_1:.2f}</b><br>Target 2: <b>{plan.target_2:.2f}</b><br>"
        f"Maximum loss / lot: <b>Rs. {plan.max_loss_per_lot:,.0f}</b><br>Lot size: <b>{plan.lot_size}</b><br><br>"
        "<span style='color:#facc15'>Paper-only position; no broker order exists.</span>"
    )


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
        "Nearest-expiry Max Pain": (_number(chain.observed_max_pain, 0), "INFO", "Computed from every available strike in NICE-PRO's nearest-expiry chain"),
        "ATM CE Premium Velocity": (_signed(call_velocity), "BULLISH" if call_velocity is not None and call_velocity > 0 else "BEARISH" if call_velocity is not None and call_velocity < 0 else "NEUTRAL", "Observed ATM call premium change per second"),
        "ATM PE Premium Velocity": (_signed(put_velocity), "BEARISH" if put_velocity is not None and put_velocity > 0 else "BULLISH" if put_velocity is not None and put_velocity < 0 else "NEUTRAL", "Observed ATM put premium change per second"),
        "Bid-Ask Spread": (_number(chain.atm_bid_ask_spread), "INFO", "Direct ATM CE/PE average bid-ask spread from Kite top-five depth"),
        "ATM Book Imbalance": (_signed(chain.atm_book_imbalance), "INFO" if chain.atm_book_imbalance is not None else "WAITING", "Direct top-five ATM CE/PE depth. It is a liquidity context, not a directional vote."),
        "Estimated CVD": (_number(chain.atm_estimated_cvd, 0), _direction_state(chain.atm_estimated_cvd), "Derived CVD estimate from tick price versus bid/ask and available trade size; Kite has no true exchange tape or aggressor flag"),
        "OTM Continuation": (_signed(chain.otm_continuation), _direction_state(chain.otm_continuation), "Derived from first OTM call versus put premium velocity; not an exchange-labelled signal"),
    }


def _direction_state(value: float | int | None) -> str:
    if value is None:
        return "WAITING"
    if value > 0:
        return "BULLISH"
    if value < 0:
        return "BEARISH"
    return "NEUTRAL"


def run_dashboard(application: "Application") -> int:
    app = QApplication.instance() or QApplication([])
    window = MainWindow(application)
    window.show()

    def start_services() -> None:
        """Keep network setup off Qt's UI event loop.

        Kite's WebSocket handshake, reconnect behaviour, and initial REST calls
        can stall on an unavailable network.  They must never make the desktop
        window appear as "Not responding".
        """
        try:
            application.start()
        except Exception as error:
            application.publish_status(f"startup error: {error}")

    # Queue after the window is visible and run the potentially slow startup
    # boundary in a worker.  GUI changes continue via Qt signals.
    QTimer.singleShot(0, lambda: Thread(target=start_services, name="nice-pro-startup", daemon=True).start())
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
QScrollArea#pageScroll { background: #000000; border: none; }
QScrollArea#pageScroll > QWidget > QWidget { background: #000000; }
QScrollBar:vertical { background: #050d17; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #1c5b83; min-height: 28px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #050d17; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #1c5b83; min-width: 28px; border-radius: 5px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
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
QLabel#convictionBox { color: #dce8f6; font-size: 12px; font-weight: 700; padding: 2px 0; }
QLabel#scoreText { color: #dce8f6; font-size: 11px; font-weight: 800; }
QLabel#mtfScoreBadge { background: #102b46; color: #d8b4fe; border: 1px solid #6d42a3; border-radius: 5px; padding: 3px 10px; font-size: 12px; font-weight: 900; }
QLabel#timeframeStrip { color: #dce8f6; font-size: 10px; font-weight: 800; padding: 1px 0; }
QLabel#workspaceReasons, QLabel#workspacePlan, QLabel#chainSummary { color: #dce8f6; font-size: 12px; }
QLabel#optionHero { color: #dce8f6; font-size: 11px; padding: 6px 8px; }
QLabel#scalpBox { color: #dce8f6; font-size: 11px; padding: 6px 8px; }
QLabel#matrixSummary { color: #dce8f6; font-size: 9px; padding: 3px 7px; border-left: 1px solid #1d4f76; }
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
