from kite_api import KiteEngine


class InstrumentManager:

    def __init__(self):

        self.kite = KiteEngine()

        self.instrument_map = {}

    def load(self):

        instruments = self.kite.instruments()

        for item in instruments:

            key = f"{item['exchange']}:{item['tradingsymbol']}"

            self.instrument_map[key] = item

    def token(self, symbol):

        if symbol not in self.instrument_map:

            return None

        return self.instrument_map[symbol]["instrument_token"]

    def instrument(self, symbol):

        return self.instrument_map.get(symbol)
