from engines.market_data import MarketData


class TickRouter:

    def __init__(self):

        self.market = MarketData()

    def process(self, ticks):

        for tick in ticks:

            self.market.update(
                tick["instrument_token"],
                tick
            )
