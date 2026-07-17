"""Cooldown-protected A/A+ desktop alerts."""

from datetime import datetime, timedelta, timezone

from nice_pro.models.market import ConvictionSnapshot, TradeGrade


class QualityAlertEngine:
    def __init__(self, cooldown_seconds: int = 300) -> None:
        self._cooldown = timedelta(seconds=cooldown_seconds)
        self._last_alert: dict[str, datetime] = {}

    def should_alert(self, snapshot: ConvictionSnapshot) -> bool:
        if snapshot.grade not in {TradeGrade.A, TradeGrade.A_PLUS} or snapshot.plan is None:
            return False
        now = datetime.now(timezone.utc)
        previous = self._last_alert.get(snapshot.underlying)
        if previous is not None and now - previous < self._cooldown:
            return False
        self._last_alert[snapshot.underlying] = now
        return True

    @staticmethod
    def play(grade: TradeGrade) -> None:
        """Best-effort sound; a missing audio device never stops the application."""
        try:
            import winsound

            if grade is TradeGrade.A_PLUS:
                for _ in range(3):
                    winsound.Beep(1200, 180)
            else:
                winsound.Beep(950, 180)
        except (ImportError, RuntimeError):
            return
