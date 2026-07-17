from dataclasses import dataclass


@dataclass
class Tick:

    symbol: str

    ltp: float

    volume: int

    bid: float

    ask: float

    tick_time: str
