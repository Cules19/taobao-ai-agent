from dataclasses import replace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import main
from boundary import RequestBoundary
from runtime import Settings
from storage import ConversationBusy, ConversationMissing, Store


@pytest.fixture
def model(monkeypatch):
    handler = Mock(return_value={"reply": "测试回复", "products": [], "favorite_ids": []})
    monkeypatch.setattr(main.agent, "run_turn", handler)
    return handler


def test_history_survives_store_reopen_and_is_private(monkeypatch, model):
    owner = TestClient(main.app)
    other = TestClient(main.app)
    result = owner.post("/chat", json={"message": "买耳机"}).json()
    conversation_id = result["session_id"]
    path = "/api/conversations/" + conversation_id

    fresh_store = Store(main.settings.database, main.settings.retention_days)
    monkeypatch.setitem(main.app.dependency_overrides, main.get_store, lambda: fresh_store)
    assert owner.get("/api/conversations").json()["items"][0]["id"] == conversation_id
    assert owner.get(path).json()["turns"][0]["message"] == "买耳机"
    assert other.get(path).status_code == 404
    assert other.post("/chat", json={"session_id": conversation_id, "message": "继续"}).status_code == 404
    assert other.delete(path).status_code == 404
    assert model.call_count == 1
    assert owner.delete(path).status_code == 204
    assert owner.get(path).status_code == 404


def test_limits_stop_before_model(monkeypatch, model):
    monkeypatch.setattr(main, "settings", replace(main.settings, daily_limit=1))
    assert TestClient(main.app).post("/chat", json={"message": "first"}).status_code == 200
    response = TestClient(main.app).post("/chat", json={"message": "second"})
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
    assert model.call_count == 1


def test_body_limit_mime_and_headers(model):
    client = TestClient(main.app)
    assert client.post("/chat", content="raw").status_code == 415
    response = client.post("/chat", json={"message": "x" * 17000})
    assert response.status_code == 413
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in client.get("/").headers["content-security-policy"]
    assert not model.called


def test_production_boundary_and_cookie(monkeypatch, model):
    settings = replace(main.settings, production=True, origin="https://shop.example.test")
    monkeypatch.setattr(main, "settings", settings)
    client = TestClient(RequestBoundary(main.app, settings), base_url=settings.origin)
    assert client.post("/chat", json={"message": "hi"}).status_code == 403
    assert client.post("/chat", json={"message": "hi"},
                       headers={"Origin": "https://another.example.test"}).status_code == 403
    response = client.post("/chat", json={"message": "hi"}, headers={"Origin": settings.origin})
    assert response.status_code == 200 and model.call_count == 1
    cookie = response.headers["set-cookie"].lower()
    assert "__host-shop_visitor=" in cookie
    assert all(flag in cookie for flag in ("secure", "httponly", "samesite=strict"))


def test_lease_excludes_concurrent_turns_and_expired_session(tmp_path):
    store = Store(tmp_path / "lease.sqlite3", retention_days=1)
    key, lease, session, visible, title = store.begin("owner", None, 100)
    store.finish("owner", key, lease, session, visible, title, "问题", {"reply": "回复"}, 100)
    _, current, *_ = store.begin("owner", key, 101)
    with pytest.raises(ConversationBusy):
        store.begin("owner", key, 102)
    with pytest.raises(ConversationBusy):
        store.delete("owner", key, 102)
    store.release("owner", key, current)
    assert store.begin("owner", key, 103)[0] == key
    with pytest.raises(ConversationMissing):
        store.read("owner", key, 90000)


def test_production_missing_configuration_does_not_start(monkeypatch):
    monkeypatch.setenv("SHOP_ENV", "production")
    monkeypatch.setenv("SHOP_PUBLIC_ORIGIN", "http://example.test")
    with pytest.raises(RuntimeError, match="HTTPS"):
        Settings.from_env()
