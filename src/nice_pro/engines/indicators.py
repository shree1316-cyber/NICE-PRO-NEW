"""Dependency-light, transparent one-minute market indicators."""

from datetime import datetime, timedelta, timezone
from math import sqrt

from nice_pro.models.market import Candle, IndicatorReading, IndicatorSnapshot, MarketRegime

# A fixed offset avoids requiring the IANA tzdata package on Windows. India does
# not observe daylight saving time, so this remains correct for market sessions.
IST = timezone(timedelta(hours=5, minutes=30), name="IST")


class IndicatorEngine:
    """Calculates a conservative first set of indicators from completed 1-minute bars.

    These values describe conditions; they are not a trade recommendation or a
    probability estimate. Weights and trade decisions arrive in later milestones.
    """

    def evaluate(
        self, symbol: str, candles: tuple[Candle, ...], timeframe_seconds: int | None = None
    ) -> IndicatorSnapshot:
        actual_timeframe = timeframe_seconds or (candles[-1].timeframe_seconds if candles else 60)
        if len(candles) < 21:
            return IndicatorSnapshot(
                symbol=symbol,
                regime=MarketRegime.INSUFFICIENT_DATA,
                calculated_at=_latest_time(candles),
                timeframe_seconds=actual_timeframe,
                close=candles[-1].close if candles else None,
                reasons=(f"Waiting for 21 one-minute candles ({len(candles)}/21 collected)",),
                readings=_waiting_readings(len(candles)),
            )
        closes = [candle.close for candle in candles]
        fast = _ema(closes, 9)
        slow = _ema(closes, 21)
        rsi = _rsi(closes, 14)
        atr = _atr(candles, 14)
        vwap = _session_vwap(candles)
        relative_volume = _relative_volume(candles, 20)
        opening_high, opening_low = _opening_range(candles)
        regime, reasons = _classify(closes[-1], fast, slow, rsi, atr, vwap, opening_high, opening_low)
        return IndicatorSnapshot(
            symbol=symbol,
            regime=regime,
            calculated_at=candles[-1].closed_at,
            timeframe_seconds=candles[-1].timeframe_seconds,
            close=closes[-1],
            vwap=vwap,
            ema_fast=fast,
            ema_slow=slow,
            rsi=rsi,
            atr=atr,
            relative_volume=relative_volume,
            opening_range_high=opening_high,
            opening_range_low=opening_low,
            reasons=tuple(reasons),
            readings=_build_readings(candles, fast, slow, rsi, atr, vwap, relative_volume, opening_high, opening_low),
        )


def _ema(values: list[float], period: int) -> float:
    multiplier = 2 / (period + 1)
    result = sum(values[:period]) / period
    for value in values[period:]:
        result = value * multiplier + result * (1 - multiplier)
    return result


def _rsi(closes: list[float], period: int) -> float:
    changes = [current - previous for previous, current in zip(closes, closes[1:])][-period:]
    gains = sum(change for change in changes if change > 0) / period
    losses = -sum(change for change in changes if change < 0) / period
    if losses == 0:
        return 100.0
    return 100 - 100 / (1 + gains / losses)


def _atr(candles: tuple[Candle, ...], period: int) -> float:
    true_ranges = [
        max(current.high - current.low, abs(current.high - previous.close), abs(current.low - previous.close))
        for previous, current in zip(candles, candles[1:])
    ]
    return sum(true_ranges[-period:]) / period


def _session_vwap(candles: tuple[Candle, ...]) -> float:
    session_date = candles[-1].opened_at.astimezone(IST).date()
    session = [bar for bar in candles if bar.opened_at.astimezone(IST).date() == session_date]
    total_volume = sum(bar.volume for bar in session)
    if total_volume == 0:
        return sum(bar.close for bar in session) / len(session)
    return sum(((bar.high + bar.low + bar.close) / 3) * bar.volume for bar in session) / total_volume


def _relative_volume(candles: tuple[Candle, ...], period: int) -> float | None:
    volumes = [bar.volume for bar in candles]
    baseline = sum(volumes[-period - 1 : -1]) / period
    return volumes[-1] / baseline if baseline else None


