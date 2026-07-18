"""Transparent intraday option-chain metrics; no trading decisions or orders."""

from collections import defaultdict, deque
from datetime import datetime, time
from math import erf, exp, log, sqrt

from nice_pro.engines.indicators import IST
from nice_pro.models.market import OptionChainSnapshot, OptionContract, OptionMetric, OptionType, Quote


class OptionChainEngine:
    def __init__(self, risk_free_rate: float = 0.065) -> None:
        self._risk_free_rate = risk_free_rate
        self._contracts: dict[int, OptionContract] = {}
        self._quotes: dict[int, Quote] = {}
        self._first_oi: dict[int, int] = {}
        self._premiums: dict[int, deque[Quote]] = defaultdict(lambda: deque(maxlen=12))

    def register(self, contracts: list[OptionContract]) -> None:
        self._contracts.update({contract.instrument_token: contract for contract in contracts})

    def is_option_token(self, token: int) -> bool:
        return token in self._contracts

    def update(self, quote: Quote, spot: float | None = None) -> OptionChainSnapshot | None:
        contract = self._contracts.get(quote.instrument_token)
        if contract is None:
            return None
        self._quotes[quote.instrument_token] = quote
        self._premiums[quote.instrument_token].append(quote)
        if quote.open_interest is not None:
            self._first_oi.setdefault(quote.instrument_token, quote.open_interest)
        return self.snapshot(contract.underlying, spot)

    def snapshot(self, underlying: str, spot: float | None = None) -> OptionChainSnapshot:
        contracts = [contract for contract in self._contracts.values() if contract.underlying == underlying]
        metrics = tuple(
            metric
            for contract in sorted(contracts, key=lambda item: (item.strike, item.option_type))
            if (metric := self._metric(contract, spot)) is not None
        )
        calls_oi = sum(metric.open_interest or 0 for metric in metrics if metric.contract.option_type is OptionType.CALL)
        puts_oi = sum(metric.open_interest or 0 for metric in metrics if metric.contract.option_type is OptionType.PUT)
        pcr = puts_oi / calls_oi if calls_oi else None
        strikes = sorted({contract.strike for contract in contracts})
        atm = min(strikes, key=lambda strike: abs(strike - spot)) if strikes and spot is not None else None
        observed_max_pain = _observed_max_pain(metrics, strikes)
        iv_skew = _atm_iv_skew(metrics, atm)
        expected_move = _atm_straddle(metrics, atm)
        return OptionChainSnapshot(
            underlying=underlying,
            calculated_at=datetime.now(tz=IST),
            spot=spot,
            atm_strike=atm,
            put_call_ratio_oi=pcr,
            metrics=metrics,
            observed_max_pain=observed_max_pain,
            iv_skew=iv_skew,
            expected_move=expected_move,
            observed_strikes=tuple(strikes),
        )

    def _metric(self, contract: OptionContract, spot: float | None) -> OptionMetric | None:
        quote = self._quotes.get(contract.instrument_token)
        if quote is None:
            return None
        baseline = self._first_oi.get(contract.instrument_token)
        oi_change = quote.open_interest - baseline if quote.open_interest is not None and baseline is not None else None
        velocity = _premium_velocity(tuple(self._premiums[contract.instrument_token]))
        iv = _implied_volatility(contract, quote, spot, self._risk_free_rate)
        return OptionMetric(contract, quote.last_price, quote.open_interest, oi_change, iv, velocity)


def _premium_velocity(quotes: tuple[Quote, ...]) -> float | None:
    if len(quotes) < 2:
        return None
    elapsed = (quotes[-1].received_at - quotes[0].received_at).total_seconds()
    return (quotes[-1].last_price - quotes[0].last_price) / elapsed if elapsed > 0 else None


def _observed_max_pain(metrics: tuple[OptionMetric, ...], strikes: list[float]) -> float | None:
    """Approximate max pain using only strikes that NICE-PRO subscribes to.

    A full-exchange max-pain figure needs OI at every strike. This function is
    intentionally scoped to observed contracts so it cannot silently imply
    exchange-wide coverage.
    """
    if not strikes or not metrics:
        return None
    losses: dict[float, float] = {}
    for settlement in strikes:
        total = 0.0
        for metric in metrics:
            oi = metric.open_interest or 0
            if metric.contract.option_type is OptionType.CALL:
                total += max(0.0, settlement - metric.contract.strike) * oi
            else:
                total += max(0.0, metric.contract.strike - settlement) * oi
        losses[settlement] = total
    return min(losses, key=losses.get)


def _atm_iv_skew(metrics: tuple[OptionMetric, ...], atm: float | None) -> float | None:
    if atm is None:
        return None
    ivs = {metric.contract.option_type: metric.implied_volatility for metric in metrics if metric.contract.strike == atm}
    call, put = ivs.get(OptionType.CALL), ivs.get(OptionType.PUT)
    return put - call if call is not None and put is not None else None


def _atm_straddle(metrics: tuple[OptionMetric, ...], atm: float | None) -> float | None:
    if atm is None:
        return None
    premiums = {metric.contract.option_type: metric.last_price for metric in metrics if metric.contract.strike == atm}
    call, put = premiums.get(OptionType.CALL), premiums.get(OptionType.PUT)
    return call + put if call is not None and put is not None else None


def _implied_volatility(contract: OptionContract, quote: Quote, spot: float | None, rate: float) -> float | None:
    if spot is None or spot <= 0 or quote.last_price <= 0:
        return None
    expiry = datetime.combine(contract.expiry, time(15, 30), tzinfo=IST)
    years = (expiry - quote.received_at.astimezone(IST)).total_seconds() / (365 * 24 * 60 * 60)
    if years <= 0:
        return None
    low, high = 0.01, 5.0
    target = quote.last_price
    if target < _black_scholes(spot, contract.strike, years, rate, low, contract.option_type):
        return None
    for _ in range(50):
        mid = (low + high) / 2
        if _black_scholes(spot, contract.strike, years, rate, mid, contract.option_type) < target:
            low = mid
        else:
            high = mid
    return (low + high) / 2 * 100


def _black_scholes(spot: float, strike: float, years: float, rate: float, sigma: float, option_type: OptionType) -> float:
    d1 = (log(spot / strike) + (rate + sigma * sigma / 2) * years) / (sigma * sqrt(years))
    d2 = d1 - sigma * sqrt(years)
    nd1, nd2 = _normal_cdf(d1), _normal_cdf(d2)
    if option_type is OptionType.CALL:
        return spot * nd1 - strike * exp(-rate * years) * nd2
    return strike * exp(-rate * years) * _normal_cdf(-d2) - spot * _normal_cdf(-d1)


def _normal_cdf(value: float) -> float:
    return (1 + erf(value / sqrt(2))) / 2
