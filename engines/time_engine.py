from datetime import datetime


class TimeEngine:

    @staticmethod
    def market_open():

        now = datetime.now()

        return (
            now.hour > 9
            or (now.hour == 9 and now.minute >= 15)
        )

    @staticmethod
    def market_close():

        now = datetime.now()

        return (
            now.hour > 15
            or (now.hour == 15 and now.minute >= 30)
        )