def _opening_range(candles: tuple[Candle, ...]) -> tuple[float | None, float | None]:
    session_date = candles[-1].opened_at.astimezone(IST).date()
    opening = [
        bar
        for bar in candles
        if bar.opened_at.astimezone(IST).date() == session_date
        and (bar.opened_at.astimezone(IST).hour, bar.opened_at.astimezone(IST).minute) < (9, 30)
    ]
    if not opening:
        return None, None
    return max(bar.high for bar in opening), min(bar.low for bar in opening)


def _classify(
    close: float,
    fast: float,
    slow: float,
    rsi: float,
    atr: float,
    vwap: float,
    opening_high: float | None,
    opening_low: float | None,
) -> tuple[MarketRegime, list[str]]:
    volatility = atr / close * 100
    if volatility >= 0.55:
        return MarketRegime.VOLATILE, [f"ATR is elevated ({volatility:.2f}% of price)"]
    if fast > slow and close > vwap and rsi >= 55:
        reasons = ["EMA 9 is above EMA 21", "Price is above session VWAP", f"RSI is supportive ({rsi:.0f})"]
        if opening_high is not None and close > opening_high:
            reasons.append("Price is above the opening-range high")
        return MarketRegime.TREND_UP, reasons
    if fast < slow and close < vwap and rsi <= 45:
        reasons = ["EMA 9 is below EMA 21", "Price is below session VWAP", f"RSI is weak ({rsi:.0f})"]
        if opening_low is not None and close < opening_low:
            reasons.append("Price is below the opening-range low")
        return MarketRegime.TREND_DOWN, reasons
    return MarketRegime.RANGE, ["Trend conditions are not aligned", "Treat signals as lower-confidence until confirmation"]


def _latest_time(candles: tuple[Candle, ...]) -> datetime:
    return candles[-1].closed_at if candles else datetime.now(tz=IST)


# The catalogue has exactly 100 rows. A row is never invented: when a required
# source is absent it remains visible as "FEED REQUIRED" with a plain-language
# reason. This lets a trader distinguish a real neutral signal from missing data.
_CATALOG: tuple[tuple[str, str], ...] = (
    *(("Trend", name) for name in ("EMA 5", "EMA 8", "EMA 9", "EMA 13", "EMA 20", "EMA 21", "EMA 34", "EMA 50", "SMA 5", "SMA 10", "SMA 20", "SMA 50", "WMA 9", "WMA 20", "MACD Line", "MACD Signal", "MACD Histogram", "EMA 9/21 Alignment", "Price vs EMA 20", "EMA 20 Slope")),
    *(("Momentum", name) for name in ("RSI 2", "RSI 7", "RSI 14", "RSI 21", "Stochastic %K", "Stochastic %D", "Williams %R", "ROC 1", "ROC 5", "ROC 10", "ROC 20", "CCI 14", "Momentum 10", "Awesome Oscillator", "RSI Divergence Proxy", "MACD Histogram Momentum", "Close vs 20-Bar Mean", "3-Bar Impulse", "10-Bar Impulse", "Price Acceleration")),
    *(("Volatility", name) for name in ("ATR 7", "ATR 14", "Bollinger Upper", "Bollinger Mid", "Bollinger Lower", "Bollinger Width", "Donchian Upper", "Donchian Mid", "Donchian Lower", "Keltner Upper", "Keltner Mid", "Keltner Lower", "Std Dev 20", "High-Low Range", "ATR Percent")),
    *(("Levels", name) for name in ("Session VWAP", "Opening Range High", "Opening Range Low", "Opening Range Position", "Session High", "Session Low", "Session Range", "Session Change", "Pivot", "R1", "S1", "Previous Close", "Price vs VWAP", "Price vs Pivot", "Close Location in Range")),
    *(("Volume", name) for name in ("Relative Volume", "Current Bar Volume", "Session Volume", "Volume SMA 20", "Volume Spike", "OBV", "CMF 20", "MFI 14", "VWAP Volume Basis", "Volume ROC", "Accumulation/Distribution", "Price Volume Trend", "Ease of Movement", "Force Index", "Chaikin Oscillator")),
    *(("Options & Flow", name) for name in ("PCR (OI)", "Call OI", "Put OI", "Session Call OI Delta", "Session Put OI Delta", "ATM IV", "IV Skew", "Expected Move", "Observed Max Pain", "ATM CE Premium Velocity", "ATM PE Premium Velocity", "Bid-Ask Spread", "ATM Book Imbalance", "Estimated CVD", "OTM Continuation")),
)


