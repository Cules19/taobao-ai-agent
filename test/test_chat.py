from unittest.mock import Mock
from uuid import UUID

from fastapi.testclient import TestClient

import main

import pytest


@pytest.fixture
def client():
    with TestClient(main.app) as session:
        yield session


def test_ui_page_and_static_assets_are_served(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "导购对话" in page.text
    assert client.get("/assets/chat.js").status_code == 200
    assert client.get("/assets/styles.css").status_code == 200


def test_chat_returns_reply(monkeypatch, client):
    fake_run_turn = Mock(return_value={"reply": "你好，想找什么商品？",
                                       "products": [], "favorite_ids": []})
    monkeypatch.setattr(main.agent, "run_turn", fake_run_turn)

    response = client.post("/chat", json={"message": " 你好 "})

    assert response.status_code == 200
    assert response.json()["reply"] == "你好，想找什么商品？"
    assert UUID(response.json()["session_id"]).version == 4
    assert fake_run_turn.call_args.args[0] == "你好"


def test_chat_rejects_blank_message(client):
    response = client.post("/chat", json={"message": "   "})

    assert response.status_code == 422


def test_chat_handles_model_error(monkeypatch, client):
    fake_run_turn = Mock(side_effect=RuntimeError("配置缺失"))
    monkeypatch.setattr(main.agent, "run_turn", fake_run_turn)

    response = client.post("/chat", json={"message": "你好"})

    assert response.status_code == 503
    assert response.json() == {"detail": "模型服务暂时不可用"}
