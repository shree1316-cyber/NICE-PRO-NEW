from kiteconnect import KiteConnect

from config import Config


class KiteEngine:

    def __init__(self):

        self.kite=KiteConnect(api_key=Config.API_KEY)

        self.kite.set_access_token(Config.ACCESS_TOKEN)

    def profile(self):

        return self.kite.profile()

    def instruments(self):

        return self.kite.instruments()

    def quote(self,symbol):

        return self.kite.quote(symbol)