def _waiting_readings(candle_count: int) -> tuple[IndicatorReading, ...]:
    return tuple(
        IndicatorReading(name, category, "—", "WAITING", f"Waiting for history ({candle_count}/21 one-minute candles)")
        for category, name in _CATALOG
    )


def _build_readings(
    candles: tuple[Candle, ...],
    fast: float,
    slow: float,
    rsi: float,
    atr: float,
    vwap: float,
    relative_volume: float | None,
    opening_high: float | None,
    opening_low: float | None,
) -> tuple[IndicatorReading, ...]:
    closes = [bar.close for bar in candles]
    highs = [bar.high for bar in candles]
    lows = [bar.low for bar in candles]
    current = closes[-1]
    values: dict[str, tuple[str, str, str]] = {}

    def put(name: str, value: float | None, state: str = "INFO", reason: str = "Calculated from completed one-minute candles", decimals: int = 2, suffix: str = "") -> None:
        values[name] = ("—" if value is None else f"{value:,.{decimals}f}{suffix}", state, reason)

    # Trend (20)
    for period in (5, 8, 9, 13, 20, 21, 34, 50):
        ema = _ema(closes, period) if len(closes) >= period else None
        put(f"EMA {period}", ema, _price_state(current, ema), "Price is above EMA" if ema is not None and current > ema else "Price is below EMA" if ema is not None else "Insufficient history")
    for period in (5, 10, 20, 50):
        sma = _sma(closes, period)
        put(f"SMA {period}", sma, _price_state(current, sma), "Price relative to simple moving average")
    for period in (9, 20):
        wma = _wma(closes, period)
        put(f"WMA {period}", wma, _price_state(current, wma), "Price relative to weighted moving average")
    macd_line, macd_signal, macd_hist = _macd(closes)
    put("MACD Line", macd_line, "BULLISH" if macd_line is not None and macd_line > 0 else "BEARISH", "MACD line relative to zero")
    put("MACD Signal", macd_signal, "INFO", "Nine-period EMA of MACD line")
    put("MACD Histogram", macd_hist, "BULLISH" if macd_hist is not None and macd_hist > 0 else "BEARISH", "MACD line less signal line")
    put("EMA 9/21 Alignment", fast - slow, "BULLISH" if fast > slow else "BEARISH", "EMA 9 above EMA 21" if fast > slow else "EMA 9 below EMA 21")
    ema20 = _ema(closes, 20)
    put("Price vs EMA 20", current - ema20, _price_state(current, ema20), "Distance from EMA 20")
    ema20_prior = _ema(closes[:-1], 20) if len(closes) >= 21 else None
    put("EMA 20 Slope", ema20 - ema20_prior if ema20_prior is not None else None, "BULLISH" if ema20_prior is not None and ema20 > ema20_prior else "BEARISH", "Current EMA 20 change")

    # Momentum (20)
    for period in (2, 7, 14, 21):
        value = _rsi(closes, period) if len(closes) > period else None
        put(f"RSI {period}", value, "BULLISH" if value is not None and value >= 55 else "BEARISH" if value is not None and value <= 45 else "NEUTRAL", "RSI above 55 is supportive; below 45 is weak", 1)
    stochastic_k, stochastic_d = _stochastic(candles)
    put("Stochastic %K", stochastic_k, "BULLISH" if stochastic_k is not None and stochastic_k > 50 else "BEARISH", "Fourteen-period stochastic position", 1)
    put("Stochastic %D", stochastic_d, "BULLISH" if stochastic_d is not None and stochastic_d > 50 else "BEARISH", "Three-period average of %K", 1)
    williams = _williams_r(candles)
    put("Williams %R", williams, "BULLISH" if williams is not None and williams > -50 else "BEARISH", "Fourteen-period Williams %R", 1)
    for period in (1, 5, 10, 20):
        roc = _roc(closes, period)
        put(f"ROC {period}", roc, "BULLISH" if roc is not None and roc > 0 else "BEARISH", "Rate of change", 2, "%")
    cci = _cci(candles)
    put("CCI 14", cci, "BULLISH" if cci is not None and cci > 0 else "BEARISH", "Commodity channel index", 1)
    momentum10 = current - closes[-11] if len(closes) >= 11 else None
    put("Momentum 10", momentum10, "BULLISH" if momentum10 is not None and momentum10 > 0 else "BEARISH", "Ten-bar price change")
    awesome = _awesome(candles)
    put("Awesome Oscillator", awesome, "BULLISH" if awesome is not None and awesome > 0 else "BEARISH", "Five-period less 34-period median-price SMA")
    rsi7 = _rsi(closes, 7)
    rsi14 = _rsi(closes, 14)
    put("RSI Divergence Proxy", rsi7 - rsi14, "BULLISH" if rsi7 >= rsi14 else "BEARISH", "Short RSI relative to standard RSI")
    macd_previous = _macd(closes[:-1])[2] if len(closes) > 35 else None
    put("MACD Histogram Momentum", macd_hist - macd_previous if macd_hist is not None and macd_previous is not None else None, "BULLISH" if macd_previous is not None and macd_hist > macd_previous else "BEARISH", "Histogram change from prior candle")
    mean20 = _sma(closes, 20)
    put("Close vs 20-Bar Mean", current - mean20, _price_state(current, mean20), "Distance from 20-bar mean")
    impulse3 = current - closes[-4] if len(closes) >= 4 else None
    impulse10 = current - closes[-11] if len(closes) >= 11 else None
    put("3-Bar Impulse", impulse3, "BULLISH" if impulse3 is not None and impulse3 > 0 else "BEARISH", "Three-bar impulse")
    put("10-Bar Impulse", impulse10, "BULLISH" if impulse10 is not None and impulse10 > 0 else "BEARISH", "Ten-bar impulse")
    acceleration = (closes[-1] - closes[-2]) - (closes[-2] - closes[-3]) if len(closes) >= 3 else None
    put("Price Acceleration", acceleration, "BULLISH" if acceleration is not None and acceleration > 0 else "BEARISH", "Change in one-bar price velocity")

    # Volatility (15)
    atr7 = _atr(candles, 7)
    put("ATR 7", atr7, "INFO", "Seven-period average true range")
    put("ATR 14", atr, "INFO", "Fourteen-period average true range")
    mean, deviation = _sma(closes, 20), _stddev(closes, 20)
    upper = mean + 2 * deviation if mean is not None and deviation is not None else None
    lower = mean - 2 * deviation if mean is not None and deviation is not None else None
    put("Bollinger Upper", upper, "BEARISH" if upper is not None and current > upper else "INFO", "20 SMA plus two standard deviations")
    put("Bollinger Mid", mean, _price_state(current, mean), "20-period simple moving average")
    put("Bollinger Lower", lower, "BULLISH" if lower is not None and current < lower else "INFO", "20 SMA less two standard deviations")
    put("Bollinger Width", ((upper - lower) / mean * 100) if upper is not None and lower is not None and mean else None, "INFO", "Band width as percentage of midline", 2, "%")
    donchian_high = max(highs[-20:]) if len(highs) >= 20 else None
    donchian_low = min(lows[-20:]) if len(lows) >= 20 else None
    donchian_mid = (donchian_high + donchian_low) / 2 if donchian_high is not None and donchian_low is not None else None
    put("Donchian Upper", donchian_high, "BULLISH" if donchian_high is not None and current >= donchian_high else "INFO", "20-bar highest high")
    put("Donchian Mid", donchian_mid, _price_state(current, donchian_mid), "Midpoint of 20-bar Donchian channel")
    put("Donchian Lower", donchian_low, "BEARISH" if donchian_low is not None and current <= donchian_low else "INFO", "20-bar lowest low")
    keltner_mid = _ema(closes, 20)
    put("Keltner Upper", keltner_mid + 2 * atr if keltner_mid is not None else None, "INFO", "EMA 20 plus 2 ATR")
    put("Keltner Mid", keltner_mid, _price_state(current, keltner_mid), "EMA 20")
    put("Keltner Lower", keltner_mid - 2 * atr if keltner_mid is not None else None, "INFO", "EMA 20 less 2 ATR")
    put("Std Dev 20", deviation, "INFO", "20-period closing-price standard deviation")
    current_range = candles[-1].high - candles[-1].low
    put("High-Low Range", current_range, "INFO", "Current one-minute high-low range")
    put("ATR Percent", atr / current * 100, "INFO", "ATR 14 as percentage of close", 3, "%")

    # Levels (15)
    session = _current_session(candles)
    session_high, session_low = max(bar.high for bar in session), min(bar.low for bar in session)
    session_open = session[0].open
    previous_close = _previous_session_close(candles)
    pivot, r1, s1 = _pivots(candles)
    opening_position = _range_position(current, opening_low, opening_high)
    put("Session VWAP", vwap, _price_state(current, vwap), "Price relative to session VWAP")
    put("Opening Range High", opening_high, "BULLISH" if opening_high is not None and current > opening_high else "INFO", "First 15-minute high")
    put("Opening Range Low", opening_low, "BEARISH" if opening_low is not None and current < opening_low else "INFO", "First 15-minute low")
    put("Opening Range Position", opening_position, "BULLISH" if opening_position is not None and opening_position > 1 else "BEARISH" if opening_position is not None and opening_position < 0 else "NEUTRAL", "Position inside or outside opening range", 2)
    put("Session High", session_high, "BULLISH" if current >= session_high else "INFO", "Current session high")
    put("Session Low", session_low, "BEARISH" if current <= session_low else "INFO", "Current session low")
    put("Session Range", session_high - session_low, "INFO", "High less low for the current session")
    put("Session Change", current - session_open, "BULLISH" if current > session_open else "BEARISH", "Current close less session open")
    put("Pivot", pivot, _price_state(current, pivot), "Previous-session pivot")
    put("R1", r1, "INFO", "Previous-session first resistance")
    put("S1", s1, "INFO", "Previous-session first support")
    put("Previous Close", previous_close, _price_state(current, previous_close), "Most recent close from previous session")
    put("Price vs VWAP", current - vwap, _price_state(current, vwap), "Distance from session VWAP")
    put("Price vs Pivot", current - pivot if pivot is not None else None, _price_state(current, pivot), "Distance from previous-session pivot")
    put("Close Location in Range", _range_position(current, session_low, session_high), "INFO", "0 = session low; 1 = session high", 2)

    # Volume (15). Index-volume fields can be unavailable from the subscription;
    # the UI must say so instead of treating zero as a trade signal.
    if any(bar.volume > 0 for bar in candles):
        vols = [bar.volume for bar in candles]
        volume_sma = _sma([float(volume) for volume in vols], 20)
        session_volume = sum(bar.volume for bar in session)
        obv = _obv(candles)
        put("Relative Volume", relative_volume, "BULLISH" if relative_volume is not None and relative_volume >= 1.2 else "NEUTRAL", "Current volume relative to previous 20 bars", 2, "x")
        put("Current Bar Volume", float(vols[-1]), "INFO", "Latest completed one-minute volume", 0)
        put("Session Volume", float(session_volume), "INFO", "Cumulative current-session volume", 0)
        put("Volume SMA 20", volume_sma, "INFO", "20-bar volume average", 0)
        put("Volume Spike", relative_volume, "BULLISH" if relative_volume is not None and relative_volume >= 1.5 else "NEUTRAL", "Relative-volume spike check", 2, "x")
        put("OBV", obv, "BULLISH" if obv is not None and obv > 0 else "BEARISH", "On-balance volume from available candles", 0)
        for name in ("CMF 20", "MFI 14", "VWAP Volume Basis", "Volume ROC", "Accumulation/Distribution", "Price Volume Trend", "Ease of Movement", "Force Index", "Chaikin Oscillator"):
            values[name] = ("—", "FEED REQUIRED", "Requires validated trade-volume or depth data; not inferred from an index quote")
    else:
        for name in (name for category, name in _CATALOG if category == "Volume"):
            values[name] = ("—", "FEED REQUIRED", "This subscription does not provide usable index-volume data")

    # Options & flow are populated by the separate option/microstructure engines.
    # Keeping the rows visible makes each missing real-time feed explicit.
    for name in (name for category, name in _CATALOG if category == "Options & Flow"):
        values[name] = ("—", "FEED REQUIRED", "Displayed in option context after the corresponding live option/depth feed is available")

    return tuple(IndicatorReading(name, category, *values.get(name, ("—", "WAITING", "Awaiting indicator input"))) for category, name in _CATALOG)


