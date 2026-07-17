import winsound


class AlertEngine:

    @staticmethod
    def a_plus():

        for _ in range(3):

            winsound.Beep(1200, 250)

    @staticmethod
    def a():

        winsound.Beep(1000, 250)

    @staticmethod
    def warning():

        winsound.Beep(450, 500)

    @staticmethod
    def target():

        winsound.Beep(1700, 200)
