from kiteconnect import KiteTicker

from config import Config


class KiteSocket:

    def __init__(self):

        self.kws = KiteTicker(
            Config.API_KEY,
            Config.ACCESS_TOKEN
        )

    def connect(self):

        self.kws.connect(threaded=True)

    def subscribe(self, tokens):

        self.kws.subscribe(tokens)

        self.kws.set_mode(
            self.kws.MODE_FULL,
            tokens
        )