def _sma(values: list[float], period: int) -> float | None:
    return sum(values[-period:]) / period if len(values) >= period else None


def _wma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    weights = list(range(1, period + 1))
    return sum(value * weight for value, weight in zip(values[-period:], weights)) / sum(weights)


def _macd(values: list[float]) -> tuple[float | None, float | None, float | None]:
    if len(values) < 35:
        return None, None, None
    lines = [_ema(values[:index], 12) - _ema(values[:index], 26) for index in range(26, len(values) + 1)]
    line = lines[-1]
    signal = _ema(lines, 9) if len(lines) >= 9 else None
    return line, signal, line - signal if signal is not None else None


def _stochastic(candles: tuple[Candle, ...], period: int = 14) -> tuple[float | None, float | None]:
    if len(candles) < period + 2:
        return None, None
    ks: list[float] = []
    for index in range(period, len(candles) + 1):
        segment = candles[index - period : index]
        high, low = max(bar.high for bar in segment), min(bar.low for bar in segment)
        ks.append((segment[-1].close - low) / (high - low) * 100 if high > low else 50.0)
    return ks[-1], sum(ks[-3:]) / min(3, len(ks))


def _williams_r(candles: tuple[Candle, ...], period: int = 14) -> float | None:
    if len(candles) < period:
        return None
    segment = candles[-period:]
    high, low = max(bar.high for bar in segment), min(bar.low for bar in segment)
    return (high - segment[-1].close) / (high - low) * -100 if high > low else -50.0


