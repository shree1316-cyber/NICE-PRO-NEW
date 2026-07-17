from collections import deque


class MarketData:

    def __init__(self):

        self.latest = {}

        self.history = {}

    def update(self, symbol, tick):

        self.latest[symbol] = tick

        if symbol not in self.history:

            self.history[symbol] = deque(maxlen=5000)

        self.history[symbol].append(tick)

    def last(self, symbol):

        return self.latest.get(symbol)

    def ticks(self, symbol):

        return self.history.get(symbol, [])
