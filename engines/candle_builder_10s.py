from datetime import datetime


class CandleBuilder10S:

    def __init__(self):

        self.current = None

        self.candles = []

    def update(self, price):

        now = datetime.now()

        bucket = now.second // 10

        key = (
            now.hour,
            now.minute,
            bucket
        )

        if self.current is None:

            self.current = {

                "bucket": key,

                "open": price,

                "high": price,

                "low": price,

                "close": price

            }

            return

        if self.current["bucket"] != key:

            self.candles.append(self.current)

            self.current = {

                "bucket": key,

                "open": price,

                "high": price,

                "low": price,

                "close": price

            }

            return

        self.current["high"] = max(
            self.current["high"],
            price
        )

        self.current["low"] = min(
            self.current["low"],
            price
        )

        self.current["close"] = price