def _roc(values: list[float], period: int) -> float | None:
    return (values[-1] / values[-period - 1] - 1) * 100 if len(values) > period and values[-period - 1] else None


def _cci(candles: tuple[Candle, ...], period: int = 14) -> float | None:
    if len(candles) < period:
        return None
    typical = [(bar.high + bar.low + bar.close) / 3 for bar in candles[-period:]]
    mean = sum(typical) / period
    deviation = sum(abs(value - mean) for value in typical) / period
    return (typical[-1] - mean) / (0.015 * deviation) if deviation else 0.0


def _awesome(candles: tuple[Candle, ...]) -> float | None:
    if len(candles) < 34:
        return None
    median = [(bar.high + bar.low) / 2 for bar in candles]
    return _sma(median, 5) - _sma(median, 34)  # type: ignore[operator]


def _stddev(values: list[float], period: int) -> float | None:
    mean = _sma(values, period)
    return sqrt(sum((value - mean) ** 2 for value in values[-period:]) / period) if mean is not None else None


def _current_session(candles: tuple[Candle, ...]) -> tuple[Candle, ...]:
    session_date = candles[-1].opened_at.astimezone(IST).date()
    return tuple(bar for bar in candles if bar.opened_at.astimezone(IST).date() == session_date)


def _previous_session_close(candles: tuple[Candle, ...]) -> float | None:
    session_date = candles[-1].opened_at.astimezone(IST).date()
    prior = [bar for bar in candles if bar.opened_at.astimezone(IST).date() < session_date]
    return prior[-1].close if prior else None


def _pivots(candles: tuple[Candle, ...]) -> tuple[float | None, float | None, float | None]:
    session_date = candles[-1].opened_at.astimezone(IST).date()
    prior = [bar for bar in candles if bar.opened_at.astimezone(IST).date() < session_date]
    if not prior:
        return None, None, None
    high, low, close = max(bar.high for bar in prior), min(bar.low for bar in prior), prior[-1].close
    pivot = (high + low + close) / 3
    return pivot, 2 * pivot - low, 2 * pivot - high


def _range_position(value: float, low: float | None, high: float | None) -> float | None:
    return (value - low) / (high - low) if low is not None and high is not None and high > low else None


def _obv(candles: tuple[Candle, ...]) -> float | None:
    if not any(bar.volume > 0 for bar in candles):
        return None
    result = 0
    for previous, current in zip(candles, candles[1:]):
        result += current.volume if current.close > previous.close else -current.volume if current.close < previous.close else 0
    return float(result)


def _price_state(current: float, reference: float | None) -> str:
    if reference is None:
        return "WAITING"
    return "BULLISH" if current > reference else "BEARISH" if current < reference else "NEUTRAL"
