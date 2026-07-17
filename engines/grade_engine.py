class GradeEngine:

    @staticmethod
    def grade(score):

        if score >= 90:

            return "A+"

        if score >= 80:

            return "A"

        if score >= 70:

            return "B"

        if score >= 60:

            return "C"

        return "AVOID"
