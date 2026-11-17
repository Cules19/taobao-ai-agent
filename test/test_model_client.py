from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import model_client


def test_ask_model_calls_sdk(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-placeholder")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")

    fake_client = Mock()
    fake_client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="你好")
            )
        ]
    )
    fake_constructor = Mock(return_value=fake_client)
    monkeypatch.setattr(model_client, "OpenAI", fake_constructor)

    assert model_client.ask_model("我想买耳机") == "你好"
    fake_constructor.assert_called_once_with(
        api_key="unit-test-placeholder",
        base_url="https://example.test/v1",
    )
    fake_client.chat.completions.create.assert_called_once_with(
        model="test-model",
        messages=[{"role": "user", "content": "我想买耳机"}],
    )


def test_ask_model_requires_config(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "test-model")

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        model_client.ask_model("你好")