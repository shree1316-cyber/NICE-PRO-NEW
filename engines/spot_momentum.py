class SpotMomentum:

    def calculate(self, prices):

        if len(prices) < 5:

            return 0

        latest = prices[-1]

        avg = sum(prices[-5:]) / 5

        return latest - avg
