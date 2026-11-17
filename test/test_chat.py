from unittest.mock import Mock

from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_chat_returns_reply(monkeypatch):
    fake_ask_model = Mock(return_value="你好，想找什么商品？")
    monkeypatch.setattr(main.model_client, "ask_model", fake_ask_model)

    response = client.post("/chat", json={"message": " 你好 "})

    assert response.status_code == 200
    assert response.json() == {"reply": "你好，想找什么商品？"}
    fake_ask_model.assert_called_once_with("你好")


def test_chat_rejects_blank_message():
    response = client.post("/chat", json={"message": "   "})

    assert response.status_code == 422


def test_chat_handles_model_error(monkeypatch):
    fake_ask_model = Mock(side_effect=RuntimeError("配置缺失"))
    monkeypatch.setattr(main.model_client, "ask_model", fake_ask_model)

    response = client.post("/chat", json={"message": "你好"})

    assert response.status_code == 503
    assert response.json() == {"detail": "模型服务暂时不可用"}