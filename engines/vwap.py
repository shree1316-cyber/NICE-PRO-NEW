import pandas as pd


class VWAP:

    @staticmethod
    def calculate(df: pd.DataFrame):

        tp = (
            df["high"]
            + df["low"]
            + df["close"]
        ) / 3

        return (
            tp * df["volume"]
        ).cumsum() / df["volume"].cumsum()
