from app.pilot_operations import PilotRateLimitMiddleware, _env_int


def test_env_int_clamps(monkeypatch):
    monkeypatch.setenv("X_LIMIT", "0")
    assert _env_int("X_LIMIT", 10) == 1
    monkeypatch.setenv("X_LIMIT", "9999999")
    assert _env_int("X_LIMIT", 10, maximum=100) == 100


def test_rate_limit_rules(monkeypatch):
    class URL:
        path = "/api/pilot/register"

    class Request:
        method = "POST"
        url = URL()

    monkeypatch.setenv("SRIS_RATE_LIMIT_SIGNUP_PER_15M", "7")
    assert PilotRateLimitMiddleware._rule(Request()) == (7, 900, "signup")

    Request.url.path = "/api/pilot/intelligence/analyze"
    monkeypatch.setenv("SRIS_RATE_LIMIT_AI_PER_MINUTE", "11")
    assert PilotRateLimitMiddleware._rule(Request()) == (11, 60, "ai")

    Request.method = "GET"
    assert PilotRateLimitMiddleware._rule(Request()) is None
