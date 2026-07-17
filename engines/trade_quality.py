class TradeQuality:

    def quality(

        self,

        probability,

        confidence,

        rr

    ):

        if (

            probability >= 90

            and confidence >= 90

            and rr >= 2

        ):

            return "A+"

        if (

            probability >= 80

            and confidence >= 80

        ):

            return "A"

        if probability >= 70:

            return "B"

        if probability >= 60:

            return "C"

        return "AVOID"
