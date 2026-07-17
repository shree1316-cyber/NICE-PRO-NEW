import pandas as pd


class EMA:

    @staticmethod
    def ema(series: pd.Series, period: int):

        return series.ewm(
            span=period,
            adjust=False,
        ).mean()
