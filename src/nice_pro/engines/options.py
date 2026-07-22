"""Transparent intraday option-chain metrics; no trading decisions or orders."""

from collections import defaultdict, deque
from datetime import datetime, time, timezone
from math import erf, exp, log, sqrt

from nice_pro.engines.indicators import IST
from nice_pro.models.market import OptionChainSnapshot, OptionContract, OptionMetric, OptionType, Quote


class OptionChainEngine:
    """Nearest-expiry option-chain state with explicit data provenance.

    Kite supplies quote/depth snapshots, not a complete exchange order-event
    stream.  The engine therefore keeps direct fields and model-derived fields
    separate, and clears derived state after every stream interruption.
    """

    FRESH_QUOTE_MAX_AGE_SECONDS = 10.0

    def __init__(self, risk_free_rate: float = 0.065) -> None:
        self._risk_free_rate = risk_free_rate
        self._contracts: dict[int, OptionContract] = {}
        self._quotes: dict[int, Quote] = {}
        self._first_oi: dict[int, int] = {}
        self._premiums: dict[int, deque[Quote]] = defaultdict(lambda: deque(maxlen=12))
        self._estimated_cvd: dict[int, int] = defaultdict(int)
        # A signed-volume estimate needs at least two consecutive quotes.  A
        # zero on the first quote must remain "not ready", not be displayed as
        # a neutral live CVD reading.
        self._cvd_ready_tokens: set[int] = set()

    def register(self, contracts: list[OptionContract]) -> None:
        self._contracts.update({contract.instrument_token: contract for contract in contracts})

    def reset_derived_metrics(self) -> None:
        """Discard pre-interruption option state before the next stream quote.

        An estimated CVD or premium velocity spanning a WebSocket outage is not
        an honest live measurement.  Clearing quote history forces the model to
        warm up again rather than silently treating missed ticks as flow.
        Session OI baselines are intentionally retained because they represent
        the first observed OI for the current application session.
        """
        self._quotes.clear()
        self._premiums.clear()
        self._estimated_cvd.clear()
        self._cvd_ready_tokens.clear()

    def is_option_token(self, token: int) -> bool:
        return token in self._contracts

    def ingest(self, quote: Quote) -> OptionContract | None:
        """Store one option tick without recalculating the whole chain."""
        contract = self._contracts.get(quote.instrument_token)
        if contract is None:
            return None
        previous = self._quotes.get(quote.instrument_token)
        self._estimated_cvd[quote.instrument_token] += _estimated_signed_volume(quote, previous)
        if previous is not None:
            self._cvd_ready_tokens.add(quote.instrument_token)
        self._quotes[quote.instrument_token] = quote
        self._premiums[quote.instrument_token].append(quote)
        if quote.open_interest is not None:
            self._first_oi.setdefault(quote.instrument_token, quote.open_interest)
        return contract

    def update(self, quote: Quote, spot: float | None = None) -> OptionChainSnapshot | None:
        """Compatibility helper for callers/tests needing an immediate snapshot."""
        contract = self.ingest(quote)
        if contract is None:
            return None
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
        atm_spread = _atm_bid_ask_spread(metrics, atm)
        atm_imbalance = _atm_book_imbalance(metrics, atm)
        atm_cvd = _atm_estimated_cvd(metrics, atm)
        otm_continuation = _otm_continuation(metrics, atm)
        now = datetime.now(timezone.utc)
        quoted_contracts = sum(contract.instrument_token in self._quotes for contract in contracts)
        quote_ages = [
            _quote_age_seconds(self._quotes[contract.instrument_token].received_at, now)
            for contract in contracts
            if contract.instrument_token in self._quotes
        ]
        fresh_contracts = sum(age <= self.FRESH_QUOTE_MAX_AGE_SECONDS for age in quote_ages)
        atm_ages = [
            _quote_age_seconds(metric.quote_received_at, now)
            for metric in metrics
            if metric.contract.strike == atm and metric.quote_received_at is not None
        ]
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
            atm_bid_ask_spread=atm_spread,
            atm_book_imbalance=atm_imbalance,
            atm_estimated_cvd=atm_cvd,
            otm_continuation=otm_continuation,
            registered_contracts=len(contracts),
            quoted_contracts=quoted_contracts,
            fresh_contracts=fresh_contracts,
            oldest_quote_age_seconds=max(quote_ages) if quote_ages else None,
            # Both ATM CE and PE must be current, so use the older quote age.
            atm_quote_age_seconds=max(atm_ages) if len(atm_ages) == 2 else None,
        )

    def _metric(self, contract: OptionContract, spot: float | None) -> OptionMetric | None:
        quote = self._quotes.get(contract.instrument_token)
        if quote is None:
            return None
        baseline = self._first_oi.get(contract.instrument_token)
        oi_change = quote.open_interest - baseline if quote.open_interest is not None and baseline is not None else None
        velocity = _premium_velocity(tuple(self._premiums[contract.instrument_token]))
        iv = _implied_volatility(contract, quote, spot, self._risk_free_rate)
        return OptionMetric(
            contract, quote.last_price, quote.open_interest, oi_change, iv, velocity,
            quote.bid, quote.ask, quote.top_bid_quantity, quote.top_ask_quantity,
            quote.bid_depth_quantity, quote.ask_depth_quantity,
            (
                self._estimated_cvd.get(contract.instrument_token)
                if contract.instrument_token in self._cvd_ready_tokens
                else None
            ),
            quote.received_at,
        )


