"""Dependency-light, transparent one-minute market indicators."""

from datetime import datetime, timedelta, timezone

from nice_pro.models.market import Candle, IndicatorSnapshot, MarketRegime

# A fixed offset avoids requiring the IANA tzdata package on Windows. India does
# not observe daylight saving time, so this remains correct for market sessions.
IST = timezone(timedelta(hours=5, minutes=30), name="IST")


class IndicatorEngine:
    """Calculates a conservative first set of indicators from completed 1-minute bars.

    These values describe conditions; they are not a trade recommendation or a
    probability estimate. Weights and trade decisions arrive in later milestones.
    """

    def evaluate(self, symbol: str, candles: tuple[Candle, ...]) -> IndicatorSnapshot:
        if len(candles) < 21:
            return IndicatorSnapshot(
                symbol=symbol,
                regime=MarketRegime.INSUFFICIENT_DATA,
                calculated_at=_latest_time(candles),
                close=candles[-1].close if candles else None,
                reasons=(f"Waiting for 21 one-minute candles ({len(candles)}/21 collected)",),
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
