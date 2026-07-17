class PremiumVelocity:

    def calculate(self, premiums):

        if len(premiums) < 2:

            return 0

        return premiums[-1] - premiums[-2]