def _premium_velocity(quotes: tuple[Quote, ...]) -> float | None:
    if len(quotes) < 2:
        return None
    # Quote timestamps should already be normalised by KiteService, but retain
    # this guard for test data and any future data-provider integration.
    elapsed = (_as_aware_utc(quotes[-1].received_at) - _as_aware_utc(quotes[0].received_at)).total_seconds()
    return (quotes[-1].last_price - quotes[0].last_price) / elapsed if elapsed > 0 else None


def _estimated_signed_volume(current: Quote, previous: Quote | None) -> int:
    """Estimate aggressor-signed volume from top-of-book and price movement.

    Kite does not send exchange trade-side/aggressor flags. This is therefore
    explicitly an estimate, never true exchange CVD.
    """
    if previous is None:
        return 0
    size = current.last_quantity or 0
    if not size and current.volume is not None and previous.volume is not None:
        size = max(0, current.volume - previous.volume)
    if size <= 0:
        return 0
    if current.ask is not None and current.last_price >= current.ask:
        return size
    if current.bid is not None and current.last_price <= current.bid:
        return -size
    if current.last_price > previous.last_price:
        return size
    if current.last_price < previous.last_price:
        return -size
    return 0


def _as_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=IST)
    return value.astimezone(timezone.utc)


def _quote_age_seconds(value: datetime, now: datetime) -> float:
    """Return a non-negative quote age despite minor exchange-clock skew."""
    return max(0.0, (_as_aware_utc(now) - _as_aware_utc(value)).total_seconds())


def _observed_max_pain(metrics: tuple[OptionMetric, ...], strikes: list[float]) -> float | None:
    """Calculate max pain from the contracts presently held in the chain.

    In full-current-expiry mode this covers every subscribed CE/PE strike for
    the nearest expiry. It is not an all-expiries exchange metric.
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


def _atm_bid_ask_spread(metrics: tuple[OptionMetric, ...], atm: float | None) -> float | None:
    spreads = [
        metric.ask - metric.bid
        for metric in metrics
        if metric.contract.strike == atm and metric.bid is not None and metric.ask is not None and metric.ask >= metric.bid
    ]
    return sum(spreads) / len(spreads) if spreads else None


def _atm_book_imbalance(metrics: tuple[OptionMetric, ...], atm: float | None) -> float | None:
    """Direct top-five-depth imbalance, normalized to -1 .. +1."""
    bids = sum(metric.bid_depth_quantity or 0 for metric in metrics if metric.contract.strike == atm)
    asks = sum(metric.ask_depth_quantity or 0 for metric in metrics if metric.contract.strike == atm)
    total = bids + asks
    return (bids - asks) / total if total else None


def _atm_estimated_cvd(metrics: tuple[OptionMetric, ...], atm: float | None) -> int | None:
    calls = [metric.estimated_cvd for metric in metrics if metric.contract.strike == atm and metric.contract.option_type is OptionType.CALL]
    puts = [metric.estimated_cvd for metric in metrics if metric.contract.strike == atm and metric.contract.option_type is OptionType.PUT]
    if not calls or not puts or calls[0] is None or puts[0] is None:
        return None
    # Rising call-aggression relative to put-aggression is positive for the
    # underlying; the inverse is negative.
    return calls[0] - puts[0]


def _otm_continuation(metrics: tuple[OptionMetric, ...], atm: float | None) -> float | None:
    """Derived OTM continuation score from the first available OTM pair.

    Positive means call-led continuation, negative means put-led continuation.
    It is a chain-derived estimate, not an exchange-labelled order-flow event.
    """
    if atm is None:
        return None
    call_candidates = sorted(
        (metric for metric in metrics if metric.contract.option_type is OptionType.CALL and metric.contract.strike > atm),
        key=lambda metric: metric.contract.strike,
    )
    put_candidates = sorted(
        (metric for metric in metrics if metric.contract.option_type is OptionType.PUT and metric.contract.strike < atm),
        key=lambda metric: metric.contract.strike,
        reverse=True,
    )
    if not call_candidates or not put_candidates:
        return None
    call_velocity, put_velocity = call_candidates[0].premium_velocity, put_candidates[0].premium_velocity
    if call_velocity is None or put_velocity is None:
        return None
    return call_velocity - put_velocity


def _implied_volatility(contract: OptionContract, quote: Quote, spot: float | None, rate: float) -> float | None:
    if spot is None or spot <= 0 or quote.last_price <= 0:
        return None
    expiry = datetime.combine(contract.expiry, time(15, 30), tzinfo=IST)
    years = (expiry - _as_aware_utc(quote.received_at).astimezone(IST)).total_seconds() / (365 * 24 * 60 * 60)
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
