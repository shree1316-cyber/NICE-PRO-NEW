from nice_pro.config.settings import Settings


def test_settings_reports_missing_kite_credentials(monkeypatch) -> None:
    monkeypatch.delenv("KITE_API_KEY", raising=False)
    monkeypatch.delenv("KITE_ACCESS_TOKEN", raising=False)
    assert Settings.load().kite_configured is False
