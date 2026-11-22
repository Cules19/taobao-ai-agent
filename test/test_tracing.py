from datetime import datetime, timezone
from unittest.mock import Mock

import tracing


def test_tracing_is_off_without_app_opt_in(monkeypatch):
    monkeypatch.delenv("SHOP_LANGSMITH_TRACING", raising=False)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "placeholder")
    client = Mock()
    monkeypatch.setattr(tracing, "smith_client", client)
    run = tracing.TurnTrace("opaque-id")
    run.record("model", datetime.now(timezone.utc), "ok")
    run.finish("ok")
    client.assert_not_called()


def test_tracing_submits_only_allowed_payload(monkeypatch):
    client = Mock()
    monkeypatch.setattr(tracing, "smith_client", lambda *args: client)
    monkeypatch.setattr(tracing._pool, "submit", lambda task, *args: task(*args))
    monkeypatch.setenv("SHOP_LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "private-api-key")
    run = tracing.TurnTrace("request-id")
    now = datetime.now(timezone.utc)
    run.record("query_order", now, "ok")
    run.record("retrieve_knowledge", now, "not_found")
    run.record("model", now, "error")
    run.record("sensitive-conversation DEMO1001", now, "ok")
    run.record("tools", now, "sensitive payload")
    run.finish("error")
    calls = client.create_run.call_args_list
    assert [call.args[0] for call in calls] == ["shop.turn", "query_order", "retrieve_knowledge", "model"]
    for call in calls:
        assert call.args[1] == {}
        assert set(call.kwargs["outputs"]) == {"status"}
        assert call.kwargs["extra"]["metadata"] == {"request_id": "request-id", "redaction": "metadata-only"}
        assert all(secret not in str(call) for secret in ("private-api-key", "DEMO1001", "sensitive payload"))
    assert calls[-1].kwargs["error"] == "node_failed"
    assert calls[-1].kwargs["parent_run_id"] == calls[0].kwargs["id"]
